"""Switch entities: child lock (direct) and on/off advanced settings (B11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .devices import has_prop, is_climate, is_sq610, is_switch
from .entity import SalusDeviceEntity, SalusEntity


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
    entities: list[SwitchEntity] = [
        SalusSwitch(coordinator, device_id, description)
        for device_id in coordinator.data["th"]
        for description in SWITCHES
        # B11 settings exist only on the SQ610 family; other iT600 thermostats keep the lock.
        if description.prop or is_sq610(coordinator.hub.models.get(device_id))
    ]
    for device_id, info in coordinator.data["aux"].items():
        if is_switch(info):
            entities.append(DeviceSwitch(coordinator, device_id))
        if is_climate(info) and has_prop(info, "sTherUIS", "LockKey"):
            entities.append(DeviceChildLock(coordinator, device_id))
    async_add_entities(entities)


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


class DeviceSwitch(SalusDeviceEntity, SwitchEntity):
    """SP600/SPE600 smart plug or SR600 smart relay (sOnOffS)."""

    _attr_name = None

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "switch")
        model = (self.info.get("model") or "").upper()
        self._attr_device_class = (
            SwitchDeviceClass.OUTLET if model.startswith(("SP", "CTLP", "SX885")) else SwitchDeviceClass.SWITCH
        )

    @property
    def is_on(self) -> bool | None:
        value = self.cl("sOnOffS").get("OnOff")
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.write_cluster("sOnOffS", {"OnOff": 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.write_cluster("sOnOffS", {"OnOff": 0})


class DeviceChildLock(SalusDeviceEntity, SwitchEntity):
    """Keypad lock of a Zigbee 3.0 thermostat / TRV (sTherUIS.LockKey)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "child_lock")

    @property
    def is_on(self) -> bool | None:
        value = self.cl("sTherUIS").get("LockKey")
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.write_cluster("sTherUIS", {"LockKey": 1})

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.write_cluster("sTherUIS", {"LockKey": 0})
