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
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .blob import decode_field
from .devices import features, has_prop, is_climate, is_sq610
from .entity import SalusAuxEntity, SalusDeviceEntity, SalusEntity, SalusGatewayEntity
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
    sq610_only: bool = False  # SQ610 humidity, B11 blob and schedule


_DIAG = {"entity_category": EntityCategory.DIAGNOSTIC}

SENSORS: tuple[SalusSensorDescription, ...] = (
    SalusSensorDescription(
        key="temperature", value=_x100("LocalTemperature_x100"),
        device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    SalusSensorDescription(
        key="humidity", value=lambda raw: raw.get("SunnySetpoint_x100"), sq610_only=True,
        device_class=SensorDeviceClass.HUMIDITY, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    SalusSensorDescription(key="min_off_time_heating", value=_blob("min_off_time_heating"), sq610_only=True, **_DIAG),
    SalusSensorDescription(key="min_off_time_cooling", value=_blob("min_off_time_cooling"), sq610_only=True,
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="language", value=_blob("language"), sq610_only=True, **_DIAG),
    SalusSensorDescription(key="out_sensor_probe", value=lambda raw: raw.get("OUTSensorProbe"),
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="out_sensor_type", value=lambda raw: raw.get("OUTSensorType"),
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="schedule_type", value=lambda raw: raw.get("ScheduleType"),
                           entity_registry_enabled_default=False, **_DIAG),
    SalusSensorDescription(key="schedule", value=lambda raw: _schedule_summary(raw), sq610_only=True),
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
        if not description.sq610_only or is_sq610(coordinator.hub.models.get(device_id))
    ]
    for device_id, info in coordinator.data["aux"].items():
        entities.append(AuxSensor(coordinator, device_id, "signal_strength", "LastMessageRSSI_d"))
        entities.append(AuxSensor(coordinator, device_id, "link_quality", "LastMessageLQI_d"))
        entities.extend(
            DeviceSensor(coordinator, device_id, d)
            for d in DEVICE_SENSORS
            if d.cluster in features(info) and has_prop(info, d.cluster, d.prop)
            and not (d.cluster == "sTherS" and not is_climate(info))
        )
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


@dataclass(frozen=True, kw_only=True)
class DeviceSensorDescription(SensorEntityDescription):
    cluster: str
    prop: str
    scale: float = 1


_TEMP = {
    "device_class": SensorDeviceClass.TEMPERATURE,
    "state_class": SensorStateClass.MEASUREMENT,
    "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
    "scale": 0.01,
}

DEVICE_SENSORS: tuple[DeviceSensorDescription, ...] = (
    # PS600 / CTLS63x remote sensors (also the temperature of a Zigbee 3.0 thermostat).
    DeviceSensorDescription(key="temperature", cluster="sTempS", prop="MeasuredValue_x100", **_TEMP),
    DeviceSensorDescription(
        key="humidity", cluster="sHumiS", prop="MeasuredValue_x100", scale=0.01,
        device_class=SensorDeviceClass.HUMIDITY, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
    ),
    # Floor sensor of TRV3RF / FC600 style thermostats (sTherS).
    DeviceSensorDescription(key="floor_temperature", cluster="sTherS", prop="FloorTemperature_x100",
                            entity_registry_enabled_default=False, **_TEMP),
    DeviceSensorDescription(
        key="heating_demand", cluster="sTherS", prop="HeatingDemandInPtg",
        state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=PERCENTAGE,
    ),
    # iT600 TRV (TRV10RFM, it600TRV).
    DeviceSensorDescription(
        key="valve_opening", cluster="sIT6ZB", prop="TRVOutputPercentage",
        state_class=SensorStateClass.MEASUREMENT, native_unit_of_measurement=PERCENTAGE,
    ),
    DeviceSensorDescription(key="trv_temperature", cluster="sIT6ZB", prop="TRVInternalSensorTemp_x100", **_TEMP),
    # Battery devices report the cell voltage; the app shows only "low battery".
    DeviceSensorDescription(
        key="battery_voltage", cluster="sPowerS", prop="BatteryVoltage_x10", scale=0.1,
        device_class=SensorDeviceClass.VOLTAGE, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # SPE600 smart plug / ECM600 energy monitor (ZCL metering, Multiplier/Divisor scaled).
    DeviceSensorDescription(
        key="power", cluster="sMeterS", prop="InstantaneousDemand",
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
    ),
    DeviceSensorDescription(
        key="energy", cluster="sMeterS", prop="CurrentSummationDelivered",
        device_class=SensorDeviceClass.ENERGY, state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    ),
)


class DeviceSensor(SalusDeviceEntity, SensorEntity):
    entity_description: DeviceSensorDescription

    def __init__(self, coordinator, device_id: str, description: DeviceSensorDescription) -> None:
        super().__init__(coordinator, device_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        d = self.entity_description
        cluster = self.cl(d.cluster)
        value = cluster.get(d.prop)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        if d.cluster == "sMeterS":
            multiplier = cluster.get("Multiplier") or 1
            divisor = cluster.get("Divisor") or 1
            return round(value * multiplier / divisor, 3)
        return round(value * d.scale, 2)
