"""Sensor platform for the Sunology Stream integration."""

from __future__ import annotations

from collections.abc import Callable
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CURRENCY_EURO,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfEnergy,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import SunologyStreamConfigEntry
from .coordinator import SunologyStreamData, SunologyStreamDataUpdateCoordinator
from .entity import (
    SunologyStreamPanelEntity,
    async_track_panels,
    erl_device_info,
    installation_device_info,
)


# ISO 4217 code: the Energy dashboard only accepts prices in "EUR/kWh".
CURRENCY_EURO_CODE = "EUR"


@dataclass(frozen=True, kw_only=True)
class SunologyStreamSensorDescription(SensorEntityDescription):
    """Describes a Sunology Stream sensor entity."""

    value_fn: Callable[[SunologyStreamData], Any]
    # For state_class TOTAL sensors that restart from 0 at local midnight:
    # exposes last_reset so long-term statistics handle the daily reset.
    resets_daily: bool = False
    # Grid-side data measured by the ERL: attached to the ERL device when
    # the account has one, otherwise to the installation device.
    on_erl: bool = False
    # Only created when this holds for the data at setup.
    requires: Callable[[SunologyStreamData], bool] | None = None


SENSOR_DESCRIPTIONS: tuple[SunologyStreamSensorDescription, ...] = (
    SunologyStreamSensorDescription(
        key="production_power",
        translation_key="production_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.get("production", {}).get("total"),
    ),
    SunologyStreamSensorDescription(
        key="consumption_power",
        translation_key="consumption_power",
        on_erl=True,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.get("consumptionData", {}).get("total"),
    ),
    SunologyStreamSensorDescription(
        key="grid_purchased_power",
        translation_key="grid_purchased_power",
        on_erl=True,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.overview.get("consumptionData", {}).get("purchased"),
    ),
    SunologyStreamSensorDescription(
        key="daily_production_energy",
        translation_key="daily_production_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _history_watt_value(data, "productionHistory"),
    ),
    SunologyStreamSensorDescription(
        key="daily_consumption_energy",
        translation_key="daily_consumption_energy",
        on_erl=True,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _history_watt_value(data, "consumptionHistory"),
    ),
    SunologyStreamSensorDescription(
        key="self_reliance",
        translation_key="self_reliance",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.history_daily.get("selfReliance"),
    ),
)


def _history_watt_value(data: SunologyStreamData, section: str) -> Any:
    """Extract the raw Wh total from a history_daily section, e.g.
    history_daily["productionHistory"]["total"]["wattValueSuffix"]["value"].
    """
    return (
        data.history_daily.get(section, {})
        .get("total", {})
        .get("wattValueSuffix", {})
        .get("value")
    )

ERL_LAST_SYNC_DESCRIPTION = SunologyStreamSensorDescription(
    key="erl_last_synchronization",
    translation_key="erl_last_synchronization",
    on_erl=True,
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    value_fn=lambda data: _parse_erl_timestamp(data),
)


def _parse_erl_timestamp(data: SunologyStreamData) -> datetime | None:
    if not data.erl:
        return None
    raw = data.erl.get("lastSynchronizationDate")
    if not raw:
        return None
    return dt_util.parse_datetime(raw)


def _off_peak_ranges(contract: dict[str, Any] | None) -> list[tuple[int, int]]:
    """Off-peak ranges from the signed contract, in minutes since midnight.

    The contract splits ranges at midnight ({"start": "22:56", "end": "00:00"}
    and {"start": "00:00", "end": "06:56"}); an "end" of "00:00" means 24:00.
    """
    if not contract:
        return []
    ranges = []
    for item in contract.get("config", {}).get("off_peak_hours") or []:
        try:
            start_h, start_m = (int(x) for x in item["start"].split(":"))
            end_h, end_m = (int(x) for x in item["end"].split(":"))
        except (KeyError, ValueError, AttributeError):
            continue
        start = start_h * 60 + start_m
        end = end_h * 60 + end_m or 24 * 60
        if end > start:
            ranges.append((start, end))
        else:
            ranges.extend([(start, 24 * 60), (0, end)])
    return ranges


