"""Sensor platform for the Sunology Stream integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CURRENCY_EURO,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import SunologyStreamConfigEntry
from .coordinator import SunologyStreamData, SunologyStreamDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class SunologyStreamSensorDescription(SensorEntityDescription):
    """Describes a Sunology Stream sensor entity."""

    value_fn: Callable[[SunologyStreamData], Any]
    # For state_class TOTAL sensors that restart from 0 at local midnight:
    # exposes last_reset so long-term statistics handle the daily reset.
    resets_daily: bool = False


SENSOR_DESCRIPTIONS: tuple[SunologyStreamSensorDescription, ...] = (
    SunologyStreamSensorDescription(
        key="production_power",
        translation_key="production_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.get("production", {}).get("total"),
    ),
    SunologyStreamSensorDescription(
        key="consumption_power",
        translation_key="consumption_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.get("consumptionData", {}).get("total"),
    ),
    SunologyStreamSensorDescription(
        key="grid_purchased_power",
        translation_key="grid_purchased_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.get("consumptionData", {}).get("purchased"),
    ),
    SunologyStreamSensorDescription(
        key="daily_production_energy",
        translation_key="daily_production_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _history_watt_value(data, "productionHistory"),
    ),
    SunologyStreamSensorDescription(
        key="daily_consumption_energy",
        translation_key="daily_consumption_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _history_watt_value(data, "consumptionHistory"),
    ),
    SunologyStreamSensorDescription(
        key="self_reliance",
        translation_key="self_reliance",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.history_daily.get("selfReliance"),
    ),
)


def _history_watt_value(data: SunologyStreamData, section: str) -> Any:
    """Extract the raw Wh total from a history_daily section, e.g.
    history_daily["productionHistory"]["total"]["wattValueSuffix"]["value"].
    """
    return (
        data.history_daily.get(section, {})
        .get("total", {})
        .get("wattValueSuffix", {})
        .get("value")
    )

ERL_LAST_SYNC_DESCRIPTION = SunologyStreamSensorDescription(
    key="erl_last_synchronization",
    translation_key="erl_last_synchronization",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda data: _parse_erl_timestamp(data),
)


def _parse_erl_timestamp(data: SunologyStreamData) -> datetime | None:
    if not data.erl:
        return None
    raw = data.erl.get("lastSynchronizationDate")
    if not raw:
        return None
    return dt_util.parse_datetime(raw)


def _off_peak_ranges(contract: dict[str, Any] | None) -> list[tuple[int, int]]:
    """Off-peak ranges from the signed contract, in minutes since midnight.

    The contract splits ranges at midnight ({"start": "22:56", "end": "00:00"}
    and {"start": "00:00", "end": "06:56"}); an "end" of "00:00" means 24:00.
    """
    if not contract:
        return []
    ranges = []
    for item in contract.get("config", {}).get("off_peak_hours") or []:
        try:
            start_h, start_m = (int(x) for x in item["start"].split(":"))
            end_h, end_m = (int(x) for x in item["end"].split(":"))
        except (KeyError, ValueError, AttributeError):
            continue
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m or 24 * 60
        if end > start:
            ranges.append((start, end))
        else:
            ranges.extend([(start, 24 * 60), (0, end)])
    return ranges


def _off_peak_fraction(hour_start: datetime, ranges: list[tuple[int, int]]) -> float:
    """Share of the hour starting at `hour_start` (local) that is off-peak."""
    start = hour_start.hour * 60 + hour_start.minute
    end = start + 60
    overlap = sum(max(0, min(end, r_end) - max(start, r_start)) for r_start, r_end in ranges)
    return min(overlap, 60) / 60


def _day_energy_hours(data: SunologyStreamData) -> list[tuple[datetime, dict[str, Any]]]:
    """Today's completed hours as (local hour start, values) pairs."""
    if not data.day_energy:
        return []
    hours = []
    for key, values in (data.day_energy.get("energyAmountsAndCostsByHour") or {}).items():
        parsed = dt_util.parse_datetime(key)
        if parsed is None:
            continue
        hours.append((dt_util.as_local(parsed), values))
    return hours


def _day_consumption_split(data: SunologyStreamData, off_peak: bool) -> float | None:
    """Today's grid consumption (kWh) during off-peak or peak hours.

    Hours straddling a tariff change (e.g. 06:00-07:00 with off-peak ending at
    06:56) are split pro rata, the same way the API prices them.
    """
    ranges = _off_peak_ranges(data.contract)
    if not ranges or data.day_energy is None:
        return None
    total = 0.0
    for hour_start, values in _day_energy_hours(data):
        fraction = _off_peak_fraction(hour_start, ranges)
        total += (values.get("consumptionInKWh") or 0) * (fraction if off_peak else 1 - fraction)
    return round(total, 3)


