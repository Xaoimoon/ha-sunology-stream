"""Tests for how entities are grouped into devices."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.sunology_stream import binary_sensor, sensor
from custom_components.sunology_stream.const import DOMAIN
from custom_components.sunology_stream.coordinator import SunologyStreamData
from custom_components.sunology_stream.entity import (
    erl_device_info,
    installation_device_info,
    panel_device_info,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "sunology_stream"


def load_fixture(name: str):
    return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def make_data(**overrides) -> SunologyStreamData:
    data = dict(
        client=load_fixture("client"),
        overview=load_fixture("overview"),
        history_daily=load_fixture("history-daily"),
        erl=load_fixture("erl"),
        stream_meters=[],
        storage_batteries=[],
        contract=load_fixture("client-signed-contract"),
        day_energy=load_fixture("energy-amounts-and-costs-for-day"),
        panel_details={
            "AAAAAAAAAAAA": load_fixture("solar-panel"),
            "BBBBBBBBBBBB": {**load_fixture("solar-panel"), "serialNumber": "BBBBBBBBBBBB"},
        },
    )
    data.update(overrides)
    return SunologyStreamData(**data)


async def setup_platform(platform, data: SunologyStreamData) -> dict:
    """Run a platform's async_setup_entry and index the entities by unique_id."""
    entry = MagicMock()
    entry.entry_id = "entry"
    entry.runtime_data.coordinator.data = data
    entities = []
    await platform.async_setup_entry(MagicMock(), entry, entities.extend)
    return {entity.unique_id: entity for entity in entities}


def device_id(entity) -> str:
    (identifier,) = entity.device_info["identifiers"]
    assert identifier[0] == DOMAIN
    return identifier[1]


def test_installation_device():
    info = installation_device_info("entry")
    assert info["identifiers"] == {(DOMAIN, "entry")}
    assert info["translation_key"] == "installation"
    assert info["entry_type"] == "service"


def test_erl_device():
    info = erl_device_info("entry", load_fixture("erl"))
    assert info["identifiers"] == {(DOMAIN, "000000000000")}
    assert info["model"] == "ERL"
    assert info["serial_number"] == "000000000000"
    assert info["via_device"] == (DOMAIN, "entry")


def test_erl_device_without_serial_number():
    assert erl_device_info("entry", {})["identifiers"] == {(DOMAIN, "entry_erl")}


def test_panel_device():
    info = panel_device_info(
        "entry",
        "AAAAAAAAAAAA",
        {"surname": "Sunology 1", "panelType": "PLAY_MAX"},
        load_fixture("solar-panel"),
    )
    assert info["identifiers"] == {(DOMAIN, "AAAAAAAAAAAA")}
    assert info["name"] == "Sunology 1"
    assert info["model"] == "PLAY_MAX"
    assert info["sw_version"] == "202624.2"
    assert info["via_device"] == (DOMAIN, "entry")


def test_panel_device_without_details_or_surname():
    info = panel_device_info("entry", "AAAAAAAAAAAA", {}, None)
    assert info["name"] == "AAAAAAAAAAAA"
    assert info["sw_version"] is None


@pytest.mark.asyncio
async def test_sensors_are_grouped_by_device():
    entities = await setup_platform(sensor, make_data())
    by_device: dict[str, set[str]] = {}
    for unique_id, entity in entities.items():
        by_device.setdefault(device_id(entity), set()).add(unique_id.removeprefix("entry_"))

    assert by_device == {
        "entry": {"production_power", "daily_production_energy", "self_reliance"},
        "000000000000": {
            "consumption_power",
            "grid_purchased_power",
            "daily_consumption_energy",
            "erl_last_synchronization",
            "daily_consumption_cost",
            "daily_off_peak_consumption_energy",
            "daily_peak_consumption_energy",
            "daily_off_peak_consumption_cost",
            "daily_peak_consumption_cost",
        },
        # Sunology 1 has a battery: it also gets the charge threshold.
        "AAAAAAAAAAAA": {
            f"panel_AAAAAAAAAAAA_{key}"
            for key in (
                "production",
                "battery_level",
                "battery_state",
                "wifi_signal",
                "firmware_version",
                "last_synchronization",
                "battery_charge_threshold",
            )
        },
        "BBBBBBBBBBBB": {
            f"panel_BBBBBBBBBBBB_{key}"
            for key in (
                "production",
                "battery_level",
                "battery_state",
                "wifi_signal",
                "firmware_version",
                "last_synchronization",
            )
        },
    }


@pytest.mark.asyncio
async def test_grid_sensors_fall_back_to_installation_without_erl():
    entities = await setup_platform(sensor, make_data(erl=None))
    assert device_id(entities["entry_consumption_power"]) == "entry"
    assert "entry_erl_last_synchronization" not in entities


@pytest.mark.asyncio
async def test_binary_sensors_are_grouped_by_device():
    entities = await setup_platform(binary_sensor, make_data())
    assert {uid: device_id(e) for uid, e in entities.items()} == {
        "entry_erl_connected": "000000000000",
        "entry_panel_AAAAAAAAAAAA_battery_preserve_energy": "AAAAAAAAAAAA",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", [sensor, binary_sensor])
async def test_every_entity_has_a_translated_name(platform):
    entities = await setup_platform(platform, make_data())
    domain = platform.__name__.rsplit(".", 1)[-1]
    for path in ("strings.json", "translations/en.json", "translations/fr.json"):
        strings = json.loads((COMPONENT_DIR / path).read_text(encoding="utf-8"))
        for entity in entities.values():
            assert entity.has_entity_name
            key = entity.translation_key
            assert key in strings["entity"][domain], (path, key)
        for device_key in ("installation", "erl"):
            assert device_key in strings["device"], (path, device_key)
