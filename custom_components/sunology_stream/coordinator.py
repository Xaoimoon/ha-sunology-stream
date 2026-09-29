"""DataUpdateCoordinator for the Sunology Stream integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SunologyStreamApiClient,
    SunologyStreamApiError,
    SunologyStreamAuthError,
    SunologyStreamConnectionError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, SLOW_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class SunologyStreamData:
    """Snapshot of the data polled from the Sunology Stream API."""

    client: dict[str, Any]
    overview: dict[str, Any]
    history_daily: dict[str, Any]
    erl: dict[str, Any] | None
    # Raw lists kept for future use — no entities built on top yet since this
    # account has hasGridStreamMeter/hasStorageBattery both False, so we have
    # no real non-empty response shape to design entities against.
    stream_meters: list[Any]
    storage_batteries: list[Any]
    # Both refreshed every SLOW_SCAN_INTERVAL, and None if never fetched
    # successfully (or, for day_energy, if the account has no ERL).
    contract: dict[str, Any] | None = None
    day_energy: dict[str, Any] | None = None
    # Local midnight of the day `day_energy` covers. Usually today, but
    # yesterday between midnight and the end of today's first hour.
    day_energy_start: datetime | None = None
    # Per-panel details from /solar-panels/{id}, keyed by serial number.
    panel_details: dict[str, dict[str, Any]] = field(default_factory=dict)


def zone_param(now: datetime) -> str:
    """Format the API "zone" param: the UTC offset in hours, e.g. "2"."""
    offset = now.utcoffset()
    hours = offset.total_seconds() / 3600 if offset else 0.0
    return str(int(hours)) if hours.is_integer() else str(hours)


def local_midnight(now: datetime) -> datetime:
    """Midnight of `now`'s day, in `now`'s time zone."""
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def day_param(now: datetime) -> str:
    """Local midnight of `now`'s day as a UTC ISO timestamp, like the app's
    `startOfDay(date).toISOString()`, e.g. "2026-09-25T22:00:00.000Z".
    """
    return dt_util.as_utc(local_midnight(now)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class SunologyStreamDataUpdateCoordinator(DataUpdateCoordinator[SunologyStreamData]):
    """Coordinates polling of the Sunology Stream cloud API."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, api: SunologyStreamApiClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.api = api
        self._contract: dict[str, Any] | None = None
        self._day_energy: dict[str, Any] | None = None
        self._day_energy_start: datetime | None = None
        self._panel_details: dict[str, dict[str, Any]] = {}
        self._slow_refreshed_at: datetime | None = None
        self._slow_refreshed_day: str | None = None

    async def _async_update_data(self) -> SunologyStreamData:
        try:
            client = await self.api.get_client()
            overview = await self.api.get_overview()

            now = dt_util.now()
            zone = zone_param(now)
            history_daily = await self.api.get_history_daily(
                now.strftime("%Y-%m-%d"), zone
            )

            erl: dict[str, Any] | None = None
            if client.get("hasErl"):
                erl = await self.api.get_erl()

            stream_meters: list[Any] = []
            if client.get("hasGridStreamMeter"):
                stream_meters = await self.api.get_stream_meter()

            storage_batteries: list[Any] = []
            if client.get("hasStorageBattery"):
                storage_batteries = await self.api.get_storage_battery_all_paired()

            await self._async_refresh_slow_data(
                now,
                zone,
                bool(client.get("hasErl")),
                set(overview.get("production", {}).get("panels", {})),
            )
        except SunologyStreamAuthError as err:
            raise ConfigEntryAuthFailed("Session expired and re-login failed") from err
        except SunologyStreamConnectionError as err:
            raise UpdateFailed(f"Cannot reach Sunology Stream API: {err}") from err

        return SunologyStreamData(
            client=client,
            overview=overview,
            history_daily=history_daily,
            erl=erl,
            stream_meters=stream_meters,
            storage_batteries=storage_batteries,
            contract=self._contract,
            day_energy=self._day_energy,
            day_energy_start=self._day_energy_start,
            panel_details=dict(self._panel_details),
        )

    async def _async_refresh_slow_data(
        self, now: datetime, zone: str, has_erl: bool, panel_serials: set[str]
    ) -> None:
        """Refresh the contract, today's hourly energy and the panel details, at most every
        SLOW_SCAN_INTERVAL (and right away when the local day changes).

        These endpoints are best-effort: a failure keeps the previous values
        instead of failing the whole update, so live power keeps working.
        """
        day = day_param(now)
        if (
            self._slow_refreshed_at is not None
            and now - self._slow_refreshed_at < SLOW_SCAN_INTERVAL
            and day == self._slow_refreshed_day
        ):
            return

        try:
            self._contract = await self.api.get_signed_contract()
        except SunologyStreamAuthError:
            raise
        except SunologyStreamApiError as err:
            _LOGGER.debug("Cannot fetch the signed contract: %s", err)

        if has_erl:
            await self._async_refresh_day_energy(now, zone)

        await self._async_refresh_panel_details(panel_serials)

        self._slow_refreshed_at = now
        self._slow_refreshed_day = day

    async def _async_refresh_day_energy(self, now: datetime, zone: str) -> None:
        """Refresh the hourly energy/costs of today, or finish yesterday's.

        The API only lists completed hours and answers 500 for a day that has
        none yet, i.e. from midnight until about 01:00. Until today's data
        exists, yesterday is fetched instead, so its 23:00-24:00 hour (only
        complete after midnight) still gets counted before the daily reset.
        """
        today = local_midnight(now)
        try:
            self._day_energy = await self.api.get_energy_amounts_and_costs_for_day(
                day_param(today), zone
            )
            self._day_energy_start = today
            return
        except SunologyStreamAuthError:
            raise
        except SunologyStreamApiError as err:
            if self._day_energy_start == today:
                # Today's data already exists: a transient error, keep it.
                _LOGGER.debug("Cannot fetch today's energy amounts: %s", err)
                return
            _LOGGER.debug("No energy amounts for today yet (%s), finishing yesterday", err)

        # Wall-clock arithmetic on the local time zone: DST-safe.
        yesterday = local_midnight(today - timedelta(hours=1))
        try:
            self._day_energy = await self.api.get_energy_amounts_and_costs_for_day(
                day_param(yesterday), zone
            )
            self._day_energy_start = yesterday
        except SunologyStreamAuthError:
            raise
        except SunologyStreamApiError as err:
            _LOGGER.debug("Cannot fetch yesterday's energy amounts: %s", err)
            if self._day_energy_start != yesterday:
                # Never keep data older than yesterday.
                self._day_energy = None
                self._day_energy_start = None

    async def _async_refresh_panel_details(self, panel_serials: set[str]) -> None:
        """Fetch /solar-panels/{id} for each panel listed in the overview.

        The overview keys panels by serial number, but /solar-panels wants
        the device id, so the mapping comes from /devices/stations-and-storages.
        A panel whose fetch fails keeps its previous details.
        """
        if not panel_serials:
            return
        try:
            devices = await self.api.get_stations_and_storages()
        except SunologyStreamAuthError:
            raise
        except SunologyStreamApiError as err:
            _LOGGER.debug("Cannot list the account's devices: %s", err)
            return

        for device in devices or []:
            serial_number = device.get("serialNumber")
            if serial_number not in panel_serials or not device.get("id"):
                continue
            try:
                self._panel_details[serial_number] = await self.api.get_solar_panel(
                    device["id"]
                )
            except SunologyStreamAuthError:
                raise
            except SunologyStreamApiError as err:
                _LOGGER.debug("Cannot fetch details of panel %s: %s", serial_number, err)
