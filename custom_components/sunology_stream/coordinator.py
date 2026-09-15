"""DataUpdateCoordinator for the Sunology Stream integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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


class SunologyStreamDataUpdateCoordinator(DataUpdateCoordinator[SunologyStreamData]):
    """Coordinates polling of the Sunology Stream cloud API."""

    def __init__(self, hass: HomeAssistant, api: SunologyStreamApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> SunologyStreamData:
        try:
            client = await self.api.get_client()
            overview = await self.api.get_overview()
        except SunologyStreamAuthError as err:
            raise ConfigEntryAuthFailed("Session expired and re-login failed") from err
        except SunologyStreamConnectionError as err:
            raise UpdateFailed(f"Cannot reach Sunology Stream API: {err}") from err

        return SunologyStreamData(client=client, overview=overview)
