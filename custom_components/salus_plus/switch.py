"""Switch entities: child lock (direct) and on/off advanced settings (B11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .entity import SalusEntity


@dataclass(frozen=True, kw_only=True)
class SalusSwitchDescription(SwitchEntityDescription):
    prop: str | None = None
    setting: str | None = None


SWITCHES: tuple[SalusSwitchDescription, ...] = (
    SalusSwitchDescription(key="child_lock", prop="LockKey", entity_category=EntityCategory.CONFIG),
    *(
        SalusSwitchDescription(key=key, setting=key, entity_category=EntityCategory.CONFIG)
        for key in (
            "display_time",
            "display_humidity",
            "display_floor_temperature",
            "valve_protection",
            "optimum_start",
            "optimum_stop",
            "unlock_from_thermostat",
            "adjust_setpoint_when_locked",
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SalusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SalusSwitch(coordinator, device_id, description)
        for device_id in coordinator.data["th"]
        for description in SWITCHES
    )


class SalusSwitch(SalusEntity, SwitchEntity):
    entity_description: SalusSwitchDescription

    def __init__(self, coordinator, device_id: str, description: SalusSwitchDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        d = self.entity_description
        if d.prop:
            value = self.raw.get(d.prop)
            return None if value is None else bool(value)
        return self.setting(d.setting)

    async def _set(self, on: bool) -> None:
        d = self.entity_description
        if d.prop:
            await self.write_direct(d.prop, int(on))
        else:
            await self.write_setting(d.setting, on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