def _off_peak_fraction(hour_start: datetime, ranges: list[tuple[int, int]]) -> float:
    """Share of the hour starting at `hour_start` (local) that is off-peak."""
    start = hour_start.hour * 60 + hour_start.minute
    end = start + 60
    overlap = sum(max(0, min(end, r_end) - max(start, r_start)) for r_start, r_end in ranges)
    return min(overlap, 60) / 60


def _day_energy_hours(data: SunologyStreamData) -> list[tuple[datetime, dict[str, Any]]]:
    """Today's completed hours as (local hour start, values) pairs."""
    if not data.day_energy:
        return []
    hours = []
    for key, values in (data.day_energy.get("energyAmountsAndCostsByHour") or {}).items():
        parsed = dt_util.parse_datetime(key)
        if parsed is None:
            continue
        hours.append((dt_util.as_local(parsed), values))
    return hours


def _day_consumption_kwh(data: SunologyStreamData, off_peak: bool) -> float | None:
    """Unrounded today's grid consumption (kWh) during off-peak or peak hours.

    Hours straddling a tariff change (e.g. 06:00-07:00 with off-peak ending at
    06:56) are split pro rata, the same way the API prices them.
    """
    ranges = _off_peak_ranges(data.contract)
    if not ranges or data.day_energy is None:
        return None
    total = 0.0
    for hour_start, values in _day_energy_hours(data):
        fraction = _off_peak_fraction(hour_start, ranges)
        total += (values.get("consumptionInKWh") or 0) * (fraction if off_peak else 1 - fraction)
    return total


def _day_consumption_split(data: SunologyStreamData, off_peak: bool) -> float | None:
    kwh = _day_consumption_kwh(data, off_peak)
    return None if kwh is None else round(kwh, 3)


def _tariff_unit_price(data: SunologyStreamData, off_peak: bool) -> float | None:
    """Exact off-peak or peak price (EUR/kWh) from the Selectra tariff sheet."""
    key = "price kwh hc" if off_peak else "price kwh hp"
    for feature in (data.tariff_details or {}).get("features") or []:
        if feature.get("type") == "consumption" and feature.get("key") == key:
            return feature.get("value")
    return None


def _current_unit_price(data: SunologyStreamData) -> float | None:
    """Price (EUR/kWh) of the Selectra price slot covering the current time."""
    now = dt_util.utcnow()
    for slot in (data.tariff_prices or {}).get("prices") or []:
        start = dt_util.parse_datetime(slot.get("start") or "")
        end = dt_util.parse_datetime(slot.get("end") or "")
        if start and end and start <= now < end:
            return slot.get("price")
    return None


def _day_consumption_cost(
    data: SunologyStreamData, off_peak: bool | None = None
) -> float | None:
    """Today's grid consumption cost (EUR).

    With the Selectra off-peak and peak prices, each tariff's kWh times its
    exact price. Otherwise the API's own hourly costs, whose prices are
    rounded to the cent (e.g. 16 c instead of 15.89 c): then with `off_peak`
    set, each hour's cost is split between the tariffs by duration.
    """
    if data.day_energy is None:
        return None
    ranges = _off_peak_ranges(data.contract)
    if off_peak is not None and not ranges:
        return None
    prices = {tariff: _tariff_unit_price(data, tariff) for tariff in (True, False)}
    if ranges and None not in prices.values():
        tariffs = (True, False) if off_peak is None else (off_peak,)
        return round(
            sum(_day_consumption_kwh(data, tariff) * prices[tariff] for tariff in tariffs), 2
        )
    total = 0.0
    for hour_start, values in _day_energy_hours(data):
        cost = values.get("consumptionInEuros") or 0
        if off_peak is not None:
            fraction = _off_peak_fraction(hour_start, ranges)
            cost *= fraction if off_peak else 1 - fraction
        total += cost
    return round(total, 2)


