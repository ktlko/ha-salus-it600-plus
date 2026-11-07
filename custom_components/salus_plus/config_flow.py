"""Config flow for Salus iT600 Plus."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_EUID, DOMAIN
from .hub import SalusHub


class SalusPlusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for gateway host and EUID (prefilled from the existing salus entry)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            hub = SalusHub(
                user_input[CONF_HOST], user_input[CONF_EUID], async_get_clientsession(self.hass)
            )
            try:
                gateway_id = await hub.async_connect()
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(gateway_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Salus iT600 Plus", data=user_input)

        defaults: dict[str, str] = {}
        for entry in self.hass.config_entries.async_entries("salus"):
            defaults = {CONF_HOST: entry.data.get("host", ""), CONF_EUID: entry.data.get("token", "")}
            break
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
                vol.Required(CONF_EUID, default=defaults.get(CONF_EUID, "")): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
