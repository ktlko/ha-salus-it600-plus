"""Select entities: display formats (direct) and advanced settings (B11)."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .devices import is_sq610
from .entity import SalusEntity


@dataclass(frozen=True, kw_only=True)
class SalusSelectDescription(SelectEntityDescription):
    values: dict[str, int] = field(default_factory=dict)  # option -> wire value
    prop: str | None = None
    setting: str | None = None


def _d(key: str, values: dict[str, int], *, prop=None, setting=None, installer=False):
    return SalusSelectDescription(
        key=key,
        values=values,
        options=list(values),
        prop=prop,
        setting=setting,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=not installer,
    )


SELECTS: tuple[SalusSelectDescription, ...] = (
    _d("time_format", {"24h": 1, "12h": 0}, prop="TimeFormat24Hour"),
    _d("temperature_unit", {"celsius": 0, "fahrenheit": 1}, prop="TemperatureDisplayMode"),
    _d("display_resolution", {"0_5": 0, "0_1": 1}, setting="display_resolution"),
    _d("comfort_warm_floor", {"off": 0, "level_1": 1, "level_2": 2, "level_3": 3},
       setting="comfort_warm_floor"),
    # Installer-level settings: hidden by default, change only if you know the wiring.
    _d("control_algorithm",
       {"itlc_underfloor": 0, "itlc_radiators": 1, "itlc_electrical": 2, "thb_actuator": 5},
       setting="control_algorithm", installer=True),
    _d("s1_s2_function",
       {"disabled": 0, "floor_sensor": 1, "external_sensor": 2, "occupancy_sensor": 3,
        "run_onetouch": 4, "changeover": 5},
       setting="s1_s2_function", installer=True),
    _d("internal_relay_function",
       {"disabled": 0, "heat_and_cool": 1, "heat_only": 2, "cool_only": 3},
       setting="internal_relay_function", installer=True),
    _d("relay_contact_type", {"no_com": 0, "nc_com": 1},
       setting="relay_contact_type", installer=True),
    _d("cooling_control_span", {"0_25": 1, "0_5": 2, "1_0": 6, "1_5": 7, "2_0": 8},
       setting="cooling_control_span", installer=True),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: SalusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SalusSelect(coordinator, device_id, description)
        for device_id in coordinator.data["th"]
        for description in SELECTS
        if description.prop or is_sq610(coordinator.hub.models.get(device_id))
    )


class SalusSelect(SalusEntity, SelectEntity):
    entity_description: SalusSelectDescription

    def __init__(self, coordinator, device_id: str, description: SalusSelectDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        d = self.entity_description
        wire = self.raw.get(d.prop) if d.prop else self.setting(d.setting)
        for option, value in d.values.items():
            if value == wire:
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        d = self.entity_description
        value = d.values[option]
        if d.prop:
            await self.write_direct(d.prop, value)
        else:
            await self.write_setting(d.setting, value)
