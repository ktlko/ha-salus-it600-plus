"""Climate entity for Salus SQ610 thermostats."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
import voluptuous as vol

from . import SalusConfigEntry
from .schedule import ScheduleError, SwitchPoint, decode, encode_mo_su
from .const import (
    HOLD_AWAY,
    HOLD_PERMANENT,
    HOLD_SCHEDULE,
    HOLD_STANDBY,
    HOLD_TEMPORARY,
    SYSTEM_MODE_COOL,
    SYSTEM_MODE_HEAT,
)
from .entity import SalusEntity

PRESET_SCHEDULE = "schedule"
PRESET_TEMPORARY = "temporary_hold"
PRESET_PERMANENT = "permanent_hold"
PRESET_AWAY = "away"

PRESET_TO_HOLD = {
    PRESET_SCHEDULE: HOLD_SCHEDULE,
    PRESET_TEMPORARY: HOLD_TEMPORARY,
    PRESET_PERMANENT: HOLD_PERMANENT,
    PRESET_AWAY: HOLD_AWAY,
}
HOLD_TO_PRESET = {v: k for k, v in PRESET_TO_HOLD.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: SalusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(SalusClimate(coordinator, device_id) for device_id in coordinator.data["th"])
    entity_platform.async_get_current_platform().async_register_entity_service(
        "set_schedule",
        {
            vol.Required("points"): vol.All(
                cv.ensure_list,
                vol.Length(min=1, max=6),
                [
                    vol.Schema(
                        {
                            vol.Required("time"): cv.string,
                            vol.Required("temperature"): vol.Coerce(float),
                        }
                    )
                ],
            )
        },
        "async_set_schedule",
    )


class SalusClimate(SalusEntity, ClimateEntity):
    """SQ610 thermostat: mode, preset (schedule/hold/away), setpoint."""

    _attr_name = None
    _attr_translation_key = "thermostat"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_preset_modes = list(PRESET_TO_HOLD)
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "climate")
        self._last_hold = HOLD_PERMANENT

    def _x100(self, prop: str) -> float | None:
        value = self.raw.get(prop)
        return value / 100 if isinstance(value, (int, float)) else None

    @property
    def _cooling(self) -> bool:
        return self.raw.get("SystemMode") == SYSTEM_MODE_COOL

    @property
    def hvac_modes(self) -> list[HVACMode]:
        modes = [HVACMode.OFF, HVACMode.HEAT]
        if self.raw.get("CoolingControl") == 1 or self._cooling:
            modes.append(HVACMode.COOL)
        return modes

    @property
    def hvac_mode(self) -> HVACMode:
        if self.raw.get("HoldType") == HOLD_STANDBY:
            return HVACMode.OFF
        return HVACMode.COOL if self._cooling else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if not self.raw.get("RunningState"):
            return HVACAction.IDLE
        return HVACAction.COOLING if self._cooling else HVACAction.HEATING

    @property
    def preset_mode(self) -> str | None:
        return HOLD_TO_PRESET.get(self.raw.get("HoldType"))

    @property
    def native_current_temperature(self) -> float | None:
        return self._x100("LocalTemperature_x100")

    @property
    def current_humidity(self) -> float | None:
        # SQ610 reports relative humidity in SunnySetpoint_x100 (whole percent).
        value = self.raw.get("SunnySetpoint_x100")
        return value if isinstance(value, (int, float)) else None

    @property
    def native_target_temperature(self) -> float | None:
        if self.hvac_mode == HVACMode.OFF:
            return None
        return self._x100("CoolingSetpoint_x100" if self._cooling else "HeatingSetpoint_x100")

    @property
    def min_temp(self) -> float:
        prop = "MinCoolSetpoint_x100" if self._cooling else "MinHeatSetpoint_x100"
        return self._x100(prop) or 5.0

    @property
    def max_temp(self) -> float:
        prop = "MaxCoolSetpoint_x100" if self._cooling else "MaxHeatSetpoint_x100"
        return self._x100(prop) or 35.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "hold_type": self.raw.get("HoldType"),
            "system_mode": self.raw.get("SystemMode"),
            "heating_setpoint": self._x100("HeatingSetpoint_x100"),
            "cooling_setpoint": self._x100("CoolingSetpoint_x100"),
            "schedule_type": self.raw.get("ScheduleType"),
            "schedule": decode(self.raw.get("HeatSchedule1")),
        }

    async def async_set_schedule(self, points: list[dict[str, Any]]) -> None:
        """Replace the on-device Mo-Su heating program (1-6 switch points)."""
        try:
            value = encode_mo_su(
                self.raw.get("HeatSchedule1"),
                [SwitchPoint(p["time"], p["temperature"]) for p in points],
            )
        except ScheduleError as err:
            raise HomeAssistantError(f"Invalid schedule: {err}") from err
        if self.raw.get("ScheduleType") not in (None, 1):
            raise HomeAssistantError(
                "Only the Monday-Sunday program (ScheduleType 1) is supported for writing"
            )
        try:
            await self.coordinator.hub.async_write_schedule(self.device_id, value)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Salus schedule write failed: {err}") from err
        self.coordinator.schedule_followup_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        value = round(round(float(temperature) * 2) / 2 * 100)
        prop = "CoolingSetpoint_x100" if self._cooling else "HeatingSetpoint_x100"
        await self.write_direct(prop, value)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        hold = PRESET_TO_HOLD[preset_mode]
        self._last_hold = hold
        await self.write_direct("HoldType", hold)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        current_hold = self.raw.get("HoldType")
        if hvac_mode == HVACMode.OFF:
            if current_hold not in (None, HOLD_STANDBY):
                self._last_hold = current_hold
            await self.write_direct("HoldType", HOLD_STANDBY)
            return
        mode = SYSTEM_MODE_COOL if hvac_mode == HVACMode.COOL else SYSTEM_MODE_HEAT
        if self.raw.get("SystemMode") != mode:
            await self.write_direct("SystemMode", mode)
        if current_hold == HOLD_STANDBY:
            await self.write_direct("HoldType", self._last_hold)

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.COOL if self._cooling else HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)
