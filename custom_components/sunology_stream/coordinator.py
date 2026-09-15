"""DataUpdateCoordinator for the Sunology Stream integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    SunologyStreamApiClient,
    SunologyStreamAuthError,
    SunologyStreamConnectionError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

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

    async def _async_update_data(self) -> SunologyStreamData:
        try:
            client = await self.api.get_client()
            overview = await self.api.get_overview()

            now = dt_util.now()
            history_daily = await self.api.get_history_daily(
                now.strftime("%Y-%m-%d"), now.strftime("%z")
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
        )