# Built on /client/energyAmountsAndCostsForDay, which only lists completed
# hours: these lag real time by up to an hour, and until about 01:00 they
# still show yesterday's full total (including its 23:00-24:00 hour).
OFF_PEAK_DESCRIPTIONS: tuple[SunologyStreamSensorDescription, ...] = (
    SunologyStreamSensorDescription(
        key="daily_off_peak_consumption_energy",
        translation_key="daily_off_peak_consumption_energy",
        on_erl=True,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _day_consumption_split(data, off_peak=True),
    ),
    SunologyStreamSensorDescription(
        key="daily_peak_consumption_energy",
        translation_key="daily_peak_consumption_energy",
        on_erl=True,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: _day_consumption_split(data, off_peak=False),
    ),
    # Meant as the "entity tracking the total costs" of the matching grid
    # consumption source in the Energy dashboard.
    SunologyStreamSensorDescription(
        key="daily_off_peak_consumption_cost",
        translation_key="daily_off_peak_consumption_cost",
        on_erl=True,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        state_class=SensorStateClass.TOTAL,
        resets_daily=True,
        value_fn=lambda data: _day_consumption_cost(data, off_peak=True),
    ),
    SunologyStreamSensorDescription(
        key="daily_peak_consumption_cost",
        translation_key="daily_peak_consumption_cost",
        on_erl=True,
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_EURO,
        state_class=SensorStateClass.TOTAL,
        resets_daily=True,
        value_fn=lambda data: _day_consumption_cost(data, off_peak=False),
    ),
)

DAILY_CONSUMPTION_COST_DESCRIPTION = SunologyStreamSensorDescription(
    key="daily_consumption_cost",
    translation_key="daily_consumption_cost",
    on_erl=True,
    device_class=SensorDeviceClass.MONETARY,
    native_unit_of_measurement=CURRENCY_EURO,
    state_class=SensorStateClass.TOTAL,
    resets_daily=True,
    value_fn=_day_consumption_cost,
)


def _contract_config(data: SunologyStreamData) -> dict[str, Any]:
    return (data.contract or {}).get("config") or {}


def _contract_choice(data: SunologyStreamData, field: str) -> str | None:
    """Label of a contract field stored as an id, e.g. provider_id 16 -> "EDF",
    looked up in the Selectra form options that come with the contract.
    """
    value = _contract_config(data).get(field)
    if value is None:
        return None
    options = (
        ((data.contract or {}).get("questionsForSelectra") or {}).get(field, {}).get("options")
        or {}
    )
    return options.get(str(value))


def _contract_offer(data: SunologyStreamData) -> str | None:
    """Offer name, given per language ({"fr": "Tarif bleu résidentiel"})."""
    name = _contract_config(data).get("offer_name")
    if isinstance(name, dict):
        return name.get("fr") or next(iter(name.values()), None)
    return name or _contract_choice(data, "offer_id")


def _contract_subscribed_power(data: SunologyStreamData) -> float | None:
    """Subscribed power in kVA, from its label (e.g. "9 kVA")."""
    label = _contract_choice(data, "power_id")
    match = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*kVA", label or "")
    return float(match.group(1).replace(",", ".")) if match else None


def _contract_off_peak_hours(data: SunologyStreamData) -> str | None:
    """Off-peak hours as "22:56-06:56", ranges split at midnight merged back."""
    ranges = sorted(_off_peak_ranges(data.contract))
    if not ranges:
        return None
    merged: list[list[int]] = []
    for start, end in ranges:
        if merged and merged[-1][1] == start:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    if len(merged) > 1 and merged[0][0] == 0 and merged[-1][1] == 24 * 60:
        # 22:56-24:00 followed by 00:00-06:56 is a single overnight range.
        merged[0][0] = merged.pop()[0]

    def fmt(minutes: int) -> str:
        return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"

    return ", ".join(f"{fmt(start)}-{fmt(end)}" for start, end in merged)


