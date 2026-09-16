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
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
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
    ] = [
        SunologyStreamSensor(coordinator, entry.entry_id, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    if coordinator.data.erl:
        entities.append(
            SunologyStreamSensor(coordinator, entry.entry_id, ERL_LAST_SYNC_DESCRIPTION)
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
