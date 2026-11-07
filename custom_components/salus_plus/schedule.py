"""SQ610 on-device weekly heating schedule (`sScheS.HeatSchedule1`).

Layout verified live on Pracovňa (SQ610NH fw 56, ScheduleType 1 = Mo-Su), 2026-11-04:
  byte 0      save counter (thermostat-owned; it stores its own next value)
  byte 1      day group: 00 = Monday-Sunday (one program for all days)
  bytes 2-25  6 switch points x 4 bytes: HHMM, temperature x100, both decimal
              digits written as hex ("0600" "2100" = 06:00 -> 21.00 degC);
              unused point = "ffff" + a placeholder temperature
  bytes 26-62 0xff padding (63 bytes total)
Writes use `sScheS.SetHeatSchedule1` with the same 63-byte layout. Other day
groups (Mo-Fr / Sa-Su, single days) are not verified and are reported raw.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LENGTH = 63
DAY_MO_SU = 0x00
POINTS = 6
_UNUSED_TEMPS = (2100, 1900, 2100, 2100, 1800, 2100)  # thermostat's own placeholders
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    """Invalid schedule value or unverified layout."""


@dataclass(frozen=True)
class SwitchPoint:
    time: str  # "HH:MM"
    temperature: float


def _dec(raw: bytes) -> int | None:
    digits = raw.hex()
    return int(digits) if digits.isdigit() else None


def decode(value: str | None) -> dict | None:
    """Return {"days": "mon_sun", "points": [...]} or {"raw": ...}; None if absent."""
    if not isinstance(value, str):
        return None
    try:
        raw = bytes.fromhex(value)
    except ValueError:
        return None
    if len(raw) != LENGTH or raw[1] != DAY_MO_SU:
        return {"days": "unknown", "raw": value}
    points = []
    for i in range(POINTS):
        slot = raw[2 + 4 * i : 6 + 4 * i]
        if slot[:2] == b"\xff\xff":
            continue
        hhmm, temp = _dec(slot[:2]), _dec(slot[2:])
        if hhmm is None or temp is None:
            return {"days": "unknown", "raw": value}
        points.append({"time": f"{hhmm // 100:02d}:{hhmm % 100:02d}", "temperature": temp / 100})
    return {"days": "mon_sun", "points": points}


def encode_mo_su(current: str | None, points: list[SwitchPoint]) -> str:
    """Build a 63-byte Mo-Su HeatSchedule1 value for `SetHeatSchedule1`."""
    if not 1 <= len(points) <= POINTS:
        raise ScheduleError(f"1 to {POINTS} switch points are required")
    parsed = []
    for point in points:
        match = _TIME.match(point.time.strip())
        if not match:
            raise ScheduleError(f"invalid time {point.time!r} (use HH:MM)")
        minutes = int(match.group(1)) * 60 + int(match.group(2))
        temp = round(float(point.temperature) * 2) / 2
        if not 5 <= temp <= 35:
            raise ScheduleError(f"temperature {point.temperature} outside 5-35 °C")
        parsed.append((minutes, temp))
    parsed.sort()
    if len({m for m, _ in parsed}) != len(parsed):
        raise ScheduleError("two switch points have the same time")
    counter = 0x01
    if isinstance(current, str):
        try:
            current_raw = bytes.fromhex(current)
            if len(current_raw) == LENGTH:
                counter = current_raw[0]
        except ValueError:
            pass
    body = bytearray([counter, DAY_MO_SU])
    for i in range(POINTS):
        if i < len(parsed):
            minutes, temp = parsed[i]
            body += bytes.fromhex(f"{minutes // 60:02d}{minutes % 60:02d}{round(temp * 100):04d}")
        else:
            body += bytes.fromhex(f"ffff{_UNUSED_TEMPS[i]:04d}")
    body += b"\xff" * (LENGTH - len(body))
    return body.hex()
