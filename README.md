# Sunology Stream for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://hacs.xyz/docs/faq/custom_repositories)
[![Active installations](https://img.shields.io/badge/dynamic/json?style=for-the-badge&color=41BDF5&label=Active%20installations&cacheSeconds=15600&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.sunology_stream.total)](https://analytics.home-assistant.io/)
[![Release](https://img.shields.io/github/v/release/Xaoimoon/ha-sunology-stream?style=for-the-badge)](https://github.com/Xaoimoon/ha-sunology-stream/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=for-the-badge)](https://github.com/Xaoimoon/ha-sunology-stream/blob/main/LICENSE)

[![Maintained](https://img.shields.io/badge/maintained-yes-green.svg?style=for-the-badge)](https://github.com/Xaoimoon/ha-sunology-stream/commits/main)
[![Activity](https://img.shields.io/github/commit-activity/y/Xaoimoon/ha-sunology-stream?style=for-the-badge)](https://github.com/Xaoimoon/ha-sunology-stream/commits/main)
[![Discussions](https://img.shields.io/github/discussions/Xaoimoon/ha-sunology-stream?style=for-the-badge&logo=github&color=7289DA)](https://github.com/Xaoimoon/ha-sunology-stream/discussions)
[![Issues](https://img.shields.io/github/issues/Xaoimoon/ha-sunology-stream?style=for-the-badge&logo=github&color=E05D44)](https://github.com/Xaoimoon/ha-sunology-stream/issues)
[![Stars](https://img.shields.io/github/stars/Xaoimoon/ha-sunology-stream?style=for-the-badge&logo=github&color=DFB317)](https://github.com/Xaoimoon/ha-sunology-stream/stargazers)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-support-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/xaoimoon)

Unofficial Home Assistant integration for Sunology Stream solar panels and the Linky TIC reader. It shows in Home Assistant the same information as the Sunology Stream app: solar production, household consumption, off-peak and peak hours, costs and panel status.

## Features

- Real-time solar production and energy produced today, in total and per panel.
- Household consumption and grid purchase, if you have a Linky TIC reader.
- Today's consumption in off-peak and peak hours, and its cost.
- Electricity prices of your contract: off-peak, peak and current price.
- Battery and status of each panel: WiFi, firmware, last synchronization, charge threshold, nomad mode.
- Works with the Home Assistant Energy dashboard.

## Installation

### Via HACS (recommended)

[![Open the repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Xaoimoon&repository=ha-sunology-stream&category=integration)

Click the button above, or add the repository manually:

1. In HACS, open the **⋮ > Custom repositories** menu and add `https://github.com/Xaoimoon/ha-sunology-stream` with the **Integration** type.
2. Search for "Sunology Stream" in HACS, then **Download**.
3. Restart Home Assistant.

HACS will then offer new versions automatically.

### Manual

1. Find the Home Assistant configuration folder (the one that contains `configuration.yaml`).
2. Create a `custom_components` folder in it if it does not exist yet.
3. Copy the `custom_components/sunology_stream` folder of this repository into it, to get `<config>/custom_components/sunology_stream/`.
4. Restart Home Assistant.

## Configuration

[![Add the integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=sunology_stream)

Click the button above, or:

1. **Settings > Devices & services > Add integration**.
2. Search for "Sunology Stream".
3. Sign in with the email and password of your Sunology Stream app account.

Home Assistant Core 2026.8 or later is required. If the integration does not show up in the search, check **Settings > System > Logs**: the most likely cause is a Home Assistant version that is too old.

## Devices and entities

The integration creates three kinds of devices:

- **Sunology installation** (one per account): total production power, energy produced today, self-reliance.
- **Linky TIC reader** (if you have one):
  - consumed power and power purchased from the grid;
  - energy consumed today, including off-peak and peak hours, and their cost;
  - off-peak, peak and current prices, in €/kWh;
  - status and last synchronization of the reader;
  - in diagnostics, the contract entered in the app: delivery point (PDL), offer, tariff option, subscribed power, off-peak hours, provider, grid operator.
- **One device per panel** (model, serial number, firmware): production, battery and diagnostics.

The Linky TIC reader and the panels are attached to the Sunology installation device. Without a Linky TIC reader, the consumption sensors are placed on the Sunology installation device.

## Good to know

### Off-peak and peak hours

- These sensors only appear if you have a Linky TIC reader **and** an off-peak / peak hours contract entered in the Sunology app (**Settings > Energy tariffs**).
- They are updated at the end of each hour, so with up to one hour of delay.
- Between midnight and 1 am, they still show the previous day's total, then start again from zero. No hour is lost.
- Costs use the prices of your contract, like in the app, and follow their changes.

### Energy dashboard

- The cost sensors can be used as the **entity tracking the total costs**.
- The **Current price** sensor can be used as the **entity with the current price**.

### Adding and removing panels

- A panel added in the Sunology app shows up on its own in Home Assistant, in less than a minute, without a restart.
- A panel removed from the app becomes "unavailable". You can then delete its device from its page in Home Assistant. Panels still on the account cannot be deleted.
- If a panel deleted from Home Assistant later comes back on the account, reload the integration to make it reappear.

### Internet connection

Data goes through the Sunology cloud: the integration needs Internet access, and the values are the ones shown in the app.

## Disclaimer

This project is not affiliated with Sunology. The integration relies on an undocumented API that may change without notice.

## For developers

How the API works, the development environment, the tests and the release process are described in [TECHNIQUE.md](https://github.com/Xaoimoon/ha-sunology-stream/blob/main/TECHNIQUE.md) (in French).

## License

MIT — see [LICENSE](https://github.com/Xaoimoon/ha-sunology-stream/blob/main/LICENSE).
