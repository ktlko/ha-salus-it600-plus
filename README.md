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

## Supported devices

All devices are paired with a Salus **UGE600** gateway and read over its local API. Device families
are recognised by the gateway clusters they report, so OEM variants of the same hardware work too.

### Tested

| Device | Entities |
| --- | --- |
| **SQ610 / SQ610NH / SQ610RF** Quantum thermostat | climate, settings, schedule, sensors (full list above) |
| **KL08RF** Wiring Centre (`it600WC`) | connection, problem, signal, zone demand, pump/boiler demand |
| **RX10RB** boiler receiver (`it600Receiver`) | connection, problem, signal, boiler relay |
| **UGE600** gateway | cloud / LAN connection, IP address, Zigbee channel and firmware |

### Untested

Added in 1.1.0 from the device catalogue and gateway protocol of the official *SALUS Premium Lite* app.
They should work, but nobody has tried them with this integration yet – please
[open an issue](https://github.com/ktlko/ha-salus-it600-plus/issues) with the result and a debug log (see Troubleshooting).

| Device | Gateway clusters | Entities |
| --- | --- | --- |
| **VS10 / VS20** (`it600ThermHW`), **HTRP / HTRS / HTR** thermostats, **TS600** | `sIT600TH` | climate (off / heat / presets / setpoint), child lock, setpoint limits, time format, temperature, heating demand |
| **TRV3RF** SuperQuiet TRV, **FC600** fan coil and other Zigbee 3.0 thermostats | `sTherS`, `sComm`, `sTherUIS` | climate (off / heat (/ cool) / presets / setpoint), child lock, heating demand, floor temperature, battery |
| **TRV10RFM / it600TRV** TRV paired with a thermostat | `sIT6ZB` | valve opening, valve temperature |
| **iT600 Mini TRV** (`it600MINITRV`) | `sIT600I` | valve relay |
| **SP600 / SPE600** smart plug | `sOnOffS` (+ `sMeterS`) | switch (outlet), power and energy (SPE600) |
| **SR600** smart relay, **SC812ZB / SC824ZB** contact relays | `sOnOffS` | switch |
| **RS600** roller shutter | `sLevelS` | cover (open / close / position) |
| **SW600 / OS600** door/window sensor | `sIASZS` | window, tamper, low battery, battery voltage |
| **WLS600** water leak sensor | `sIASZS` | water leak, low battery |
| **SmokeSensor-EM**, **SMSZB-120** smoke detector, **HESZB-120** heat detector | `sIASZS` | smoke / heat alarm, tamper, low battery |
| **CSB600** protective button | `sIASZS` | panic button |
| **MS600** motion sensor | `sOccupS` | motion |
| **PS600** remote temperature sensor, **CTLS631 / 632 / 633** | `sTempS`, `sHumiS` | temperature, humidity, battery voltage |
| **ECM600** energy monitor | `sMeterS` | power, energy |

Every new device also gets *Connected*, *Problem*, *Signal strength* and *Link quality*.

Not supported yet (the app's protocol for them could not be confirmed without the hardware): hot water timers
(`it600HW`, `sIT600HW`), fan speed of the FC600, SB600 smart button events, SQ605RF dial thermostats, sirens,
keypads, door locks, lights and dimmers, solar inverters and the US-only devices of the app.

## Requirements

- Salus **UGE600** gateway with **local mode** (the gateway's *EUID* is printed on its label – 16 characters)
- Salus devices paired with the gateway (see [Supported devices](#supported-devices))

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
the Wiring Centre, the boiler receiver and the other devices are found automatically; newly paired devices appear after a reload.

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
