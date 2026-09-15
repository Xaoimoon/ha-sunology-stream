"""Tests for the DataUpdateCoordinator's flag-gating and error mapping."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sunology_stream.api import (
    SunologyStreamAuthError,
    SunologyStreamConnectionError,
)
from custom_components.sunology_stream.coordinator import (
    SunologyStreamDataUpdateCoordinator,
)


def make_coordinator(api: AsyncMock) -> SunologyStreamDataUpdateCoordinator:
    hass = MagicMock()
    config_entry = MagicMock()
    return SunologyStreamDataUpdateCoordinator(hass, config_entry, api)


@pytest.mark.asyncio
async def test_skips_optional_endpoints_when_flags_are_false():
    api = AsyncMock()
    api.get_client.return_value = {
        "hasErl": False,
        "hasGridStreamMeter": False,
        "hasStorageBattery": False,
    }
    api.get_overview.return_value = {"production": {}, "consumptionData": {}}
    api.get_history_daily.return_value = {}

    coordinator = make_coordinator(api)
    data = await coordinator._async_update_data()

    api.get_erl.assert_not_called()
    api.get_stream_meter.assert_not_called()
    api.get_storage_battery_all_paired.assert_not_called()
    assert data.erl is None
    assert data.stream_meters == []
    assert data.storage_batteries == []


@pytest.mark.asyncio
async def test_fetches_optional_endpoints_when_flags_are_true():
    api = AsyncMock()
    api.get_client.return_value = {
        "hasErl": True,
        "hasGridStreamMeter": True,
        "hasStorageBattery": True,
    }
    api.get_overview.return_value = {"production": {}, "consumptionData": {}}
    api.get_history_daily.return_value = {}
    api.get_erl.return_value = {"state": True}
    api.get_stream_meter.return_value = [{"id": 1}]
    api.get_storage_battery_all_paired.return_value = [{"id": 2}]

    coordinator = make_coordinator(api)
    data = await coordinator._async_update_data()

    api.get_erl.assert_awaited_once()
    api.get_stream_meter.assert_awaited_once()
    api.get_storage_battery_all_paired.assert_awaited_once()
    assert data.erl == {"state": True}
    assert data.stream_meters == [{"id": 1}]
    assert data.storage_batteries == [{"id": 2}]


@pytest.mark.asyncio
async def test_auth_error_becomes_config_entry_auth_failed():
    api = AsyncMock()
    api.get_client.side_effect = SunologyStreamAuthError("expired")

    coordinator = make_coordinator(api)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_connection_error_becomes_update_failed():
    api = AsyncMock()
    api.get_client.side_effect = SunologyStreamConnectionError("unreachable")

    coordinator = make_coordinator(api)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
