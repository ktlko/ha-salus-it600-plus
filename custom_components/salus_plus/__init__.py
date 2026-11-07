"""Salus iT600 Plus: full local control of Salus SQ610 thermostats."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import AUX_IMPORT_MODELS, CONF_AUX_DEVICES, CONF_EUID, DOMAIN
from .coordinator import SalusCoordinator
from .hub import SalusHub

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type SalusConfigEntry = ConfigEntry[SalusCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SalusConfigEntry) -> bool:
    hub = SalusHub(
        entry.data[CONF_HOST], entry.data[CONF_EUID], async_get_clientsession(hass)
    )
    try:
        await hub.async_connect()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"Cannot reach Salus gateway: {err}") from err
    _import_aux_from_salus(hass, entry)
    coordinator = SalusCoordinator(hass, entry, hub)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    if hub.gateway_id:
        # Register the gateway first so thermostats/WC/receiver can point to it.
        gw = coordinator.data.get("gw", {})
        gateway_device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, hub.gateway_id)},
            connections={(dr.CONNECTION_NETWORK_MAC, hub.gateway_id)},
            name="UGE600",
            manufacturer="Salus",
            model=gw.get("ModelIdentifier") or "UGE600",
            sw_version=gw.get("GatewaySoftwareVersion"),
            hw_version=gw.get("GatewayHardwareVersion"),
        )
        hub.gateway_device_id = gateway_device.id
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _import_aux_from_salus(hass: HomeAssistant, entry: SalusConfigEntry) -> None:
    """Pick up WC/receiver devices the original `salus` integration knows about.

    An unplugged boiler receiver is no longer listed by the gateway, but it is
    still in the device registry of the original integration.
    """
    known = dict(entry.data.get(CONF_AUX_DEVICES, {}))
    registry = dr.async_get(hass)
    for salus_entry in hass.config_entries.async_entries("salus"):
        for device in dr.async_entries_for_config_entry(registry, salus_entry.entry_id):
            if device.model not in AUX_IMPORT_MODELS:
                continue
            for domain, uid in device.identifiers:
                if domain == "salus" and uid not in known:
                    known[uid] = {"model": device.model, "name": device.name_by_user or device.name}
    if known != entry.data.get(CONF_AUX_DEVICES, {}):
        hass.config_entries.async_update_entry(entry, data={**entry.data, CONF_AUX_DEVICES: known})


async def async_unload_entry(hass: HomeAssistant, entry: SalusConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.cancel_followups()
        await entry.runtime_data.hub.async_close()
    return unloaded
