"""Tests for the pure data-extraction logic used by sensor entities.

These use anonymized real API captures (tests/fixtures/) rather than
hand-written data, so they double as a guard against the extraction paths
silently drifting out of sync with the actual (undocumented) API shape.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.sunology_stream.coordinator import SunologyStreamData
from custom_components.sunology_stream.sensor import (
    DAILY_CONSUMPTION_COST_DESCRIPTION,
    ERL_LAST_SYNC_DESCRIPTION,
    OFF_PEAK_DESCRIPTIONS,
    SENSOR_DESCRIPTIONS,
    _off_peak_ranges,
)
from homeassistant.util import dt as dt_util

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def sample_data() -> SunologyStreamData:
    return SunologyStreamData(
        client=load_fixture("client"),
        overview=load_fixture("overview"),
        history_daily=load_fixture("history-daily"),
        erl=load_fixture("erl"),
        stream_meters=[],
        storage_batteries=[],
        contract=load_fixture("client-signed-contract"),
        day_energy=load_fixture("energy-amounts-and-costs-for-day"),
    )


@pytest.fixture
def paris_time_zone():
    """The day-energy fixture was captured for 2026-09-26 in Europe/Paris."""
    previous = dt_util.get_default_time_zone()
    dt_util.set_default_time_zone(dt_util.get_time_zone("Europe/Paris"))
    yield
    dt_util.set_default_time_zone(previous)


def get_description(key: str):
    return next(d for d in SENSOR_DESCRIPTIONS if d.key == key)


def test_production_power(sample_data: SunologyStreamData):
    assert get_description("production_power").value_fn(sample_data) == 0


def test_consumption_power(sample_data: SunologyStreamData):
    assert get_description("consumption_power").value_fn(sample_data) == 4088.0


def test_grid_purchased_power(sample_data: SunologyStreamData):
    assert get_description("grid_purchased_power").value_fn(sample_data) == 4088.0


def test_daily_production_energy(sample_data: SunologyStreamData):
    assert get_description("daily_production_energy").value_fn(sample_data) == 21287


def test_daily_consumption_energy(sample_data: SunologyStreamData):
    assert get_description("daily_consumption_energy").value_fn(sample_data) == 38562


def test_self_reliance(sample_data: SunologyStreamData):
    assert get_description("self_reliance").value_fn(sample_data) == 36.0


def test_erl_last_synchronization(sample_data: SunologyStreamData):
    value = ERL_LAST_SYNC_DESCRIPTION.value_fn(sample_data)
    assert isinstance(value, datetime)
    assert value.year == 2026


def test_erl_last_synchronization_missing_erl():
    data = SunologyStreamData(
        client=load_fixture("client"),
        overview=load_fixture("overview"),
        history_daily=load_fixture("history-daily"),
        erl=None,
        stream_meters=[],
        storage_batteries=[],
    )
    assert ERL_LAST_SYNC_DESCRIPTION.value_fn(data) is None


def test_panel_production_values(sample_data: SunologyStreamData):
    panels = sample_data.overview["production"]["panels"]
    assert set(panels.keys()) == {"AAAAAAAAAAAA", "BBBBBBBBBBBB"}
    assert panels["AAAAAAAAAAAA"]["production"] == 0
    assert panels["AAAAAAAAAAAA"]["surname"] == "Sunology 1"


def test_panel_battery_values(sample_data: SunologyStreamData):
    panels = sample_data.overview["production"]["panels"]
    assert panels["AAAAAAAAAAAA"]["battery"] == 2
    assert panels["AAAAAAAAAAAA"]["batteryState"] == "DISCHARGING"
    assert panels["BBBBBBBBBBBB"]["battery"] == 0
    assert panels["BBBBBBBBBBBB"]["batteryState"] == "UNPLUGGED"


def get_off_peak_description(key: str):
    return next(d for d in OFF_PEAK_DESCRIPTIONS if d.key == key)


def test_off_peak_ranges_split_at_midnight(sample_data: SunologyStreamData):
    assert _off_peak_ranges(sample_data.contract) == [(22 * 60 + 56, 24 * 60), (0, 6 * 60 + 56)]


def test_off_peak_ranges_without_contract():
    assert _off_peak_ranges(None) == []
    assert _off_peak_ranges({"config": {"option_name": "Base"}}) == []


@pytest.mark.usefixtures("paris_time_zone")
def test_daily_off_peak_and_peak_consumption(sample_data: SunologyStreamData):
    # Checked against the Enedis load curve for that day: 14.2 / 31.8 kWh.
    # 06:00-07:00 and 22:00-23:00 straddle 06:56/22:56 and are split pro rata.
    off_peak = get_off_peak_description("daily_off_peak_consumption_energy")
    peak = get_off_peak_description("daily_peak_consumption_energy")
    assert off_peak.value_fn(sample_data) == pytest.approx(14.219, abs=0.001)
    assert peak.value_fn(sample_data) == pytest.approx(31.781, abs=0.001)


def test_daily_off_peak_consumption_without_contract(sample_data: SunologyStreamData):
    sample_data.contract = None
    off_peak = get_off_peak_description("daily_off_peak_consumption_energy")
    assert off_peak.value_fn(sample_data) is None


def test_daily_off_peak_consumption_before_first_hour(sample_data: SunologyStreamData):
    sample_data.day_energy = {"energyAmountsAndCostsByHour": {}}
    off_peak = get_off_peak_description("daily_off_peak_consumption_energy")
    assert off_peak.value_fn(sample_data) == 0


def test_daily_consumption_cost(sample_data: SunologyStreamData):
    assert DAILY_CONSUMPTION_COST_DESCRIPTION.value_fn(sample_data) == pytest.approx(8.95)


def test_daily_consumption_cost_without_day_energy(sample_data: SunologyStreamData):
    sample_data.day_energy = None
    assert DAILY_CONSUMPTION_COST_DESCRIPTION.value_fn(sample_data) is None
