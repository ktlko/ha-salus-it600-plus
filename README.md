# Salus iT600 Plus for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![GitHub release](https://img.shields.io/github/v/release/ktlko/ha-salus-it600-plus)](https://github.com/ktlko/ha-salus-it600-plus/releases)
[![Validate](https://github.com/ktlko/ha-salus-it600-plus/actions/workflows/validate.yml/badge.svg)](https://github.com/ktlko/ha-salus-it600-plus/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Full **local** control of **Salus SQ610 / SQ610RF** thermostats through the **UGE600** gateway – including the settings from the thermostat menu that the built-in Salus integration does not offer.

[![Buy me a coffee](https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&emoji=&slug=kotelino&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff)](https://www.buymeacoffee.com/kotelino)

**Languages:** English, Slovenčina, Čeština, Deutsch, Polski, Español, Italiano

## Features

Per thermostat:

- **climate**: off / heat (/ cool), presets *schedule / temporary hold / permanent hold / away*, target temperature
- **switches**: child lock, show time / humidity / floor temperature, valve protection, optimum start / stop,
  unlock on the thermostat, setpoint change while locked
- **numbers**: min/max heating (and cooling) setpoint, temperature calibration, frost protection,
  max/min floor temperature
- **selects**: time format, °C/°F, display resolution, comfort warm floor; installer settings (control algorithm,
  S1/S2 input, relay function and contact type, cooling hysteresis) are disabled by default
- **sensors**: temperature, humidity, heating demand, problem, signal, weekly schedule
- **service `salus_plus.set_schedule`** – write the Monday–Sunday heating program to the thermostat

Gateway and Wiring Centre:

- UGE600: cloud / LAN connection, IP address, Zigbee channel and firmware
- KL08RF Wiring Centre zones and pump/boiler demand (derived from the thermostats' demand)
- boiler receiver: connection and boiler relay

## Requirements

- Salus **UGE600** gateway with **local mode** (the gateway's *EUID* is printed on its label – 16 characters)
- Salus **SQ610 / SQ610RF** thermostats paired with the gateway

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ktlko&repository=ha-salus-it600-plus&category=integration)

1. In Home Assistant open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/ktlko/ha-salus-it600-plus` with the type **Integration**.
3. Search for **Salus iT600 Plus**, open it and click **Download**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & services → Add integration** and pick **Salus iT600 Plus**.

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=salus_plus)

### Manual

Copy `custom_components/salus_plus` into the `custom_components` folder of your Home Assistant
configuration (the folder that contains `configuration.yaml`) and restart Home Assistant.

## Configuration

| Field | Meaning |
| --- | --- |
| Host | IP address of the UGE600 gateway |
| EUID | 16-character EUID from the gateway label |

If you use the built-in **Salus iT600** integration, both fields are pre-filled from it. All thermostats,
the Wiring Centre and the boiler receiver are found automatically; newly paired thermostats appear after a reload.

## Weekly schedule

```yaml
action: salus_plus.set_schedule
target:
  entity_id: climate.living_room
data:
  points:
    - {time: "06:00", temperature: 21}
    - {time: "22:00", temperature: 19}
```

1–6 switch points, 5–35 °C in 0.5 °C steps. The schedule is stored in the thermostat.

## Credits

Transport (AES framing, discovery) by [salus-it600-client](https://github.com/Jordi-14/salus-it600-client).

## Troubleshooting

Add this to `configuration.yaml` to get debug logs, then reproduce the problem and attach the log to an issue:

```yaml
logger:
  logs:
    custom_components.salus_plus: debug
```

**Settings → Devices & services → (integration) → ⋮ → Download diagnostics** creates a file without passwords or tokens –
attach it to bug reports.

## Support

Found a bug or have an idea? [Open an issue](https://github.com/ktlko/ha-salus-it600-plus/issues).

If this integration saves you time, you can support the development:

[![Buy me a coffee](https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&emoji=&slug=kotelino&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff)](https://www.buymeacoffee.com/kotelino)

## License

[MIT](LICENSE) – this project is not affiliated with or endorsed by the device manufacturers.
