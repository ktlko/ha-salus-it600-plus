"""Number entities: setpoint limits (direct) and advanced settings (B11)."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .devices import is_sq610
from .entity import SalusEntity


@dataclass(frozen=True, kw_only=True)
class SalusNumberDescription(NumberEntityDescription):
    prop: str | None = None  # direct sIT600TH property (x100)
    setting: str | None = None  # B11 blob field


_TEMP = {
    "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
    "entity_category": EntityCategory.CONFIG,
    "mode": NumberMode.BOX,
}

NUMBERS: tuple[SalusNumberDescription, ...] = (
    SalusNumberDescription(key="min_heat_setpoint", prop="MinHeatSetpoint_x100",
                           native_min_value=5, native_max_value=35, native_step=0.5, **_TEMP),
    SalusNumberDescription(key="max_heat_setpoint", prop="MaxHeatSetpoint_x100",
                           native_min_value=5, native_max_value=35, native_step=0.5, **_TEMP),
    SalusNumberDescription(key="min_cool_setpoint", prop="MinCoolSetpoint_x100",
                           native_min_value=5, native_max_value=40, native_step=0.5,
                           entity_registry_enabled_default=False, **_TEMP),
    SalusNumberDescription(key="max_cool_setpoint", prop="MaxCoolSetpoint_x100",
                           native_min_value=5, native_max_value=40, native_step=0.5,
                           entity_registry_enabled_default=False, **_TEMP),
    SalusNumberDescription(key="temperature_calibration", setting="temperature_calibration",
                           native_min_value=-3, native_max_value=3, native_step=0.5, **_TEMP),
    SalusNumberDescription(key="standby_heating_setpoint", setting="standby_heating_setpoint",
                           native_min_value=5, native_max_value=17, native_step=0.5, **_TEMP),
    SalusNumberDescription(key="max_floor_temp_heating", setting="max_floor_temp_heating",
                           native_min_value=15, native_max_value=45, native_step=0.5, **_TEMP),
    SalusNumberDescription(key="min_floor_temp_heating", setting="min_floor_temp_heating",
                           native_min_value=5, native_max_value=30, native_step=0.5, **_TEMP),
    SalusNumberDescription(key="min_floor_temp_cooling", setting="min_floor_temp_cooling",
                           native_min_value=5, native_max_value=30, native_step=0.5,
                           entity_registry_enabled_default=False, **_TEMP),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SalusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SalusNumber(coordinator, device_id, description)
        for device_id in coordinator.data["th"]
        for description in NUMBERS
        if description.prop or is_sq610(coordinator.hub.models.get(device_id))
    )


class SalusNumber(SalusEntity, NumberEntity):
    entity_description: SalusNumberDescription

    def __init__(self, coordinator, device_id: str, description: SalusNumberDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        d = self.entity_description
        if d.prop:
            value = self.raw.get(d.prop)
            return value / 100 if isinstance(value, (int, float)) else None
        return self.setting(d.setting)

    async def async_set_native_value(self, value: float) -> None:
        d = self.entity_description
        if d.prop:
            await self.write_direct(d.prop, round(value * 100))
        else:
            await self.write_setting(d.setting, value)
