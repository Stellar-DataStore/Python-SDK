"""JSON encoding and decoding in StellarDS's wire formats.

The standard library can't write a :class:`decimal.Decimal` as a JSON number without going through ``float``, which
rounds. :func:`dumps` first converts the value to plain JSON types, putting a unique placeholder string where each
decimal goes, and then swaps each placeholder for the decimal's digits. The result is a JSON number with exactly the
decimal's digits.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import json
import secrets
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Callable

__all__ = ["dumps", "loads", "to_wire", "format_decimal"]


def format_decimal(value: Decimal) -> str:
    """The decimal as a JSON number: plain digits, no exponent, no rounding."""
    if not value.is_finite():
        raise ValueError(f"{value} can't be sent to StellarDS: JSON has no NaN or Infinity")
    text = format(value, "f")
    # "-0" and "-0.00" are valid JSON numbers, so they can go as they are.
    return text


def format_time(value: _dt.time) -> str:
    if value.tzinfo is not None and value.utcoffset() is not None:
        raise ValueError(
            "StellarDS Time fields have no time zone: convert the time to the zone you mean and pass it naive"
        )
    timespec = "seconds" if value.microsecond == 0 else "microseconds"
    return value.replace(tzinfo=None).isoformat(timespec=timespec)


def format_datetime(value: _dt.datetime) -> str:
    timespec = "seconds" if value.microsecond == 0 else "microseconds"
    return value.isoformat(timespec=timespec)


def to_wire(value: Any, on_decimal: Callable[[Decimal], Any] | None = None) -> Any:
    """Converts ``value`` to plain JSON types (dict, list, str, int, float, bool, None).

    - ``datetime.datetime`` -> ISO 8601 (with its offset when it is aware)
    - ``datetime.date`` -> ``"yyyy-MM-dd"``
    - ``datetime.time`` -> ``"HH:mm:ss"`` (fractional seconds only when there are any)
    - ``uuid.UUID`` -> its string
    - ``enum.Enum`` -> its value
    - ``Decimal`` -> ``on_decimal(value)``, or a float when no callback is given (only for display)
    - dataclasses -> a dict of their fields; mappings -> dicts; lists, tuples and sets -> lists
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("JSON has no NaN or Infinity")
        return value
    if isinstance(value, Decimal):
        if on_decimal is None:
            return float(value)
        return on_decimal(value)
    # datetime is a subclass of date, so it must come first.
    if isinstance(value, _dt.datetime):
        return format_datetime(value)
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, _dt.time):
        return format_time(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, enum.Enum):
        return to_wire(value.value, on_decimal)
    if isinstance(value, Mapping):
        return {str(k): to_wire(v, on_decimal) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_wire(v, on_decimal) for v in value]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return to_wire(to_dict(), on_decimal)
        return {f.name: to_wire(getattr(value, f.name), on_decimal) for f in dataclasses.fields(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise TypeError("Binary data goes through the blob endpoints: use records.upload_blob(...)")
    raise TypeError(f"Object of type {type(value).__name__} can't be sent as JSON")


def dumps(value: Any) -> str:
    """Serializes ``value`` to JSON in StellarDS's wire formats (see :func:`to_wire`)."""
    decimals: dict[str, str] = {}
    marker = "__stellards_decimal_" + secrets.token_hex(8) + "_"

    def on_decimal(d: Decimal) -> str:
        key = f"{marker}{len(decimals)}"
        decimals[key] = format_decimal(d)
        return key

    text = json.dumps(to_wire(value, on_decimal), ensure_ascii=False, separators=(",", ":"))
    for key, digits in decimals.items():
        text = text.replace(f'"{key}"', digits, 1)
    return text


def loads(text: str | bytes, *, parse_decimals: bool = False) -> Any:
    """Parses JSON. With ``parse_decimals``, numbers with a fraction or exponent become ``Decimal``."""
    if parse_decimals:
        return json.loads(text, parse_float=Decimal)
    return json.loads(text)