def _day_consumption_cost(
    data: SunologyStreamData, off_peak: bool | None = None
) -> float | None:
    """Today's grid consumption cost (EUR), as priced by the API.

    With `off_peak` set, only the off-peak (True) or peak (False) share. The
    two hours straddling a tariff change are split by duration, which is off
    by less than a cent a day compared to pricing each part separately.
    """
    if data.day_energy is None:
        return None
    ranges = _off_peak_ranges(data.contract)
    if off_peak is not None and not ranges:
        return None
    total = 0.0
    for hour_start, values in _day_energy_hours(data):
        cost = values.get("consumptionInEuros") or 0
        if off_peak is not None:
            fraction = _off_peak_fraction(hour_start, ranges)
            cost *= fraction if off_peak else 1 - fraction
        total += cost
    return round(total, 2)


# Built on /client/energyAmountsAndCostsForDay, which only lists completed
# hours: these lag real time by up to an hour, and until about 01:00 they
# still show yesterday's full total (including its 23:00-24:00 hour).
OFF_PEAK_DESCRIPTIONS: tuple[SunologyStreamSensorDescription, ...] = (
    SunologyStreamSensorDescription(
        key="daily_off_peak_consumption_energy",
        translation_key="daily_off_peak_consumption_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _day_consumption_split(data, off_peak=True),
    ),
    SunologyStreamSensorDescription(
        key="daily_peak_consumption_energy",
        translation_key="daily_peak_consumption_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _day_consumption_split(data, off_peak=False),
    ),
    # Meant as the "entity tracking the total costs" of the matching grid
    # consumption source in the Energy dashboard.
    SunologyStreamSensorDescription(
        key="daily_off_peak_consumption_cost",
        translation_key="daily_off_peak_consumption_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        state_class=SensorStateClass.TOTAL,
        resets_daily=True,
        value_fn=lambda data: _day_consumption_cost(data, off_peak=True),
    ),
    SunologyStreamSensorDescription(
        key="daily_peak_consumption_cost",
        translation_key="daily_peak_consumption_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        state_class=SensorStateClass.TOTAL,
        resets_daily=True,
        value_fn=lambda data: _day_consumption_cost(data, off_peak=False),
    ),
)

DAILY_CONSUMPTION_COST_DESCRIPTION = SunologyStreamSensorDescription(
    key="daily_consumption_cost",
    translation_key="daily_consumption_cost",
    device_class=SensorDeviceClass.MONETARY,
    native_unit_of_measurement=CURRENCY_EURO,
    state_class=SensorStateClass.TOTAL,
    resets_daily=True,
    value_fn=_day_consumption_cost,
)


@dataclass(frozen=True, kw_only=True)
class SunologyStreamPanelDetailDescription(SensorEntityDescription):
    """Describes a per-panel sensor built on /solar-panels/{id}."""

    name_suffix: str
    value_fn: Callable[[dict[str, Any]], Any]
    # Only created for panels with an integrated battery (overview "has_b").
    requires_battery: bool = False


def _parse_timestamp(raw: Any) -> datetime | None:
    return dt_util.parse_datetime(raw) if raw else None


