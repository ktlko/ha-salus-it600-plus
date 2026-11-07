"""Polling coordinator for Salus iT600 Plus."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_AUX_DEVICES, DEFAULT_SCAN_INTERVAL, DOMAIN, REFRESH_DELAYS
from .hub import SalusHub
from .wc import parse_zones

_LOGGER = logging.getLogger(__name__)


class SalusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch every device: {"th": thermostats, "aux": WC/receiver, "gw": UGE600, "zc": Zigbee}."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub: SalusHub) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.hub = hub
        self.known_aux: dict[str, dict[str, str]] = dict(entry.data.get(CONF_AUX_DEVICES, {}))
        self._followups: set[asyncio.TimerHandle] = set()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.hub.async_fetch_all(self.known_aux)
        except Exception as err:  # noqa: BLE001 - surface any transport error
            raise UpdateFailed(f"Salus gateway: {err}") from err
        # Remember every auxiliary device ever seen so it stays listed when unplugged,
        # plus the last valid WC zone table (the B70 frame can be replaced by other replies).
        seen: dict[str, dict[str, Any]] = {}
        for uid, aux in data["aux"].items():
            entry_info: dict[str, Any] = {"model": aux["model"], "name": aux["name"]}
            zones = parse_zones(aux.get("flat", {}).get("CommandResponse_d"))
            if zones:
                entry_info["zones"] = [[z.zone, z.short_id] for z in zones]
            elif "zones" in self.known_aux.get(uid, {}):
                entry_info["zones"] = self.known_aux[uid]["zones"]
            if "zones" in entry_info:
                aux["zones"] = entry_info["zones"]
            seen[uid] = entry_info
        if seen != self.known_aux:
            self.known_aux = seen
            entry = self.config_entry
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_AUX_DEVICES: seen}
            )
        return data

    def schedule_followup_refresh(self) -> None:
        """Re-read a few seconds after a write so the UI shows the device state."""
        for delay in REFRESH_DELAYS:
            handle = self.hass.loop.call_later(
                delay, lambda: self.hass.async_create_task(self.async_request_refresh())
            )
            self._followups.add(handle)

    def cancel_followups(self) -> None:
        for handle in self._followups:
            handle.cancel()
        self._followups.clear()
