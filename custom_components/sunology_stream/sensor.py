"""Sensor platform for the Sunology Stream integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunologyStreamConfigEntry
from .const import DOMAIN
from .coordinator import SunologyStreamData, SunologyStreamDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class SunologyStreamSensorDescription(SensorEntityDescription):
    """Describes a Sunology Stream sensor entity."""

    value_fn: Callable[[SunologyStreamData], float | None]


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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunologyStreamConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sunology Stream sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        SunologyStreamSensor(coordinator, entry.entry_id, description)
        for description in SENSOR_DESCRIPTIONS
    )


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