# From /client/clientSignedContract, i.e. what was entered in the app's
# "Energy rates" settings. Shown on the Linky TIC reader device.
CONTRACT_DESCRIPTIONS: tuple[SunologyStreamSensorDescription, ...] = (
    SunologyStreamSensorDescription(
        key="contract_pdl",
        translation_key="contract_pdl",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_erl=True,
        value_fn=lambda data: _contract_config(data).get("pdl"),
    ),
    SunologyStreamSensorDescription(
        key="contract_offer",
        translation_key="contract_offer",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_erl=True,
        value_fn=_contract_offer,
    ),
    SunologyStreamSensorDescription(
        key="contract_option",
        translation_key="contract_option",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_erl=True,
        value_fn=lambda data: _contract_config(data).get("option_name")
        or _contract_choice(data, "option_id"),
    ),
    # A plain kVA number rather than device_class apparent_power, whose kVA
    # unit only exists in recent Home Assistant versions.
    SunologyStreamSensorDescription(
        key="contract_subscribed_power",
        translation_key="contract_subscribed_power",
        native_unit_of_measurement="kVA",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_erl=True,
        value_fn=_contract_subscribed_power,
    ),
    SunologyStreamSensorDescription(
        key="contract_off_peak_hours",
        translation_key="contract_off_peak_hours",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_erl=True,
        value_fn=_contract_off_peak_hours,
    ),
    SunologyStreamSensorDescription(
        key="contract_off_peak_price",
        translation_key="contract_off_peak_price",
        native_unit_of_measurement=f"{CURRENCY_EURO_CODE}/{UnitOfEnergy.KILO_WATT_HOUR}",
        on_erl=True,
        requires=lambda data: _tariff_unit_price(data, True) is not None,
        value_fn=lambda data: _tariff_unit_price(data, True),
    ),
    SunologyStreamSensorDescription(
        key="contract_peak_price",
        translation_key="contract_peak_price",
        native_unit_of_measurement=f"{CURRENCY_EURO_CODE}/{UnitOfEnergy.KILO_WATT_HOUR}",
        on_erl=True,
        requires=lambda data: _tariff_unit_price(data, False) is not None,
        value_fn=lambda data: _tariff_unit_price(data, False),
    ),
    # Follows the Selectra price slots: usable as the Energy dashboard's
    # "entity with current price" for any time-of-use contract.
    SunologyStreamSensorDescription(
        key="current_price",
        translation_key="current_price",
        native_unit_of_measurement=f"{CURRENCY_EURO_CODE}/{UnitOfEnergy.KILO_WATT_HOUR}",
        on_erl=True,
        requires=lambda data: bool((data.tariff_prices or {}).get("prices")),
        value_fn=_current_unit_price,
    ),
    SunologyStreamSensorDescription(
        key="contract_provider",
        translation_key="contract_provider",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_erl=True,
        value_fn=lambda data: _contract_choice(data, "provider_id"),
    ),
    SunologyStreamSensorDescription(
        key="contract_distributor",
        translation_key="contract_distributor",
        entity_category=EntityCategory.DIAGNOSTIC,
        on_erl=True,
        value_fn=lambda data: _contract_config(data).get("distributor_name"),
    ),
)


@dataclass(frozen=True, kw_only=True)
class SunologyStreamPanelDetailDescription(SensorEntityDescription):
    """Describes a per-panel sensor built on /solar-panels/{id}."""

    value_fn: Callable[[dict[str, Any]], Any]
    # Only created for panels with an integrated battery (overview "has_b").
    requires_battery: bool = False


def _parse_timestamp(raw: Any) -> datetime | None:
    return dt_util.parse_datetime(raw) if raw else None


