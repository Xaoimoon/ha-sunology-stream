"""The Sunology Stream integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry

from .api import (
    SunologyStreamApiClient,
    SunologyStreamAuthError,
    SunologyStreamConnectionError,
)
from .const import DOMAIN
from .coordinator import SunologyStreamDataUpdateCoordinator
from .entity import installation_device_info, live_device_identifiers

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


@dataclass
class SunologyStreamRuntimeData:
    """Data stored on the config entry at runtime."""

    api: SunologyStreamApiClient
    coordinator: SunologyStreamDataUpdateCoordinator
    # Device registry id of the installation device, which the ERL and the
    # panels link to (`via_device_id`).
    installation_device_id: str


type SunologyStreamConfigEntry = ConfigEntry[SunologyStreamRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: SunologyStreamConfigEntry) -> bool:
    """Set up Sunology Stream from a config entry."""
    api = SunologyStreamApiClient(
        entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )

    try:
        await api.login()
    except SunologyStreamAuthError as err:
        await api.close()
        raise ConfigEntryAuthFailed("Invalid Sunology Stream credentials") from err
    except SunologyStreamConnectionError as err:
        await api.close()
        raise ConfigEntryNotReady(f"Cannot reach Sunology Stream API: {err}") from err

    coordinator = SunologyStreamDataUpdateCoordinator(hass, entry, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await api.close()
        raise

    # Registered before the platforms: the ERL and panel devices need its id.
    installation = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **installation_device_info(entry.entry_id)
    )

    entry.runtime_data = SunologyStreamRuntimeData(
        api=api, coordinator=coordinator, installation_device_id=installation.id
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SunologyStreamConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.api.close()
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: SunologyStreamConfigEntry, device_entry: DeviceEntry
) -> bool:
    """Allow removing a device only once it's gone from the account, e.g. a
    panel removed in the Sunology app. Current devices would come back anyway.
    """
    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is None:
        # Entry not loaded: only protect the installation device.
        live = {entry.entry_id}
    else:
        live = live_device_identifiers(entry.entry_id, runtime_data.coordinator.data)
    return not any(
        domain == DOMAIN and identifier in live
        for domain, identifier in device_entry.identifiers
    )
