"""SQ610 advanced-settings blob (`Status_2_d`) codec and B11 command builder.

Layout: 77 bytes, byte 0 = 0x72 read marker. Each field's hex characters are
read as decimal digits ("2700" -> 27.00 degC). B11 writes the first 60 bytes:
`423131` + body where body[0] = 0x73 and only the target field differs from a
fresh read. Bytes 1 (save counter) and 40-41 (PIN, obfuscated) are owned by the
thermostat; they are copied unchanged and never computed here.

Verified live on SQ610NH firmware 00000056 (byte 5 toggle, 2026-11-04).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BLOB_LENGTH = 77
READ_MARKER = 0x72
WRITE_MARKER = 0x73
B11_PREFIX = "423131"
B11_BODY_LENGTH = 60
DEVICE_OWNED_BYTES = frozenset({0, 1, 40, 41})
PIN_REQUIRED_BYTE = 43

Kind = Literal["flag", "int1", "int2", "temp", "calibration"]


@dataclass(frozen=True)
class BlobField:
    """One field inside the advanced-settings blob."""

    key: str
    offset: int
    kind: Kind

    @property
    def length(self) -> int:
        return 1 if self.kind in ("flag", "int1") else 2


FIELDS: dict[str, BlobField] = {
    f.key: f
    for f in (
        BlobField("display_time", 2, "flag"),
        BlobField("temperature_calibration", 3, "calibration"),
        BlobField("display_humidity", 5, "flag"),
        BlobField("standby_heating_setpoint", 6, "temp"),
        BlobField("temperature_display_unit", 10, "int1"),
        BlobField("display_resolution", 11, "int1"),
        BlobField("control_algorithm", 12, "int1"),
        BlobField("cooling_control_span", 13, "int1"),
        BlobField("s1_s2_function", 15, "int1"),
        BlobField("max_floor_temp_heating", 16, "temp"),
        BlobField("min_floor_temp_heating", 18, "temp"),
        BlobField("min_floor_temp_cooling", 20, "temp"),
        BlobField("valve_protection", 30, "flag"),
        BlobField("internal_relay_function", 31, "int1"),
        BlobField("relay_contact_type", 32, "int1"),
        BlobField("min_off_time_heating", 33, "int2"),
        BlobField("min_off_time_cooling", 35, "int2"),
        BlobField("optimum_start", 37, "flag"),
        BlobField("optimum_stop", 38, "flag"),
        BlobField("comfort_warm_floor", 39, "int1"),
        BlobField("language", 42, "int1"),
        BlobField("pin_required", 43, "flag"),
        BlobField("display_floor_temperature", 45, "flag"),
        BlobField("unlock_from_thermostat", 46, "flag"),
        BlobField("adjust_setpoint_when_locked", 47, "flag"),
    )
}


class BlobError(ValueError):
    """Raised when a blob is not the verified layout or a value is invalid."""


def parse_blob(blob: str | None) -> bytes:
    """Validate and return the raw blob bytes."""
    if not isinstance(blob, str):
        raise BlobError("missing advanced-settings blob")
    try:
        raw = bytes.fromhex(blob)
    except ValueError as err:
        raise BlobError("blob is not hex") from err
    if len(raw) != BLOB_LENGTH or raw[0] != READ_MARKER:
        raise BlobError("unknown advanced-settings layout")
    return raw


def _digits(raw: bytes, field: BlobField) -> str | None:
    chars = raw[field.offset : field.offset + field.length].hex()
    return chars if chars.isdigit() else None


def decode_field(blob: str | None, key: str) -> float | int | bool | None:
    """Decode one field; None when absent or not decimal-encoded."""
    try:
        raw = parse_blob(blob)
    except BlobError:
        return None
    field = FIELDS[key]
    if field.kind == "calibration":
        chars = raw[field.offset : field.offset + 2].hex()
        sign, mag = chars[0], chars[1:]
        if sign not in "08" or not mag.isdigit():
            return None
        value = int(mag) / 100
        return -value if sign == "8" else value
    digits = _digits(raw, field)
    if digits is None:
        return None
    number = int(digits)
    if field.kind == "flag":
        return {0: False, 1: True}.get(number)
    if field.kind == "temp":
        return number / 100
    return number


def _encode(field: BlobField, value: float | int | bool) -> bytes:
    if field.kind == "flag":
        return bytes.fromhex("01" if value else "00")
    if field.kind == "int1":
        number = int(value)
        if not 0 <= number <= 99:
            raise BlobError(f"{field.key}: {number} out of range")
        return bytes.fromhex(f"{number:02d}")
    if field.kind == "int2":
        number = int(value)
        if not 0 <= number <= 9999:
            raise BlobError(f"{field.key}: {number} out of range")
        return bytes.fromhex(f"{number:04d}")
    if field.kind == "temp":
        number = round(float(value) * 100)
        if not 0 <= number <= 9999:
            raise BlobError(f"{field.key}: {value} out of range")
        return bytes.fromhex(f"{number:04d}")
    magnitude = round(abs(float(value)) * 100)
    if magnitude > 999:
        raise BlobError(f"{field.key}: {value} out of range")
    sign = "8" if float(value) < 0 and magnitude else "0"
    return bytes.fromhex(f"{sign}{magnitude:03d}")


def build_b11_command(blob: str, key: str, value: float | int | bool) -> str | None:
    """Return the B11 SetCommand_d hex for one field change, or None if unchanged."""
    raw = parse_blob(blob)
    field = FIELDS[key]
    if field.offset + field.length > B11_BODY_LENGTH:
        raise BlobError(f"{key} is outside the B11 body")
    if DEVICE_OWNED_BYTES & set(range(field.offset, field.offset + field.length)):
        raise BlobError(f"{key} overlaps device-owned bytes")
    if key == "pin_required":
        raise BlobError("PIN settings are not writable from Home Assistant")
    if raw[PIN_REQUIRED_BYTE] != 0:
        raise BlobError("thermostat settings are PIN-protected")
    encoded = _encode(field, value)
    if raw[field.offset : field.offset + field.length] == encoded:
        return None
    body = bytearray(raw[:B11_BODY_LENGTH])
    body[0] = WRITE_MARKER
    body[field.offset : field.offset + field.length] = encoded
    return B11_PREFIX + body.hex()