PANEL_DETAIL_DESCRIPTIONS: tuple[SunologyStreamPanelDetailDescription, ...] = (
    SunologyStreamPanelDetailDescription(
        key="wifi_signal",
        translation_key="panel_wifi_signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: details.get("rssiWifi"),
    ),
    SunologyStreamPanelDetailDescription(
        key="firmware_version",
        translation_key="panel_firmware_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: details.get("firmwareVersion"),
    ),
    SunologyStreamPanelDetailDescription(
        key="last_synchronization",
        translation_key="panel_last_synchronization",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: _parse_timestamp(details.get("lastSynchronizationDate")),
    ),
    # Grid power above which the battery starts charging (app: 210-450 W).
    SunologyStreamPanelDetailDescription(
        key="battery_charge_threshold",
        translation_key="panel_battery_charge_threshold",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda details: details.get("batteryThreshold"),
        requires_battery=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SunologyStreamConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Sunology Stream sensors from a config entry."""
    coordinator = entry.runtime_data.coordinator

    installation = installation_device_info(entry.entry_id)
    erl_device = (
        erl_device_info(
            entry.entry_id,
            coordinator.data.erl,
            entry.runtime_data.installation_device_id,
        )
        if coordinator.data.erl
        else installation
    )

    def device_for(description: SunologyStreamSensorDescription) -> DeviceInfo:
        return erl_device if description.on_erl else installation

    entities: list[SensorEntity] = [
        SunologyStreamSensor(coordinator, entry.entry_id, description, device_for(description))
        for description in SENSOR_DESCRIPTIONS
    ]

    if coordinator.data.erl:
        entities.extend(
            SunologyStreamSensor(coordinator, entry.entry_id, description, erl_device)
            for description in (ERL_LAST_SYNC_DESCRIPTION, DAILY_CONSUMPTION_COST_DESCRIPTION)
        )
        # Only for peak/off-peak contracts, which carry off-peak hours.
        if _off_peak_ranges(coordinator.data.contract):
            entities.extend(
                SunologyStreamSensor(coordinator, entry.entry_id, description, erl_device)
                for description in OFF_PEAK_DESCRIPTIONS
            )

    # The contract (PDL, offer, ...) is set in the app; on the Linky TIC
    # reader device, or the installation one for accounts without an ERL.
    if _contract_config(coordinator.data):
        entities.extend(
            SunologyStreamSensor(coordinator, entry.entry_id, description, device_for(description))
            for description in CONTRACT_DESCRIPTIONS
            if description.requires is None or description.requires(coordinator.data)
        )

    async_add_entities(entities)

    def build_panel_entities(
        serial_number: str, panel_data: dict[str, Any], device: DeviceInfo
    ) -> list[SensorEntity]:
        return [
            panel_class(coordinator, entry.entry_id, serial_number, device)
            for panel_class in (
                SunologyStreamPanelProductionSensor,
                SunologyStreamPanelBatteryLevelSensor,
                SunologyStreamPanelBatteryStateSensor,
            )
        ]

    def build_detail_entities(
        serial_number: str,
        panel_data: dict[str, Any],
        details: dict[str, Any],
        device: DeviceInfo,
    ) -> list[SensorEntity]:
        return [
            SunologyStreamPanelDetailSensor(
                coordinator, entry.entry_id, serial_number, device, description
            )
            for description in PANEL_DETAIL_DESCRIPTIONS
            if panel_data.get("has_b") or not description.requires_battery
        ]

    async_track_panels(
        entry, coordinator, async_add_entities, build_panel_entities, build_detail_entities
    )


class SunologyStreamSensor(
    CoordinatorEntity[SunologyStreamDataUpdateCoordinator], SensorEntity
):
    """A Sunology Stream sensor backed by the shared coordinator."""

    entity_description: SunologyStreamSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        description: SunologyStreamSensorDescription,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry_id}_{description.key}"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def last_reset(self) -> datetime | None:
        # The day the published data covers, not the current day: just after
        # midnight the value is still yesterday's total (see coordinator).
        if self.entity_description.resets_daily:
            return self.coordinator.data.day_energy_start
        return None


class SunologyStreamPanelProductionSensor(SunologyStreamPanelEntity, SensorEntity):
    """Production power for a single solar panel."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "panel_production"

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator, entry_id, serial_number, device_info, "production")

    @property
    def native_value(self) -> Any:
        return self.panel_data.get("production")


class SunologyStreamPanelBatteryLevelSensor(SunologyStreamPanelEntity, SensorEntity):
    """State of charge for a panel's integrated battery (0 for panels without one)."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "panel_battery_level"

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator, entry_id, serial_number, device_info, "battery_level")

    @property
    def native_value(self) -> Any:
        return self.panel_data.get("battery")


class SunologyStreamPanelBatteryStateSensor(SunologyStreamPanelEntity, SensorEntity):
    """Raw charge/discharge state for a panel's integrated battery.

    Exposed as a plain string (not device_class enum) since the full set of
    values the API can return isn't confirmed yet — only "OFF",
    "DISCHARGING" and "UNPLUGGED" have been observed.
    """

    _attr_translation_key = "panel_battery_state"

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator, entry_id, serial_number, device_info, "battery_state")

    @property
    def native_value(self) -> Any:
        return self.panel_data.get("batteryState")


class SunologyStreamPanelDetailSensor(SunologyStreamPanelEntity, SensorEntity):
    """A per-panel diagnostic sensor built on /solar-panels/{id}."""

    entity_description: SunologyStreamPanelDetailDescription

    def __init__(
        self,
        coordinator: SunologyStreamDataUpdateCoordinator,
        entry_id: str,
        serial_number: str,
        device_info: DeviceInfo,
        description: SunologyStreamPanelDetailDescription,
    ) -> None:
        super().__init__(coordinator, entry_id, serial_number, device_info, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        details = self.panel_details
        if details is None:
            return None
        return self.entity_description.value_fn(details)
