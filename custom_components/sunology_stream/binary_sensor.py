"""Binary sensor platform for the Sunology Stream integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SunologyStreamConfigEntry
from .coordinator import SunologyStreamDataUpdateCoordinator
from .entity import SunologyStreamPanelEntity, async_track_panels, erl_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunologyStreamConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sunology Stream binary sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator

    entities: list[BinarySensorEntity] = []
    if coordinator.data.erl:
        entities.append(
            SunologyStreamErlConnectedBinarySensor(
                coordinator,
                entry.entry_id,
                erl_device_info(
                    entry.entry_id,
                    coordinator.data.erl,
                    entry.runtime_data.installation_device_id,
                ),
            )
        )

    async_add_entities(entities)

    def build_detail_entities(
        serial_number: str,
        panel_data: dict[str, Any],
        details: dict[str, Any],
        device: DeviceInfo,
    ) -> list[BinarySensorEntity]:
        if not panel_data.get("has_b"):
            return []
        return [
            SunologyStreamPanelBatteryPreserveBinarySensor(
                coordinator, entry.entry_id, serial_number, device
            )
        ]

    async_track_panels(
        entry, coordinator, async_add_entities, lambda *_: [], build_detail_entities
    )


class SunologyStreamErlConnectedBinarySensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], BinarySensorEntity
):
    """Whether the ERL (Linky TIC reader) is connected/synchronizing."""

    _attr_has_entity_name = True
    _attr_translation_key = "erl_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_erl_connected"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data.erl:
            return None
        return bool(self.coordinator.data.erl.get("state"))


class SunologyStreamPanelBatteryPreserveBinarySensor(
    SunologyStreamPanelEntity, BinarySensorEntity
):
    """Whether a panel's battery is set to hold its charge (the app's "nomad"
    option, which blocks discharging for 18 hours).
    """

    _attr_translation_key = "panel_battery_preserve_energy"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(
            coordinator, entry_id, serial_number, device_info, "battery_preserve_energy"
        )

    @property
    def is_on(self) -> bool | None:
        details = self.panel_details
        if details is None or details.get("batteryPreserveEnergy") is None:
            return None
        return bool(details["batteryPreserveEnergy"])
