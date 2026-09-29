"""Tests for the DataUpdateCoordinator's flag-gating and error mapping."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sunology_stream.api import (
    SunologyStreamApiError,
    SunologyStreamAuthError,
    SunologyStreamConnectionError,
)
from custom_components.sunology_stream.coordinator import (
    SunologyStreamDataUpdateCoordinator,
    day_param,
    zone_param,
)
from homeassistant.util import dt as dt_util


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


def test_zone_param_is_offset_in_hours():
    assert zone_param(datetime(2026, 9, 26, 12, tzinfo=timezone(timedelta(hours=2)))) == "2"
    assert zone_param(datetime(2026, 1, 26, 12, tzinfo=timezone(timedelta(hours=1)))) == "1"
    assert zone_param(datetime(2026, 1, 26, 12, tzinfo=timezone.utc)) == "0"
    assert zone_param(datetime(2026, 1, 26, 12, tzinfo=timezone(timedelta(hours=5, minutes=30)))) == "5.5"


def test_day_param_is_local_midnight_in_utc():
    paris = dt_util.get_time_zone("Europe/Paris")
    assert day_param(datetime(2026, 9, 26, 15, 30, tzinfo=paris)) == "2026-09-25T22:00:00.000Z"
    assert day_param(datetime(2026, 1, 26, 0, 10, tzinfo=paris)) == "2026-01-25T23:00:00.000Z"


def make_erl_api() -> AsyncMock:
    api = AsyncMock()
    api.get_client.return_value = {"hasErl": True}
    api.get_overview.return_value = {"production": {}, "consumptionData": {}}
    api.get_history_daily.return_value = {}
    api.get_erl.return_value = {"state": True}
    api.get_signed_contract.return_value = {"config": {"off_peak_hours": []}}
    api.get_energy_amounts_and_costs_for_day.return_value = {"energyAmountsAndCostsByHour": {}}
    return api


@pytest.mark.asyncio
async def test_history_uses_hour_offset_zone():
    api = make_erl_api()
    now = datetime(2026, 9, 26, 15, 30, tzinfo=dt_util.get_time_zone("Europe/Paris"))

    with patch.object(dt_util, "now", return_value=now):
        await make_coordinator(api)._async_update_data()

    api.get_history_daily.assert_awaited_once_with("2026-09-26", "2")
    api.get_energy_amounts_and_costs_for_day.assert_awaited_once_with(
        "2026-09-25T22:00:00.000Z", "2"
    )


@pytest.mark.asyncio
async def test_slow_data_is_throttled_until_interval_or_day_change():
    api = make_erl_api()
    coordinator = make_coordinator(api)
    paris = dt_util.get_time_zone("Europe/Paris")

    for now in (
        datetime(2026, 9, 26, 23, 50, tzinfo=paris),
        datetime(2026, 9, 26, 23, 51, tzinfo=paris),  # throttled
        datetime(2026, 9, 27, 0, 0, 30, tzinfo=paris),  # new day: refreshed
        datetime(2026, 9, 27, 0, 6, tzinfo=paris),  # interval elapsed
    ):
        with patch.object(dt_util, "now", return_value=now):
            data = await coordinator._async_update_data()

    assert api.get_signed_contract.await_count == 3
    assert api.get_energy_amounts_and_costs_for_day.await_count == 3
    assert data.day_energy == {"energyAmountsAndCostsByHour": {}}


@pytest.mark.asyncio
async def test_slow_data_failure_does_not_fail_update():
    api = make_erl_api()
    api.get_signed_contract.side_effect = SunologyStreamApiError("500")
    api.get_energy_amounts_and_costs_for_day.side_effect = SunologyStreamApiError("500")

    data = await make_coordinator(api)._async_update_data()

    assert data.erl == {"state": True}
    assert data.contract is None
    assert data.day_energy is None


@pytest.mark.asyncio
async def test_slow_data_skips_day_energy_without_erl():
    api = make_erl_api()
    api.get_client.return_value = {"hasErl": False}

    data = await make_coordinator(api)._async_update_data()

    api.get_energy_amounts_and_costs_for_day.assert_not_called()
    assert data.day_energy is None
