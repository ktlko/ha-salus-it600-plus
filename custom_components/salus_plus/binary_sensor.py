"""Binary sensors: heating demand and device problem flags."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .devices import LEGACY_AUX_MODELS, features, has_prop, ias_kind
from .entity import SalusAuxEntity, SalusDeviceEntity, SalusEntity, SalusGatewayEntity

RECEIVER_MODEL = "it600Receiver"


async def async_setup_entry(
    hass: HomeAssistant, entry: SalusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for device_id in coordinator.data["th"]:
        entities.append(SalusRunning(coordinator, device_id, "running"))
        entities.append(SalusProblem(coordinator, device_id, "problem"))
    for device_id, info in coordinator.data["aux"].items():
        entities.append(AuxConnected(coordinator, device_id, "connected"))
        entities.append(AuxProblem(coordinator, device_id, "problem"))
        if info.get("model") == RECEIVER_MODEL:
            entities.append(AuxRelay(coordinator, device_id, "boiler_relay"))
        if info.get("zones"):
            entities.append(WcDemand(coordinator, device_id, "wc_demand"))
            for zone, _short in info["zones"]:
                entities.append(WcZoneDemand(coordinator, device_id, zone))
        entities.extend(_device_binary_sensors(coordinator, device_id, info))
    if coordinator.hub.gateway_id:
        entities.append(GatewayFlag(coordinator, "cloud_connected", "CloudStatus"))
        entities.append(GatewayFlag(coordinator, "lan_connected", "LANConnected_d"))
    async_add_entities(entities)


class AuxConnected(SalusAuxEntity, BinarySensorEntity):
    """Whether the gateway currently reaches this WC / receiver."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool:
        return bool(self.info.get("present") and self.info.get("online"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"listed_by_gateway": bool(self.info.get("present"))}


class AuxProblem(SalusAuxEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return super().available and bool(self.info.get("present"))

    @property
    def _errors(self) -> list[str]:
        errors = [k for k, v in self.flat.items()
                  if (k.startswith("Error") or k.startswith("TRVError"))
                  and k != "ErrorCodeWC_d" and not k.startswith("ErrorIASZSAlarmed")
                  and v not in (0, None)]
        code = self.flat.get("ErrorCodeWC_d")
        if code not in (None, "0000"):
            errors.append(f"ErrorCodeWC_d={code}")
        return sorted(errors)

    @property
    def is_on(self) -> bool:
        return bool(self._errors)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active_errors": self._errors}


class AuxRelay(SalusAuxEntity, BinarySensorEntity):
    """Boiler receiver relay (sIT600I.RelayStatus)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def available(self) -> bool:
        return super().available and bool(self.info.get("online")) and "RelayStatus" in self.flat

    @property
    def is_on(self) -> bool:
        return self.flat.get("RelayStatus") == 1


class _WcBase(SalusAuxEntity, BinarySensorEntity):
    """Derived WC outputs: the gateway exposes no live actuator/pump/boiler state."""

    def _thermostat_for(self, short_id: int) -> dict[str, Any] | None:
        for raw in (self.coordinator.data or {}).get("th", {}).values():
            if raw.get("ShortID_d") == short_id:
                return raw
        return None

    def _zones(self) -> list[list[int]]:
        return self.info.get("zones") or []

    def _zone_active(self, short_id: int) -> bool:
        raw = self._thermostat_for(short_id)
        return bool(raw and raw.get("RunningState") and raw.get("HoldType") != 7)


class WcZoneDemand(_WcBase):
    """Zone actuator open (derived from the paired thermostat's heating demand)."""

    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(self, coordinator, device_id: str, zone: int) -> None:
        super().__init__(coordinator, device_id, f"wc_zone_{zone}")
        self._zone = zone
        self._attr_translation_key = "wc_zone"
        short = next((s for z, s in self._zones() if z == zone), None)
        raw = self._thermostat_for(short) if short is not None else None
        room = (coordinator.hub.names.get(raw.get("UniID")) if raw else None) or "?"
        self._attr_translation_placeholders = {"zone": str(zone), "room": room}

    @property
    def _short(self) -> int | None:
        return next((s for z, s in self._zones() if z == self._zone), None)

    @property
    def is_on(self) -> bool | None:
        short = self._short
        return None if short is None else self._zone_active(short)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = self._thermostat_for(self._short) if self._short is not None else None
        return {
            "zone": self._zone,
            "thermostat": self.coordinator.hub.names.get(raw.get("UniID")) if raw else None,
            "thermostat_short_id": f"{self._short:04x}" if self._short is not None else None,
            "derived": True,
        }


class WcDemand(_WcBase):
    """Pump + boiler demand: on while any WC zone heats (derived)."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def is_on(self) -> bool:
        return any(self._zone_active(short) for _zone, short in self._zones())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "active_zones": [z for z, short in self._zones() if self._zone_active(short)],
            "derived": True,
        }


class GatewayFlag(SalusGatewayEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key: str, prop: str) -> None:
        super().__init__(coordinator, key)
        self._prop = prop

    @property
    def is_on(self) -> bool | None:
        value = self.raw.get(self._prop)
        return None if value is None else value == 1


class SalusRunning(SalusEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.HEAT

    @property
    def is_on(self) -> bool:
        return bool(self.raw.get("RunningState"))


class SalusProblem(SalusEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def _errors(self) -> list[str]:
        return sorted(k for k, v in self.raw.items() if k.startswith("Error") and v not in (0, None))

    @property
    def is_on(self) -> bool:
        return bool(self._errors)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active_errors": self._errors}


IAS_DEVICE_CLASS = {
    "window": BinarySensorDeviceClass.WINDOW,
    "door": BinarySensorDeviceClass.DOOR,
    "water_leak": BinarySensorDeviceClass.MOISTURE,
    "smoke": BinarySensorDeviceClass.SMOKE,
    "heat_alarm": BinarySensorDeviceClass.HEAT,
    "panic": BinarySensorDeviceClass.SAFETY,
    "alarm": BinarySensorDeviceClass.SAFETY,
}


def _device_binary_sensors(coordinator, device_id: str, info: dict[str, Any]) -> list[BinarySensorEntity]:
    """Binary sensors of the device families found in the Salus app."""
    found: list[BinarySensorEntity] = []
    f = features(info)
    if kind := ias_kind(info):
        found.append(DeviceFlag(coordinator, device_id, kind, "sIASZS", "ErrorIASZSAlarmed1",
                                IAS_DEVICE_CLASS[kind]))
    if "sIASZS" in f and has_prop(info, "sIASZS", "ErrorIASZSTampered"):
        found.append(DeviceFlag(coordinator, device_id, "tamper", "sIASZS", "ErrorIASZSTampered",
                                BinarySensorDeviceClass.TAMPER, diagnostic=True))
    for cluster, prop in (("sIASZS", "ErrorIASZSLowBattery"), ("sPowerS", "ErrorPowerSLowBattery")):
        if cluster in f and has_prop(info, cluster, prop):
            found.append(DeviceFlag(coordinator, device_id, "battery_low", cluster, prop,
                                    BinarySensorDeviceClass.BATTERY, diagnostic=True))
            break
    if "sOccupS" in f and has_prop(info, "sOccupS", "Occupancy"):
        found.append(DeviceFlag(coordinator, device_id, "motion", "sOccupS", "Occupancy",
                                BinarySensorDeviceClass.MOTION))
    if info.get("model") not in LEGACY_AUX_MODELS and has_prop(info, "sIT600I", "RelayStatus"):
        # iT600 Mini TRV relay.
        found.append(DeviceFlag(coordinator, device_id, "trv_relay", "sIT600I", "RelayStatus",
                                BinarySensorDeviceClass.HEAT))
    if "sTherS" in f and has_prop(info, "sTherS", "RunningState"):
        found.append(DeviceRunning(coordinator, device_id, "running"))
    return found


class DeviceFlag(SalusDeviceEntity, BinarySensorEntity):
    """One 0/1 property of a cluster (alarm, tamper, low battery, motion, relay)."""

    def __init__(self, coordinator, device_id: str, key: str, cluster: str, prop: str,
                 device_class: BinarySensorDeviceClass, diagnostic: bool = False) -> None:
        super().__init__(coordinator, device_id, key)
        self._cluster = cluster
        self._prop = prop
        self._attr_device_class = device_class
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        value = self.cl(self._cluster).get(self._prop)
        return None if value is None else bool(value)


class DeviceRunning(SalusDeviceEntity, BinarySensorEntity):
    """Heating demand of a Zigbee 3.0 thermostat / TRV (sTherS.RunningState)."""

    _attr_device_class = BinarySensorDeviceClass.HEAT

    @property
    def is_on(self) -> bool | None:
        value = self.cl("sTherS").get("RunningState")
        return None if value is None else bool(value)
