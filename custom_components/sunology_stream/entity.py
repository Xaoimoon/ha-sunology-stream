"""Devices of the Sunology Stream integration.

Entities are grouped into three kinds of devices:
- the installation (one per account), a service device;
- the ERL (Linky TIC reader), when the account has one;
- one device per solar panel.
The ERL and the panels are linked to the installation via `via_device`.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN

MANUFACTURER = "Sunology"


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
    serial_number = erl.get("serialNumber")
    return DeviceInfo(
        identifiers={(DOMAIN, serial_number or f"{entry_id}_erl")},
        translation_key="erl",
        manufacturer=MANUFACTURER,
        model=erl.get("erlType") or "ERL",
        serial_number=serial_number,
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

    The firmware version is only read at setup: a firmware update shows up
    on the device page after a reload (the firmware sensor is always live).
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
