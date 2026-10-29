from __future__ import annotations

import datetime as dt
import enum
import json
import uuid
from decimal import Decimal

import pytest

from stellards import _json


def test_decimal_is_a_json_number_with_exact_digits() -> None:
    value = Decimal("12345678901234.5678")
    text = _json.dumps({"price": value})
    assert text == '{"price":12345678901234.5678}'
    # A float would have rounded this one.
    assert float(value) != value
    assert json.loads(text, parse_float=Decimal)["price"] == value


def test_decimal_round_trips_through_loads_with_parse_decimals() -> None:
    value = Decimal("12345678901234.5678")
    assert _json.loads(_json.dumps([value]), parse_decimals=True) == [value]
    assert isinstance(_json.loads("1.5"), float)
    assert isinstance(_json.loads("1.5", parse_decimals=True), Decimal)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0.1"), "0.1"),
        (Decimal("-0.00"), "-0.00"),
        (Decimal("1E+3"), "1000"),
        (Decimal("1.5E-7"), "0.00000015"),
        (Decimal("99999999999999999999999999.99"), "99999999999999999999999999.99"),
    ],
)
def test_decimal_formats_without_exponent(value: Decimal, expected: str) -> None:
    assert _json.dumps(value) == expected


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), float("nan"), float("inf")])
def test_non_finite_numbers_are_refused(value: object) -> None:
    with pytest.raises(ValueError):
        _json.dumps({"x": value})


def test_native_types_use_the_wire_formats() -> None:
    class Color(enum.Enum):
        RED = "red"

    record = {
        "date": dt.date(2024, 2, 29),
        "time": dt.time(13, 5, 9),
        "timeFraction": dt.time(13, 5, 9, 250000),
        "naive": dt.datetime(2024, 2, 29, 13, 5, 9),
        "aware": dt.datetime(2024, 2, 29, 13, 5, 9, tzinfo=dt.timezone(dt.timedelta(hours=2))),
        "utc": dt.datetime(2024, 2, 29, 13, 5, 9, tzinfo=dt.timezone.utc),
        "uuid": uuid.UUID("12345678-1234-5678-1234-567812345678"),
        "enum": Color.RED,
        "json": {"nested": [1, 2.5, None, True, (3, 4)]},
        "amounts": [Decimal("1.10"), Decimal("2.20")],
    }
    assert json.loads(_json.dumps(record), parse_float=Decimal) == {
        "date": "2024-02-29",
        "time": "13:05:09",
        "timeFraction": "13:05:09.250000",
        "naive": "2024-02-29T13:05:09",
        "aware": "2024-02-29T13:05:09+02:00",
        "utc": "2024-02-29T13:05:09+00:00",
        "uuid": "12345678-1234-5678-1234-567812345678",
        "enum": "red",
        "json": {"nested": [1, Decimal("2.5"), None, True, [3, 4]]},
        "amounts": [Decimal("1.10"), Decimal("2.20")],
    }


def test_aware_time_is_refused() -> None:
    with pytest.raises(ValueError):
        _json.dumps(dt.time(1, 2, 3, tzinfo=dt.timezone.utc))


def test_bytes_point_to_the_blob_endpoints() -> None:
    with pytest.raises(TypeError, match="upload_blob"):
        _json.dumps({"file": b"abc"})


def test_unknown_objects_are_refused() -> None:
    with pytest.raises(TypeError):
        _json.dumps({"x": object()})


def test_string_that_looks_like_a_placeholder_is_left_alone() -> None:
    text = _json.dumps({"a": "__stellards_decimal_x_0", "b": Decimal("1.5")})
    assert json.loads(text) == {"a": "__stellards_decimal_x_0", "b": 1.5}
