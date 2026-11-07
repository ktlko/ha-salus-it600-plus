"""Gateway access for Salus iT600 Plus.

Uses the salus-it600-client transport (AES framing, discovery) and adds the
full SQ610 write surface (tested on firmware used by the Salus app 0.121.1):
direct `sIT600TH.Set<Prop>` writes and B11 advanced-settings writes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from salus_it600.gateway import IT600Gateway, _flatten_dict

from .blob import build_b11_command

_LOGGER = logging.getLogger(__name__)

# Never keep gateway Wi-Fi/cloud credentials in coordinator data or state.
_SECRET_KEYS = re.compile(r"Password|AccessCode|SSID|Cert|ThingName|CloudID|OutboundIP", re.I)


def _device_name(flat: dict[str, Any]) -> str | None:
    try:
        return json.loads(flat.get("DeviceName", "")).get("deviceName")
    except (TypeError, ValueError, AttributeError):
        return None

# Direct writes verified against properties the SQ610NH exposes (see docs/NOTES.md).
DIRECT_WRITABLE = frozenset(
    {
        "HoldType",
        "SystemMode",
        "HeatingSetpoint_x100",
        "CoolingSetpoint_x100",
        "AutoHeatingSetpoint_x100",
        "AutoCoolingSetpoint_x100",
        "MinHeatSetpoint_x100",
        "MaxHeatSetpoint_x100",
        "MinCoolSetpoint_x100",
        "MaxCoolSetpoint_x100",
        "LockKey",
        "TemperatureDisplayMode",
        "TimeFormat24Hour",
    }
)


WRITABLE_CLUSTERS = frozenset({"sTherS", "sComm", "sTherUIS", "sOnOffS", "sLevelS"})


class SalusHub:
    """One UGE600 gateway and its SQ610 thermostats."""

    def __init__(self, host: str, euid: str, session: Any | None = None) -> None:
        self._gateway = IT600Gateway(euid=euid, host=host, session=session)
        self._write_lock = asyncio.Lock()
        self.gateway_id: str | None = None
        self.gateway_device_id: str | None = None  # device-registry id of the UGE600
        self.names: dict[str, str] = {}
        self.models: dict[str, str] = {}
        self.aux_data: dict[str, dict[str, Any]] = {}  # `data` envelope per non-SQ610 device

    async def async_connect(self) -> str:
        """Connect, discover devices and return the gateway unique id."""
        self.gateway_id = await self._gateway.connect()
        await self._gateway.poll_status()
        devices = self._gateway.get_climate_devices()
        self.names = {k: v.name for k, v in devices.items()}
        self.models = {k: v.model for k, v in devices.items()}
        return self.gateway_id

    async def async_close(self) -> None:
        await self._gateway.close()

    async def async_fetch(self, device_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
        """Return raw flattened properties per SQ610 device id."""
        return await self._gateway.fetch_sq610_properties(device_ids)

    async def async_fetch_all(self, known_aux: dict[str, dict[str, str]]) -> dict[str, Any]:
        """Read every device the gateway reports in one readall + one deviceid request.

        Returns {"th": {uid: flat}, "aux": {uid: info}, "gw": flat, "zc": flat}.
        `known_aux` devices (e.g. an unplugged boiler receiver) that the gateway no
        longer lists are returned with present=False so they show as offline.
        """
        gw = self._gateway
        readall = await gw._make_encrypted_request("read", {"requestAttr": "readall"})  # noqa: SLF001
        items = [i for i in readall.get("id", []) if isinstance(i, dict) and isinstance(i.get("data"), dict)]
        details = await gw._make_encrypted_request(  # noqa: SLF001
            "read", {"requestAttr": "deviceid", "id": [{"data": i["data"]} for i in items]}
        )
        result: dict[str, Any] = {"th": {}, "aux": {}, "gw": {}, "zc": {}}
        for item in details.get("id", []):
            if not isinstance(item, dict):
                continue
            flat = _flatten_dict(item)
            model = flat.get("ModelIdentifier_i") or flat.get("ModelIdentifier")
            uid = flat.get("UniID") or item.get("data", {}).get("UniID")
            if "sIT600TH" in item:
                result["th"][uid] = flat
            elif "sGateway" in item:
                result["gw"] = {k: v for k, v in flat.items() if not _SECRET_KEYS.search(k)}
            elif "sCoord" in item:
                result["zc"] = flat
            elif uid:
                self.aux_data[uid] = item.get("data", {})
                result["aux"][uid] = {
                    "model": model,
                    "name": _device_name(flat) or known_aux.get(uid, {}).get("name") or model,
                    "present": True,
                    "online": flat.get("OnlineStatus_i") == 1,
                    "flat": flat,
                    # Per-cluster view: several clusters share property names
                    # (e.g. sTempS/sHumiS MeasuredValue_x100), so `flat` is not enough.
                    "clusters": {k: v for k, v in item.items() if k != "data" and isinstance(v, dict)},
                }
        for uid, info in known_aux.items():
            if uid not in result["aux"]:
                result["aux"][uid] = {**info, "present": False, "online": False, "flat": {}}
        return result

    def _device(self, device_id: str) -> Any:
        device = self._gateway.get_climate_devices().get(device_id)
        if device is None:
            raise ValueError(f"unknown device {device_id}")
        return device

    async def async_write_direct(self, device_id: str, prop: str, value: int) -> None:
        """Write one sIT600TH property (`Set<prop>`)."""
        if prop not in DIRECT_WRITABLE:
            raise ValueError(f"{prop} is not a verified writable property")
        async with self._write_lock:
            _LOGGER.debug("%s Set%s=%s", device_id, prop, value)
            await self._gateway._write_device(  # noqa: SLF001 - transport only
                self._device(device_id), {"sIT600TH": {"Set" + prop: int(value)}}
            )

    async def async_write_many(self, device_id: str, values: dict[str, int]) -> None:
        """Write several sIT600TH properties in one request."""
        for prop in values:
            if prop not in DIRECT_WRITABLE:
                raise ValueError(f"{prop} is not a verified writable property")
        async with self._write_lock:
            await self._gateway._write_device(  # noqa: SLF001
                self._device(device_id),
                {"sIT600TH": {"Set" + k: int(v) for k, v in values.items()}},
            )

    async def async_write_schedule(self, device_id: str, heat_schedule1: str) -> None:
        """Write the on-device heating program (`sScheS.SetHeatSchedule1`, 63-byte hex)."""
        async with self._write_lock:
            _LOGGER.debug("%s SetHeatSchedule1=%s", device_id, heat_schedule1)
            await self._gateway._write_device(  # noqa: SLF001
                self._device(device_id), {"sScheS": {"SetHeatSchedule1": heat_schedule1}}
            )

    async def async_write_cluster(self, device_id: str, cluster: str, values: dict[str, Any]) -> None:
        """Write `Set<prop>` values to one cluster of a non-sIT600TH device.

        Used for the device families found in the Salus app (sTherS/sComm TRVs and
        fan-coil thermostats, sOnOffS plugs and relays, sLevelS shutters).
        """
        if cluster not in WRITABLE_CLUSTERS:
            raise ValueError(f"{cluster} is not a writable cluster")
        data = self.aux_data.get(device_id)
        if not data:
            raise ValueError(f"device {device_id} is not reachable")
        async with self._write_lock:
            _LOGGER.debug("%s %s %s", device_id, cluster, values)
            await self._gateway._make_encrypted_request(  # noqa: SLF001 - transport only
                "write",
                {"requestAttr": "write", "id": [{"data": data, cluster: {"Set" + k: v for k, v in values.items()}}]},
            )

    async def async_write_setting(self, device_id: str, key: str, value: Any) -> None:
        """Change one advanced setting via B11, based on a fresh blob read."""
        async with self._write_lock:
            fresh = (await self.async_fetch([device_id]))[device_id]
            command = build_b11_command(fresh.get("Status_2_d"), key, value)
            if command is None:
                return
            _LOGGER.debug("%s B11 %s=%s -> %s", device_id, key, value, command)
            await self._gateway._write_device(  # noqa: SLF001
                self._device(device_id), {"sIT600I": {"SetCommand_d": command}}
            )
