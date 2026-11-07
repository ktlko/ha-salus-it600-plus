"""iT600 Wiring Centre zone table (`sIT600I.CommandResponse_d`, "B70" frame).

Frame: "423730" + 5 zero bytes + 0x08 + 12 slots of 3 bytes
(thermostat Zigbee ShortID big-endian, 1 flag byte; ffff = empty) + trailer.
Slot order is the WC zone order. A/B test on 2026-11-04 showed the frame is a
static pairing table: it does not change when a zone starts heating, so live
actuator / pump / boiler outputs are not exposed by the gateway. Zone demand is
therefore derived from the paired thermostat's RunningState.
"""

from __future__ import annotations

from dataclasses import dataclass

B70_PREFIX = "423730"
_SLOTS_START = 9  # bytes
_SLOT_COUNT = 12


@dataclass(frozen=True)
class WcZone:
    zone: int  # 1-based
    short_id: int
    flag: int


def parse_zones(frame: str | None) -> list[WcZone]:
    if not isinstance(frame, str) or not frame.lower().startswith(B70_PREFIX):
        return []
    try:
        raw = bytes.fromhex(frame)
    except ValueError:
        return []
    zones = []
    for i in range(_SLOT_COUNT):
        start = _SLOTS_START + 3 * i
        slot = raw[start : start + 3]
        if len(slot) < 3:
            break
        short_id = int.from_bytes(slot[:2], "big")
        if short_id == 0xFFFF:
            continue
        zones.append(WcZone(zone=i + 1, short_id=short_id, flag=slot[2]))
    return zones
