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
    CONTRACT_DESCRIPTIONS,
    PANEL_DETAIL_DESCRIPTIONS,
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
        panel_details={"AAAAAAAAAAAA": load_fixture("solar-panel")},
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


def get_panel_detail_description(key: str):
    return next(d for d in PANEL_DETAIL_DESCRIPTIONS if d.key == key)


def test_panel_details_values(sample_data: SunologyStreamData):
    details = sample_data.panel_details["AAAAAAAAAAAA"]
    assert get_panel_detail_description("wifi_signal").value_fn(details) == -75.0
    assert get_panel_detail_description("firmware_version").value_fn(details) == "202624.2"
    assert get_panel_detail_description("battery_charge_threshold").value_fn(details) == 210
    synced = get_panel_detail_description("last_synchronization").value_fn(details)
    assert synced == datetime(2026, 9, 29, 22, 54, 33, tzinfo=dt_util.UTC)


def test_panel_details_missing_values():
    assert get_panel_detail_description("wifi_signal").value_fn({}) is None
    assert get_panel_detail_description("last_synchronization").value_fn({}) is None


def test_only_battery_threshold_requires_a_battery():
    assert [d.key for d in PANEL_DETAIL_DESCRIPTIONS if d.requires_battery] == [
        "battery_charge_threshold"
    ]


@pytest.mark.usefixtures("paris_time_zone")
def test_daily_off_peak_and_peak_consumption_cost(sample_data: SunologyStreamData):
    off_peak = get_off_peak_description("daily_off_peak_consumption_cost")
    peak = get_off_peak_description("daily_peak_consumption_cost")
    off_peak_cost = off_peak.value_fn(sample_data)
    peak_cost = peak.value_fn(sample_data)
    # ~14.219 kWh x 0.16 and ~31.781 kWh x 0.21 (API prices on that day).
    assert off_peak_cost == pytest.approx(2.27, abs=0.01)
    assert peak_cost == pytest.approx(6.68, abs=0.01)
    # The split adds up to the day's total.
    assert off_peak_cost + peak_cost == pytest.approx(
        DAILY_CONSUMPTION_COST_DESCRIPTION.value_fn(sample_data), abs=0.01
    )


def test_daily_off_peak_consumption_cost_without_contract(sample_data: SunologyStreamData):
    sample_data.contract = None
    off_peak = get_off_peak_description("daily_off_peak_consumption_cost")
    assert off_peak.value_fn(sample_data) is None
    # The total cost doesn't need the contract.
    assert DAILY_CONSUMPTION_COST_DESCRIPTION.value_fn(sample_data) == pytest.approx(8.95)


def test_cost_sensors_are_daily_totals():
    costs = [
        DAILY_CONSUMPTION_COST_DESCRIPTION,
        get_off_peak_description("daily_off_peak_consumption_cost"),
        get_off_peak_description("daily_peak_consumption_cost"),
    ]
    for description in costs:
        assert description.state_class == "total"
        assert description.resets_daily


def test_cost_last_reset_follows_the_published_day(sample_data: SunologyStreamData):
    from unittest.mock import MagicMock

    from custom_components.sunology_stream.sensor import SunologyStreamSensor

    yesterday = datetime(2026, 9, 26, tzinfo=dt_util.get_time_zone("Europe/Paris"))
    sample_data.day_energy_start = yesterday
    coordinator = MagicMock()
    coordinator.data = sample_data

    device = MagicMock()
    cost = SunologyStreamSensor(
        coordinator, "entry", DAILY_CONSUMPTION_COST_DESCRIPTION, device
    )
    power = SunologyStreamSensor(
        coordinator, "entry", get_description("consumption_power"), device
    )

    assert cost.last_reset == yesterday
    assert power.last_reset is None


def contract_value(key: str, data: SunologyStreamData):
    return next(d for d in CONTRACT_DESCRIPTIONS if d.key == key).value_fn(data)


def test_contract_values(sample_data: SunologyStreamData):
    assert contract_value("contract_pdl", sample_data) == "00000000000000"
    assert contract_value("contract_offer", sample_data) == "Tarif bleu résidentiel"
    assert contract_value("contract_option", sample_data) == "Heures pleines heures creuses"
    assert contract_value("contract_subscribed_power", sample_data) == 9.0
    assert contract_value("contract_off_peak_hours", sample_data) == "22:56-06:56"
    assert contract_value("contract_provider", sample_data) == "EDF"
    assert contract_value("contract_distributor", sample_data) == "Enedis"


def test_contract_values_without_contract(sample_data: SunologyStreamData):
    sample_data.contract = None
    for description in CONTRACT_DESCRIPTIONS:
        assert description.value_fn(sample_data) is None, description.key


def test_contract_labels_fall_back_to_the_selectra_options(sample_data: SunologyStreamData):
    config = sample_data.contract["config"]
    del config["offer_name"], config["option_name"]
    assert contract_value("contract_offer", sample_data) == "Tarif bleu résidentiel"
    assert contract_value("contract_option", sample_data) == "Heures pleines heures creuses"


@pytest.mark.parametrize(
    ("ranges", "expected"),
    [
        ([{"start": "22:56", "end": "00:00"}, {"start": "00:00", "end": "06:56"}], "22:56-06:56"),
        ([{"start": "22:00", "end": "06:00"}], "22:00-06:00"),
        ([{"start": "02:00", "end": "07:00"}, {"start": "13:00", "end": "16:00"}], "02:00-07:00, 13:00-16:00"),
    ],
)
def test_contract_off_peak_hours_formatting(sample_data: SunologyStreamData, ranges, expected):
    sample_data.contract["config"]["off_peak_hours"] = ranges
    assert contract_value("contract_off_peak_hours", sample_data) == expected
