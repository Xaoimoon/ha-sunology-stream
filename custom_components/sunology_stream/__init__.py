"""The Sunology Stream integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import (
    SunologyStreamApiClient,
    SunologyStreamAuthError,
    SunologyStreamConnectionError,
)
from .coordinator import SunologyStreamDataUpdateCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


@dataclass
class SunologyStreamRuntimeData:
    """Data stored on the config entry at runtime."""

    api: SunologyStreamApiClient
    coordinator: SunologyStreamDataUpdateCoordinator


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

    coordinator = SunologyStreamDataUpdateCoordinator(hass, api)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await api.close()
        raise

    entry.runtime_data = SunologyStreamRuntimeData(api=api, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SunologyStreamConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.api.close()
    return unloaded
