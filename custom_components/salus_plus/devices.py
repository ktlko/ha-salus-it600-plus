"""Device families of the Salus app (SALUS Premium Lite 0.121.1) behind a UGE600.

Model ids and gateway clusters come from the app's device catalogue
(`assets/config/salus.json`) and the cluster:property strings in its Dart code.
Everything here except the SQ610, the Wiring Centre and the boiler receiver is
untested on real hardware.

Devices are classified by the gateway clusters they report, not by model id,
so OEM variants of the same hardware work too:

- `sTherS` (+ `sComm` hold, `sTherUIS` lock): TRV3RF SuperQuiet TRV,
  FC600 fan coil and other Zigbee 3.0 thermostats -> climate
- `sOnOffS`: SP600/SPE600 smart plugs, SR600/SC812ZB/SC824ZB relays -> switch
- `sLevelS`: RS600 roller shutter -> cover
- `sIASZS`: SW600/OS600 window, WLS600 leak, SmokeSensor-EM/SMSZB-120 smoke,
  HESZB-120 heat, CSB600 panic button -> binary sensor (+ tamper, low battery)
- `sOccupS`: MS600 motion sensor -> binary sensor
- `sTempS` / `sHumiS`: PS600, CTLS631-633 -> temperature / humidity
- `sPowerS.BatteryVoltage_x10` -> battery voltage
- `sMeterS`: SPE600, ECM600 -> power / energy
- `sIT6ZB`: iT600 TRV (TRV10RFM, it600TRV) -> valve opening, TRV temperature
- `sIT600I.RelayStatus`: iT600 Mini TRV -> relay
"""

from __future__ import annotations

from typing import Any

# Kept exactly as before: these get only the original connection/problem/relay/zone entities.
LEGACY_AUX_MODELS = frozenset({"it600WC", "it600Receiver"})

# Clusters that make a device one of the new device families.
FEATURE_CLUSTERS = frozenset(
    {
        "sTherS", "sComm", "sTherUIS", "sFanS", "sOnOffS", "sLevelS", "sIASZS", "sOccupS",
        "sTempS", "sHumiS", "sPowerS", "sMeterS", "sIT6ZB", "sIT600I",
    }
)

# IAS zone (sIASZS.ErrorIASZSAlarmed1) meaning per model, from the app's device layouts.
IAS_KIND: dict[str, str] = {
    **dict.fromkeys(
        ("SW600", "OS600", "NTSW600", "SS882ZB", "SS912ZB", "CTLS634", "CTLS634_", "HDW10ZB"),
        "window",
    ),
    "SS881ZB": "door",
    **dict.fromkeys(("WLS600", "SS901ZB", "3315_S", "3315_G", "moisturev4"), "water_leak"),
    **dict.fromkeys(("SmokeSensor-EM", "SmokeSensor_EM", "SMSZB-120", "SMSZB_120"), "smoke"),
    **dict.fromkeys(("HESZB-120", "HESZB_120"), "heat_alarm"),
    **dict.fromkeys(("CSB600", "SS883ZB"), "panic"),
}

# Buttons only send events; their IAS bit is not a useful state.
BUTTON_MODELS = frozenset({"SB600", "SS884ZB"})


def clusters(info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return info.get("clusters") or {}


def features(info: dict[str, Any]) -> set[str]:
    """Clusters of a device: live when listed, remembered when it is offline."""
    if info.get("model") in LEGACY_AUX_MODELS:
        return set()
    live = clusters(info)
    names = set(live) if live else set(info.get("cluster_names", []))
    return names & FEATURE_CLUSTERS


def has_prop(info: dict[str, Any], cluster: str, prop: str) -> bool:
    if info.get("model") in LEGACY_AUX_MODELS:
        return False
    live = clusters(info)
    if live:
        return prop in live.get(cluster, {})
    return f"{cluster}.{prop}" in info.get("props", [])


def remembered(info: dict[str, Any]) -> dict[str, Any]:
    """What to keep in the config entry so an offline device keeps its entities."""
    if info.get("model") in LEGACY_AUX_MODELS:
        return {}
    live = clusters(info)
    names = sorted(set(live) & FEATURE_CLUSTERS)
    props = sorted(f"{c}.{p}" for c in names for p in live[c])
    return {"cluster_names": names, "props": props} if names else {}


def is_climate(info: dict[str, Any]) -> bool:
    return "sTherS" in features(info)


def is_cover(info: dict[str, Any]) -> bool:
    return "sLevelS" in features(info) and not is_climate(info)


def is_switch(info: dict[str, Any]) -> bool:
    f = features(info)
    return "sOnOffS" in f and "sLevelS" not in f and "sTherS" not in f


def ias_kind(info: dict[str, Any]) -> str | None:
    """Kind of the main alarm bit, or None when the device has no IAS zone to show."""
    if "sIASZS" not in features(info) or info.get("model") in BUTTON_MODELS:
        return None
    return IAS_KIND.get(info.get("model") or "", "alarm")


def is_sq610(model: str | None) -> bool:
    """SQ610 family (and unknown models, to keep earlier behaviour)."""
    return model is None or "SQ610" in model.upper()
