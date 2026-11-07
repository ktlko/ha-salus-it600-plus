"""Cover entity for the RS600 roller shutter (sLevelS). Untested."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SalusConfigEntry
from .devices import is_cover
from .entity import SalusDeviceEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: SalusConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DeviceCover(coordinator, device_id)
        for device_id, info in coordinator.data["aux"].items()
        if is_cover(info)
    )


class DeviceCover(SalusDeviceEntity, CoverEntity):
    """Position 0 = closed, 100 = open (sLevelS.CurrentLevel / SetMoveToLevel)."""

    _attr_name = None
    _attr_device_class = CoverDeviceClass.SHUTTER
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id, "cover")

    @property
    def current_cover_position(self) -> int | None:
        value = self.cl("sLevelS").get("CurrentLevel")
        return max(0, min(100, int(value))) if isinstance(value, (int, float)) else None

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return None if position is None else position == 0

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = max(0, min(100, int(kwargs[ATTR_POSITION])))
        # Level byte + default transition time (FFFF), as the Salus app sends it.
        await self.write_cluster("sLevelS", {"MoveToLevel": f"{position:02x}FFFF"})

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.async_set_cover_position(**{ATTR_POSITION: 100})

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.async_set_cover_position(**{ATTR_POSITION: 0})
