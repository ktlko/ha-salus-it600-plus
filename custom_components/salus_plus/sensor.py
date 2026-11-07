"""Sensors: temperature, humidity and read-only diagnostics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .blob import decode_field
from .entity import SalusAuxEntity, SalusEntity, SalusGatewayEntity
from .schedule import decode as decode_schedule


def _x100(prop: str) -> Callable[[dict[str, Any]], Any]:
    def get(raw: dict[str, Any]) -> Any:
        value = raw.get(prop)
        return value / 100 if isinstance(value, (int, float)) else None
    return get


def _blob(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda raw: decode_field(raw.get("Status_2_d"), key)


@dataclass(frozen=True, kw_only=True)
class SalusSensorDescription(SensorEntityDescription):
    value: Callable[[dict[str, Any]], Any]


_DIAG = {"entity_category": EntityCategory.DIAGNOSTIC}

SENSORS: tuple[SalusSensorDescription, ...] = (
    SalusSensorDescription(
        key="temperature", value=_x100("LocalTemperature_x100"),
        device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    SalusSensorDescription(
        key="humidity", value=lambda raw: raw.get("SunnySetpoint_x100"),
        device_class=SensorDeviceClass.HUMIDITY, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SalusSensorDescription(key="min_off_time_heating", value=_blob("min_off_time_heating"), **_DIAG),
    SalusSensorDescription(key="min_off_time_cooling", value=_blob("min_off_time_cooling"),
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="language", value=_blob("language"), **_DIAG),
    SalusSensorDescription(key="out_sensor_probe", value=lambda raw: raw.get("OUTSensorProbe"),
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="out_sensor_type", value=lambda raw: raw.get("OUTSensorType"),
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="schedule_type", value=lambda raw: raw.get("ScheduleType"),
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="schedule", value=lambda raw: _schedule_summary(raw)),
)


def _schedule_summary(raw: dict[str, Any]) -> str | None:
    """'06:00 21 °C · 23:00 19 °C' for the on-device Mo-Su program."""
    program = decode_schedule(raw.get("HeatSchedule1"))
    if not program:
        return None
    if program.get("days") != "mon_sun":
        return "?"
    return " · ".join(f"{p['time']} {p['temperature']:g} °C" for p in program["points"]) or "—"


async def async_setup_entry(
    hass: HomeAssistant, entry: SalusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        SalusSensor(coordinator, device_id, description)
        for device_id in coordinator.data["th"]
        for description in SENSORS
    ]
    for device_id in coordinator.data["aux"]:
        entities.append(AuxSensor(coordinator, device_id, "signal_strength", "LastMessageRSSI_d"))
        entities.append(AuxSensor(coordinator, device_id, "link_quality", "LastMessageLQI_d"))
    if coordinator.hub.gateway_id:
        entities.append(GatewaySensor(coordinator, "ip_address", lambda gw, zc: gw.get("NetworkLANIP")))
        entities.append(GatewaySensor(coordinator, "zigbee_channel", lambda gw, zc: zc.get("Channel_d")))
        entities.append(GatewaySensor(coordinator, "zigbee_firmware", lambda gw, zc: zc.get("FirmwareVersion")))
    async_add_entities(entities)


class AuxSensor(SalusAuxEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, device_id: str, key: str, prop: str) -> None:
        super().__init__(coordinator, device_id, key)
        self._prop = prop
        if key == "signal_strength":
            self._attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
            self._attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT

    @property
    def available(self) -> bool:
        return super().available and bool(self.info.get("online"))

    @property
    def native_value(self) -> Any:
        return self.flat.get(self._prop)


class GatewaySensor(SalusGatewayEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key: str, value: Callable[[dict, dict], Any]) -> None:
        super().__init__(coordinator, key)
        self._value = value

    @property
    def native_value(self) -> Any:
        return self._value(self.raw, self.zigbee)


class SalusSensor(SalusEntity, SensorEntity):
    entity_description: SalusSensorDescription

    def __init__(self, coordinator, device_id: str, description: SalusSensorDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.raw)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key != "schedule":
            return None
        program = decode_schedule(self.raw.get("HeatSchedule1"))
        if program is None:
            return {"note": "gateway has not cached this thermostat's program yet"}
        return program
