"""Field types: the ``type`` string (and Enum ``options``) of a field.

>>> FieldType.decimal(10, 2).type
'Decimal(10,2)'
>>> FieldType.nvarchar(200).type
'NVarChar(200)'
>>> FieldType.enum(["draft", "published"]).options
['draft', 'published']
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Union

__all__ = ["FieldType", "FieldTypeLike"]

# The class has methods named int and float; these aliases keep the annotations unambiguous.
_Int = int


@dataclass(frozen=True)
class FieldType:
    """A field type as StellarDS expects it: the type string plus, for Enum fields, the allowed values.

    Wire formats of record values per type (what the SDK sends for native Python values):

    ========================  ======================================================
    NVarChar                  ``str``
    TinyInt/SmallInt/Int/...  ``int``
    Real / Float              ``float``
    Decimal(p,s)              ``decimal.Decimal`` -> JSON number, exact digits
    Boolean                   ``bool``
    DateTime                  ``datetime.datetime`` -> ISO 8601
    DateTimeOffset            aware ``datetime.datetime`` -> ISO 8601 with offset
    Date                      ``datetime.date`` -> ``"yyyy-MM-dd"``
    Time                      ``datetime.time`` -> ``"HH:mm:ss"``
    Uuid                      ``uuid.UUID`` -> string
    Json                      any JSON value (dict, list, str, number, bool, None)
    Enum                      one of the field's options (``str``)
    Blob                      bytes, via ``records.upload_blob`` / ``download_blob``
    ========================  ======================================================
    """

    type: str
    options: list[str] | None = field(default=None)

    def __str__(self) -> str:
        return self.type

    # -- text
    @classmethod
    def nvarchar(cls, length: _Int | str = 255) -> FieldType:
        """Text of at most ``length`` characters; ``"max"`` for unlimited."""
        if isinstance(length, str):
            if length.lower() != "max":
                raise ValueError("length must be a positive int or 'max'")
            return cls("NVarChar(max)")
        if length < 1:
            raise ValueError("length must be a positive int or 'max'")
        return cls(f"NVarChar({length})")

    # -- numbers
    @classmethod
    def tinyint(cls) -> FieldType:
        return cls("TinyInt")

    @classmethod
    def smallint(cls) -> FieldType:
        return cls("SmallInt")

    @classmethod
    def int(cls) -> FieldType:
        return cls("Int")

    @classmethod
    def bigint(cls) -> FieldType:
        return cls("BigInt")

    @classmethod
    def real(cls) -> FieldType:
        return cls("Real")

    @classmethod
    def float(cls) -> FieldType:
        return cls("Float")

    @classmethod
    def decimal(cls, precision: _Int = 18, scale: _Int = 2) -> FieldType:
        """An exact number with ``precision`` digits, ``scale`` of them after the point."""
        if not 1 <= precision <= 38:
            raise ValueError("precision must be between 1 and 38")
        if not 0 <= scale <= precision:
            raise ValueError("scale must be between 0 and precision")
        return cls(f"Decimal({precision},{scale})")

    # -- other scalars
    @classmethod
    def boolean(cls) -> FieldType:
        return cls("Boolean")

    @classmethod
    def datetime(cls) -> FieldType:
        return cls("DateTime")

    @classmethod
    def datetime_offset(cls) -> FieldType:
        return cls("DateTimeOffset")

    @classmethod
    def date(cls) -> FieldType:
        return cls("Date")

    @classmethod
    def time(cls) -> FieldType:
        return cls("Time")

    @classmethod
    def uuid(cls) -> FieldType:
        return cls("Uuid")

    @classmethod
    def json(cls) -> FieldType:
        return cls("Json")

    @classmethod
    def blob(cls) -> FieldType:
        return cls("Blob")

    @classmethod
    def enum(cls, options: Iterable[str]) -> FieldType:
        """A text field limited to ``options`` (1 to 200 values of 1 to 100 characters, no duplicates)."""
        values = [str(o) for o in options]
        if not values:
            raise ValueError("an Enum field needs at least one option")
        if len(set(values)) != len(values):
            raise ValueError("Enum options must be unique")
        return cls("Enum", values)


#: What field methods accept as a type: a :class:`FieldType` or the type string itself (e.g. ``"Int"``).
FieldTypeLike = Union[FieldType, str]
