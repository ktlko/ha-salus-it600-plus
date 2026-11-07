"""Base entity for Salus iT600 Plus."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .blob import BlobError, decode_field
from .const import DOMAIN
from .coordinator import SalusCoordinator


class SalusEntity(CoordinatorEntity[SalusCoordinator]):
    """One entity bound to one SQ610 thermostat."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SalusCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        if key != "climate":
            self._attr_translation_key = key
        hub = coordinator.hub
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=hub.names.get(device_id, device_id),
            manufacturer="Salus",
            model=hub.models.get(device_id),
            sw_version=self.raw.get("FirmwareVersion"),
            via_device_id=hub.gateway_device_id,
        )

    @property
    def raw(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("th", {}).get(self.device_id, {})

    @property
    def available(self) -> bool:
        return super().available and self.raw.get("OnlineStatus_i", 1) == 1

    def setting(self, key: str) -> Any:
        return decode_field(self.raw.get("Status_2_d"), key)

    async def write_direct(self, prop: str, value: int) -> None:
        try:
            await self.coordinator.hub.async_write_direct(self.device_id, prop, value)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Salus write {prop} failed: {err}") from err
        self._optimistic(prop, value)
        self.coordinator.schedule_followup_refresh()

    async def write_many(self, values: dict[str, int]) -> None:
        try:
            await self.coordinator.hub.async_write_many(self.device_id, values)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Salus write failed: {err}") from err
        for prop, value in values.items():
            self._optimistic(prop, value)
        self.coordinator.schedule_followup_refresh()

    async def write_setting(self, key: str, value: Any) -> None:
        try:
            await self.coordinator.hub.async_write_setting(self.device_id, key, value)
        except BlobError as err:
            raise HomeAssistantError(f"Salus setting {key}: {err}") from err
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Salus setting {key} failed: {err}") from err
        self.coordinator.schedule_followup_refresh()

    def _optimistic(self, prop: str, value: int) -> None:
        thermostats = (self.coordinator.data or {}).get("th", {})
        if self.device_id in thermostats:
            thermostats[self.device_id][prop] = value
            self.coordinator.async_update_listeners()


class SalusGatewayEntity(CoordinatorEntity[SalusCoordinator]):
    """Entity of the UGE600 gateway itself (data from sGateway/sAWSIoT and sCoord)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SalusCoordinator, key: str) -> None:
        super().__init__(coordinator)
        gateway_id = coordinator.hub.gateway_id
        self._attr_unique_id = f"{gateway_id}_{key}"
        self._attr_translation_key = key
        gw = self.raw
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, gateway_id)},
            connections={(CONNECTION_NETWORK_MAC, gateway_id)} if gateway_id else set(),
            name="UGE600",
            manufacturer="Salus",
            model=gw.get("ModelIdentifier") or "UGE600",
            sw_version=gw.get("GatewaySoftwareVersion"),
            hw_version=gw.get("GatewayHardwareVersion"),
        )

    @property
    def raw(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("gw", {})

    @property
    def zigbee(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("zc", {})


class SalusAuxEntity(CoordinatorEntity[SalusCoordinator]):
    """Entity of a wiring centre or boiler receiver.

    Stays available while the gateway answers, so an unplugged receiver shows
    as disconnected instead of disappearing.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: SalusCoordinator, device_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_translation_key = key
        info = self.info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=info.get("name") or device_id,
            manufacturer="Salus",
            model=info.get("model"),
            sw_version=info.get("flat", {}).get("FirmwareVersion"),
            via_device_id=coordinator.hub.gateway_device_id,
        )

    @property
    def info(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("aux", {}).get(self.device_id, {})

    @property
    def flat(self) -> dict[str, Any]:
        return self.info.get("flat", {})


class SalusDeviceEntity(SalusAuxEntity):
    """Entity of a device family found in the Salus app (plug, sensor, TRV, ...).

    Unavailable while the gateway reports the device offline or no longer lists it.
    """

    @property
    def available(self) -> bool:
        return super().available and bool(self.info.get("present") and self.info.get("online"))

    def cl(self, cluster: str) -> dict[str, Any]:
        return (self.info.get("clusters") or {}).get(cluster) or {}

    def x100(self, cluster: str, prop: str) -> float | None:
        value = self.cl(cluster).get(prop)
        return value / 100 if isinstance(value, (int, float)) else None

    async def write_cluster(self, cluster: str, values: dict[str, Any]) -> None:
        try:
            await self.coordinator.hub.async_write_cluster(self.device_id, cluster, values)
        except Exception as err:  # noqa: BLE001
            raise HomeAssistantError(f"Salus write {cluster} {values} failed: {err}") from err
        current = (self.info.get("clusters") or {}).get(cluster)
        if isinstance(current, dict):
            current.update(values)
            self.coordinator.async_update_listeners()
        self.coordinator.schedule_followup_refresh()
