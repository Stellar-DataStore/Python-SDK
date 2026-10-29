"""Builders for the record query's ``where``, ``join`` and ``sort`` parameters.

>>> str(where("age", ">=", 18) & where("city", "=", "Ghent"))
'age;largerthan_equal;18&city;equal;Ghent'
>>> join("orders", "customerId", "customers", "id")
'orders;customerId=customers;id'
>>> sort_query(["-createdAt", "name"])
'createdAt;desc,name;asc'

Conditions combine left to right with ``&`` (and) and ``|`` (or); StellarDS has no parentheses, so
``a & b | c`` means ``(a and b) or c`` and ``a | b & c`` means ``(a or b) and c``.

The SDK percent-encodes each condition's value, so values may contain ``;``, ``&``, ``|``, ``%`` and ``+``.
The server splits the value of ``in`` / ``notin`` on commas, so those values can't contain a comma.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any, Union
from urllib.parse import quote

from ._json import format_datetime, format_decimal, format_time

__all__ = ["Condition", "Where", "where", "join", "sort_query", "select_query", "WhereLike", "SortLike"]

_OPERATORS = {
    "=": "equal",
    "==": "equal",
    "eq": "equal",
    "equal": "equal",
    "!=": "not_equal",
    "<>": "not_equal",
    "ne": "not_equal",
    "not_equal": "not_equal",
    ">": "largerthan",
    "gt": "largerthan",
    "largerthan": "largerthan",
    "<": "smallerthan",
    "lt": "smallerthan",
    "smallerthan": "smallerthan",
    ">=": "largerthan_equal",
    "ge": "largerthan_equal",
    "largerthan_equal": "largerthan_equal",
    "<=": "smallerthan_equal",
    "le": "smallerthan_equal",
    "smallerthan_equal": "smallerthan_equal",
    "like": "like",
    "not like": "notlike",
    "notlike": "notlike",
    "in": "in",
    "not in": "notin",
    "notin": "notin",
    "null": "null",
    "is null": "null",
}


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return format_decimal(value)
    if isinstance(value, _dt.datetime):
        return format_datetime(value)
    if isinstance(value, _dt.date):
        return value.isoformat()
    if isinstance(value, _dt.time):
        return format_time(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


class Where:
    """One or more conditions joined by and/or. Build them with :func:`where`."""

    __slots__ = ("_parts",)

    def __init__(self, parts: Sequence[tuple[str, str]]) -> None:
        # (condition text, logical operator following it or "")
        self._parts = tuple(parts)

    def _combine(self, other: Where, operator: str) -> Where:
        if not isinstance(other, Where):
            return NotImplemented
        head = list(self._parts)
        text, _ = head[-1]
        head[-1] = (text, operator)
        return Where(head + list(other._parts))

    def __and__(self, other: Where) -> Where:
        return self._combine(other, "&")

    def __or__(self, other: Where) -> Where:
        return self._combine(other, "|")

    def __str__(self) -> str:
        return "".join(text + op for text, op in self._parts)

    def __repr__(self) -> str:
        return f"Where({str(self)!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Where) and str(self) == str(other)

    def __hash__(self) -> int:
        return hash(str(self))


#: Kept for readability in type hints: a single condition is a :class:`Where` too.
Condition = Where


def where(field: str, operator: str, value: Any = True) -> Where:
    """A condition on ``field``.

    Operators: ``=``, ``!=``, ``>``, ``<``, ``>=``, ``<=``, ``like``, ``notlike``, ``in``, ``notin``, ``null``
    (or their StellarDS names such as ``largerthan_equal``). For ``in`` / ``notin`` pass a list. For ``null``
    pass ``True`` (is null, the default) or ``False`` (is not null). ``like`` uses SQL wildcards (``%``, ``_``).
    """
    if not field or any(c in field for c in ";&|"):
        raise ValueError(f"invalid field name: {field!r}")
    try:
        op = _OPERATORS[operator.strip().lower()]
    except KeyError:
        raise ValueError(f"unknown operator {operator!r}; use one of {sorted(set(_OPERATORS))}") from None
    if op in ("in", "notin"):
        single = isinstance(value, (str, bytes)) or not isinstance(value, Iterable)
        values = [value] if single else list(value)
        if not values:
            raise ValueError(f"'{operator}' needs at least one value")
        texts = [_format_value(v) for v in values]
        if any("," in t for t in texts):
            raise ValueError("values of 'in' / 'notin' can't contain a comma (the server splits on commas)")
        text = ",".join(quote(t, safe="") for t in texts)
    elif op == "null":
        text = "true" if value is None or bool(value) else "false"
    else:
        text = quote(_format_value(value), safe="")
    if not text:
        # The server's parser needs a non-empty value and silently drops the condition otherwise.
        raise ValueError("StellarDS can't filter on an empty value; use the 'null' operator for missing values")
    return Where([(f"{field};{op};{text}", "")])


def join(table_a: str, field_a: str, table_b: str, field_b: str) -> str:
    """A join of ``table_a.field_a`` with ``table_b.field_b`` (use table names). Pass a list for several joins."""
    return f"{table_a};{field_a}={table_b};{field_b}"


#: A where filter: a :class:`Where`, or the raw StellarDS syntax (``"field;operator;value&..."``).
WhereLike = Union[Where, str]
#: A sort: ``"name"`` / ``"-name"`` (descending), ``("name", "desc")``, the raw ``"name;asc"``, or a list of these.
SortLike = Union[str, tuple[str, str], Sequence[Union[str, tuple[str, str]]]]


def _sort_one(item: str | tuple[str, str]) -> str:
    if isinstance(item, tuple):
        name, direction = item
        direction = direction.lower()
        if direction not in ("asc", "desc"):
            raise ValueError(f"sort direction must be 'asc' or 'desc', not {direction!r}")
        return f"{name};{direction}"
    if ";" in item:
        return item
    if item.startswith("-"):
        return f"{item[1:]};desc"
    return f"{item.lstrip('+')};asc"


def sort_query(sort: SortLike) -> str:
    """The ``SortQuery`` text for ``sort`` (see :data:`SortLike`)."""
    if isinstance(sort, (str, tuple)):
        return _sort_one(sort)
    return ",".join(_sort_one(s) for s in sort)


def select_query(select: str | Iterable[str]) -> str:
    """The ``select`` text: field names separated by ``;``."""
    if isinstance(select, str):
        return select
    return ";".join(select)
