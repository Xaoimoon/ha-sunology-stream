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
    ERL_LAST_SYNC_DESCRIPTION,
    SENSOR_DESCRIPTIONS,
)

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
    )


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
