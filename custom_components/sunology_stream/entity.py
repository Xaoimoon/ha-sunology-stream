"""Devices of the Sunology Stream integration.

Entities are grouped into three kinds of devices:
- the installation (one per account), a service device;
- the ERL (Linky TIC reader), when the account has one;
- one device per solar panel.
The ERL and the panels are linked to the installation via `via_device`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SunologyStreamData, SunologyStreamDataUpdateCoordinator

MANUFACTURER = "Sunology"


def overview_panels(data: SunologyStreamData) -> dict[str, dict[str, Any]]:
    """The panels currently on the account, keyed by serial number."""
    return data.overview.get("production", {}).get("panels", {}) or {}


def erl_identifier(entry_id: str, erl: dict[str, Any]) -> str:
    return erl.get("serialNumber") or f"{entry_id}_erl"


def live_device_identifiers(entry_id: str, data: SunologyStreamData) -> set[str]:
    """Identifiers of the devices the account currently has."""
    identifiers = {entry_id, *overview_panels(data)}
    if data.erl:
        identifiers.add(erl_identifier(entry_id, data.erl))
    return identifiers


def installation_device_info(entry_id: str) -> DeviceInfo:
    """The account-level device, for installation-wide sensors."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        translation_key="installation",
        manufacturer=MANUFACTURER,
        entry_type=DeviceEntryType.SERVICE,
    )


def erl_device_info(entry_id: str, erl: dict[str, Any]) -> DeviceInfo:
    """The ERL (Linky TIC reader), for grid consumption sensors."""
    return DeviceInfo(
        identifiers={(DOMAIN, erl_identifier(entry_id, erl))},
        translation_key="erl",
        manufacturer=MANUFACTURER,
        model=erl.get("erlType") or "ERL",
        serial_number=erl.get("serialNumber"),
        sw_version=erl.get("firmwareVersion"),
        via_device=(DOMAIN, entry_id),
    )


def panel_device_info(
    entry_id: str,
    serial_number: str,
    panel_data: dict[str, Any],
    details: dict[str, Any] | None,
) -> DeviceInfo:
    """One solar panel, keyed by its serial number.

    The firmware version is only read when the panel's entities are created:
    a firmware update shows up on the device page after a reload (the
    firmware sensor is always live).
    """
    return DeviceInfo(
        identifiers={(DOMAIN, serial_number)},
        name=panel_data.get("surname") or serial_number,
        manufacturer=MANUFACTURER,
        model=panel_data.get("panelType"),
        serial_number=serial_number,
        sw_version=(details or {}).get("firmwareVersion"),
        via_device=(DOMAIN, entry_id),
    )


class SunologyStreamPanelEntity(CoordinatorEntity[SunologyStreamDataUpdateCoordinator]):
    """Base for the entities of one solar panel.

    Unavailable once the panel is gone from the account, until its device is
    removed from Home Assistant.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        device_info: DeviceInfo,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._serial_number = serial_number
        self._attr_unique_id = f"{entry_id}_panel_{serial_number}_{key}"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        return super().available and self._serial_number in overview_panels(
            self.coordinator.data
        )

    @property
    def panel_data(self) -> dict[str, Any]:
        return overview_panels(self.coordinator.data).get(self._serial_number, {})

    @property
    def panel_details(self) -> dict[str, Any] | None:
        return self.coordinator.data.panel_details.get(self._serial_number)


def async_track_panels(
    entry: ConfigEntry,
    coordinator: SunologyStreamDataUpdateCoordinator,
    async_add_entities: Callable[[list[Entity]], None],
    build_panel_entities: Callable[[str, dict[str, Any], DeviceInfo], list[Entity]],
    build_detail_entities: Callable[
        [str, dict[str, Any], dict[str, Any], DeviceInfo], list[Entity]
    ],
) -> None:
    """Add the entities of each panel, including panels added to the account
    after setup, without reloading the config entry.

    A new panel gets its overview-based entities as soon as it shows up, and
    its /solar-panels/{id} based ones once its details have been fetched.
    """
    with_entities: set[str] = set()
    with_detail_entities: set[str] = set()

    @callback
    def add_new_panels() -> None:
        data = coordinator.data
        new_entities: list[Entity] = []
        for serial_number, panel_data in overview_panels(data).items():
            details = data.panel_details.get(serial_number)
            device = panel_device_info(entry.entry_id, serial_number, panel_data, details)
            if serial_number not in with_entities:
                with_entities.add(serial_number)
                new_entities.extend(build_panel_entities(serial_number, panel_data, device))
            if details is not None and serial_number not in with_detail_entities:
                with_detail_entities.add(serial_number)
                new_entities.extend(
                    build_detail_entities(serial_number, panel_data, details, device)
                )
        if new_entities:
            async_add_entities(new_entities)

    add_new_panels()
    entry.async_on_unload(coordinator.async_add_listener(add_new_panels))
