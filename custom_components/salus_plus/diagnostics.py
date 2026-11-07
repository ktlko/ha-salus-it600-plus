"""Diagnostics for Salus iT600 Plus (Settings -> Devices & services -> Download diagnostics)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import SalusConfigEntry
from .const import CONF_EUID

# Gateway secrets are already dropped by the hub; these identify the installation.
TO_REDACT = {
    CONF_HOST,
    CONF_EUID,
    "MACAddress",
    "NetworkLANIP",
    "NetworkLANMAC",
    "NetworkWiFiMAC",
    "NetworkLANRouterAddr",
    "NetworkLANSubnet",
    "NetworkPriDNS",
    "NetworkSecDNS",
    "PANID_d",
    "PhoneLocation",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SalusConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    hub = coordinator.hub
    data = coordinator.data or {}
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "models": hub.models,
        "thermostats": async_redact_data(data.get("th", {}), TO_REDACT),
        "devices": {
            uid: async_redact_data(
                {k: v for k, v in info.items() if k != "flat"}, TO_REDACT
            )
            for uid, info in data.get("aux", {}).items()
        },
        "gateway": async_redact_data(data.get("gw", {}), TO_REDACT),
        "zigbee": async_redact_data(data.get("zc", {}), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
    }
