"""Binary sensor platform for the Sunology Stream integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunologyStreamConfigEntry
from .coordinator import SunologyStreamDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunologyStreamConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sunology Stream binary sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator

    if coordinator.data.erl:
        async_add_entities([SunologyStreamErlConnectedBinarySensor(coordinator, entry.entry_id)])


class SunologyStreamErlConnectedBinarySensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], BinarySensorEntity
):
    """Whether the ERL (Linky TIC reader) is connected/synchronizing."""

    _attr_has_entity_name = True
    _attr_translation_key = "erl_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self, coordinator: SunologyStreamDataUpdateCoordinator, entry_id: str
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_erl_connected"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data.erl:
            return None
        return bool(self.coordinator.data.erl.get("state"))