PANEL_DETAIL_DESCRIPTIONS: tuple[SunologyStreamPanelDetailDescription, ...] = (
    SunologyStreamPanelDetailDescription(
        key="wifi_signal",
        name_suffix="WiFi signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: details.get("rssiWifi"),
    ),
    SunologyStreamPanelDetailDescription(
        key="firmware_version",
        name_suffix="firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: details.get("firmwareVersion"),
    ),
    SunologyStreamPanelDetailDescription(
        key="last_synchronization",
        name_suffix="last synchronization",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: _parse_timestamp(details.get("lastSynchronizationDate")),
    ),
    # Grid power above which the battery starts charging (app: 210-450 W).
    SunologyStreamPanelDetailDescription(
        key="battery_charge_threshold",
        name_suffix="battery charge threshold",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: details.get("batteryThreshold"),
        requires_battery=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunologyStreamConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sunology Stream sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator

    entities: list[
        SunologyStreamSensor
        | SunologyStreamPanelProductionSensor
        | SunologyStreamPanelBatteryLevelSensor
        | SunologyStreamPanelBatteryStateSensor
        | SunologyStreamPanelDetailSensor
    ] = [
        SunologyStreamSensor(coordinator, entry.entry_id, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    if coordinator.data.erl:
        entities.append(
            SunologyStreamSensor(coordinator, entry.entry_id, ERL_LAST_SYNC_DESCRIPTION)
        )
        entities.append(
            SunologyStreamSensor(
                coordinator, entry.entry_id, DAILY_CONSUMPTION_COST_DESCRIPTION
            )
        )
        # Only for peak/off-peak contracts, which carry off-peak hours.
        if _off_peak_ranges(coordinator.data.contract):
            entities.extend(
                SunologyStreamSensor(coordinator, entry.entry_id, description)
                for description in OFF_PEAK_DESCRIPTIONS
            )

    # Panel list is discovered at setup time from the first coordinator
    # refresh. A panel added to the account later would need a reload of
    # this config entry to show up — acceptable for now.
    panels = coordinator.data.overview.get("production", {}).get("panels", {})
    for serial_number, panel_data in panels.items():
        surname = panel_data.get("surname")
        entities.append(
            SunologyStreamPanelProductionSensor(
                coordinator, entry.entry_id, serial_number, surname
            )
        )
        entities.append(
            SunologyStreamPanelBatteryLevelSensor(
                coordinator, entry.entry_id, serial_number, surname
            )
        )
        entities.append(
            SunologyStreamPanelBatteryStateSensor(
                coordinator, entry.entry_id, serial_number, surname
            )
        )
        if serial_number in coordinator.data.panel_details:
            entities.extend(
                SunologyStreamPanelDetailSensor(
                    coordinator, entry.entry_id, serial_number, surname, description
                )
                for description in PANEL_DETAIL_DESCRIPTIONS
                if panel_data.get("has_b") or not description.requires_battery
            )

    async_add_entities(entities)


class SunologyStreamSensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], SensorEntity
):
    """A Sunology Stream sensor backed by the shared coordinator."""

    entity_description: SunologyStreamSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        description: SunologyStreamSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def last_reset(self) -> datetime | None:
        # The day the published data covers, not the current day: just after
        # midnight the value is still yesterday's total (see coordinator).
        if self.entity_description.resets_daily:
            return self.coordinator.data.day_energy_start
        return None


class SunologyStreamPanelProductionSensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], SensorEntity
):
    """Production power for a single solar panel."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        surname: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._serial_number = serial_number
        self._attr_unique_id = f"{entry_id}_panel_{serial_number}_production"
        self._attr_name = f"{surname or serial_number} production"

    @property
    def native_value(self) -> Any:
        panels = self.coordinator.data.overview.get("production", {}).get("panels", {})
        panel = panels.get(self._serial_number, {})
        return panel.get("production")


class SunologyStreamPanelBatteryLevelSensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], SensorEntity
):
    """State of charge for a panel's integrated battery (0 for panels without one)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        surname: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._serial_number = serial_number
        self._attr_unique_id = f"{entry_id}_panel_{serial_number}_battery_level"
        self._attr_name = f"{surname or serial_number} battery level"

    @property
    def native_value(self) -> Any:
        panels = self.coordinator.data.overview.get("production", {}).get("panels", {})
        panel = panels.get(self._serial_number, {})
        return panel.get("battery")


class SunologyStreamPanelBatteryStateSensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], SensorEntity
):
    """Raw charge/discharge state for a panel's integrated battery.

    Exposed as a plain string (not device_class enum) since the full set of
    values the API can return isn't confirmed yet — only "OFF",
    "DISCHARGING" and "UNPLUGGED" have been observed.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        surname: str | None,
    ) -> None:
        super().__init__(coordinator)
        self._serial_number = serial_number
        self._attr_unique_id = f"{entry_id}_panel_{serial_number}_battery_state"
        self._attr_name = f"{surname or serial_number} battery state"

    @property
    def native_value(self) -> Any:
        panels = self.coordinator.data.overview.get("production", {}).get("panels", {})
        panel = panels.get(self._serial_number, {})
        return panel.get("batteryState")


class SunologyStreamPanelDetailSensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], SensorEntity
):
    """A per-panel diagnostic sensor built on /solar-panels/{id}."""

    entity_description: SunologyStreamPanelDetailDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        surname: str | None,
        description: SunologyStreamPanelDetailDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._serial_number = serial_number
        self._attr_unique_id = f"{entry_id}_panel_{serial_number}_{description.key}"
        self._attr_name = f"{surname or serial_number} {description.name_suffix}"

    @property
    def native_value(self) -> Any:
        details = self.coordinator.data.panel_details.get(self._serial_number)
        if details is None:
            return None
        return self.entity_description.value_fn(details)
