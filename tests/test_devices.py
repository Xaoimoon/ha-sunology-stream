"""Tests for how entities are grouped into devices."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_components.sunology_stream import (
    async_remove_config_entry_device,
    binary_sensor,
    sensor,
)
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
        tariff_details=load_fixture("selectra-details"),
        tariff_prices=load_fixture("selectra-prices"),
        panel_details={
            "AAAAAAAAAAAA": load_fixture("solar-panel"),
            "BBBBBBBBBBBB": {**load_fixture("solar-panel"), "serialNumber": "BBBBBBBBBBBB"},
        },
    )
    data.update(overrides)
    return SunologyStreamData(**data)


class FakePlatform:
    """Runs a platform's async_setup_entry and records what it adds."""

    def __init__(self, platform, data: SunologyStreamData) -> None:
        self.platform = platform
        self.entry = MagicMock()
        self.entry.entry_id = "entry"
        self.coordinator = self.entry.runtime_data.coordinator
        self.coordinator.data = data
        self.coordinator.last_update_success = True
        self.batches: list[list] = []

    async def setup(self) -> dict:
        await self.platform.async_setup_entry(MagicMock(), self.entry, self.batches.append)
        return self.entities

    @property
    def entities(self) -> dict:
        return {entity.unique_id: entity for batch in self.batches for entity in batch}

    def refresh(self, data: SunologyStreamData) -> list:
        """Simulate a coordinator update; return the entities it added."""
        self.coordinator.data = data
        before = len(self.batches)
        (listener,) = [c.args[0] for c in self.coordinator.async_add_listener.call_args_list]
        listener()
        return [entity for batch in self.batches[before:] for entity in batch]


async def setup_platform(platform, data: SunologyStreamData) -> dict:
    return await FakePlatform(platform, data).setup()


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
            "contract_pdl",
            "contract_offer",
            "contract_option",
            "contract_subscribed_power",
            "contract_off_peak_hours",
            "contract_provider",
            "contract_distributor",
            "contract_off_peak_price",
            "contract_peak_price",
            "current_price",
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


def with_panel_c(data: SunologyStreamData, with_details: bool) -> SunologyStreamData:
    """The same account after adding a third panel (with a battery)."""
    overview = json.loads(json.dumps(data.overview))
    overview["production"]["panels"]["CCCCCCCCCCCC"] = {
        "surname": "Sunology 3",
        "production": 120,
        "battery": 50,
        "has_b": True,
        "panelType": "PLAY_MAX",
    }
    details = dict(data.panel_details)
    if with_details:
        details["CCCCCCCCCCCC"] = {**load_fixture("solar-panel"), "rssiWifi": -50.0}
    return make_data(overview=overview, panel_details=details)


@pytest.mark.asyncio
async def test_new_panel_entities_are_added_without_reload():
    fake = FakePlatform(sensor, make_data())
    await fake.setup()
    count = len(fake.entities)

    # The panel shows up in the overview first: its overview-based entities.
    added = fake.refresh(with_panel_c(make_data(), with_details=False))
    assert {e.unique_id for e in added} == {
        "entry_panel_CCCCCCCCCCCC_production",
        "entry_panel_CCCCCCCCCCCC_battery_level",
        "entry_panel_CCCCCCCCCCCC_battery_state",
    }
    assert added[0].device_info["name"] == "Sunology 3"
    assert added[0].native_value == 120

    # Its details come with the next slow refresh: the diagnostics.
    added = fake.refresh(with_panel_c(make_data(), with_details=True))
    assert {e.unique_id for e in added} == {
        f"entry_panel_CCCCCCCCCCCC_{key}"
        for key in (
            "wifi_signal",
            "firmware_version",
            "last_synchronization",
            "battery_charge_threshold",
        )
    }
    assert fake.entities["entry_panel_CCCCCCCCCCCC_wifi_signal"].native_value == -50.0

    # Nothing is added twice.
    assert fake.refresh(with_panel_c(make_data(), with_details=True)) == []
    assert len(fake.entities) == count + 7


@pytest.mark.asyncio
async def test_new_panel_binary_sensor_is_added_without_reload():
    fake = FakePlatform(binary_sensor, make_data())
    await fake.setup()
    assert fake.refresh(with_panel_c(make_data(), with_details=False)) == []
    added = fake.refresh(with_panel_c(make_data(), with_details=True))
    assert [e.unique_id for e in added] == [
        "entry_panel_CCCCCCCCCCCC_battery_preserve_energy"
    ]


@pytest.mark.asyncio
async def test_removed_panel_entities_become_unavailable():
    fake = FakePlatform(sensor, make_data())
    entities = await fake.setup()
    production = entities["entry_panel_AAAAAAAAAAAA_production"]
    assert production.available

    overview = json.loads(json.dumps(fake.coordinator.data.overview))
    del overview["production"]["panels"]["AAAAAAAAAAAA"]
    fake.refresh(make_data(overview=overview))

    assert not production.available
    assert entities["entry_panel_BBBBBBBBBBBB_production"].available


def device_entry(identifier: str) -> MagicMock:
    device = MagicMock()
    device.identifiers = {(DOMAIN, identifier)}
    return device


def loaded_entry(data: SunologyStreamData) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "entry"
    entry.runtime_data.coordinator.data = data
    return entry


@pytest.mark.asyncio
async def test_only_devices_gone_from_the_account_can_be_removed():
    entry = loaded_entry(make_data())
    for current in ("entry", "000000000000", "AAAAAAAAAAAA", "BBBBBBBBBBBB"):
        assert not await async_remove_config_entry_device(
            MagicMock(), entry, device_entry(current)
        ), current
    assert await async_remove_config_entry_device(
        MagicMock(), entry, device_entry("CCCCCCCCCCCC")
    )


@pytest.mark.asyncio
async def test_erl_device_can_be_removed_once_unlinked():
    entry = loaded_entry(make_data(erl=None))
    assert await async_remove_config_entry_device(
        MagicMock(), entry, device_entry("000000000000")
    )


@pytest.mark.asyncio
async def test_installation_device_is_kept_when_entry_is_not_loaded():
    entry = MagicMock(spec=["entry_id"])
    entry.entry_id = "entry"
    assert not await async_remove_config_entry_device(
        MagicMock(), entry, device_entry("entry")
    )
    assert await async_remove_config_entry_device(
        MagicMock(), entry, device_entry("AAAAAAAAAAAA")
    )


@pytest.mark.asyncio
async def test_price_sensors_need_the_selectra_tariff():
    entities = await setup_platform(
        sensor, make_data(tariff_details=None, tariff_prices=None)
    )
    for key in ("contract_off_peak_price", "contract_peak_price", "current_price"):
        assert f"entry_{key}" not in entities
    assert "entry_contract_pdl" in entities
