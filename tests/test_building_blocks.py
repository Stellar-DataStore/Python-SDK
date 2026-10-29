"""Field types, filter builders and tolerant model parsing."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest

from stellards import FieldType, Procedure, Project, RolePermissions, TablePermissions, Tokens, Webhook, join, where
from stellards.filters import select_query, sort_query
from stellards.models import parse_datetime

# --------------------------------------------------------------------------------------------- field types


@pytest.mark.parametrize(
    ("field_type", "expected"),
    [
        (FieldType.nvarchar(200), "NVarChar(200)"),
        (FieldType.nvarchar("max"), "NVarChar(max)"),
        (FieldType.nvarchar(), "NVarChar(255)"),
        (FieldType.tinyint(), "TinyInt"),
        (FieldType.smallint(), "SmallInt"),
        (FieldType.int(), "Int"),
        (FieldType.bigint(), "BigInt"),
        (FieldType.real(), "Real"),
        (FieldType.float(), "Float"),
        (FieldType.decimal(10, 2), "Decimal(10,2)"),
        (FieldType.decimal(), "Decimal(18,2)"),
        (FieldType.boolean(), "Boolean"),
        (FieldType.datetime(), "DateTime"),
        (FieldType.datetime_offset(), "DateTimeOffset"),
        (FieldType.date(), "Date"),
        (FieldType.time(), "Time"),
        (FieldType.uuid(), "Uuid"),
        (FieldType.json(), "Json"),
        (FieldType.blob(), "Blob"),
        (FieldType.enum(["a", "b"]), "Enum"),
    ],
)
def test_field_type_strings(field_type: FieldType, expected: str) -> None:
    assert field_type.type == expected
    assert str(field_type) == expected


def test_enum_options() -> None:
    assert FieldType.enum(("draft", "published")).options == ["draft", "published"]
    assert FieldType.int().options is None


@pytest.mark.parametrize(
    "make",
    [
        lambda: FieldType.nvarchar(0),
        lambda: FieldType.nvarchar("huge"),
        lambda: FieldType.decimal(0, 0),
        lambda: FieldType.decimal(39, 2),
        lambda: FieldType.decimal(5, 6),
        lambda: FieldType.enum([]),
        lambda: FieldType.enum(["a", "a"]),
    ],
)
def test_invalid_field_types(make: object) -> None:
    with pytest.raises(ValueError):
        make()  # type: ignore[operator]


# --------------------------------------------------------------------------------------------- filters


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (where("a", "=", 1), "a;equal;1"),
        (where("a", "==", "x"), "a;equal;x"),
        (where("a", "!=", "x"), "a;not_equal;x"),
        (where("a", "<>", "x"), "a;not_equal;x"),
        (where("a", ">", 1), "a;largerthan;1"),
        (where("a", "<", 1), "a;smallerthan;1"),
        (where("a", ">=", 1), "a;largerthan_equal;1"),
        (where("a", "<=", 1), "a;smallerthan_equal;1"),
        (where("a", "like", "%ab_"), "a;like;%25ab_"),
        (where("a", "not like", "x"), "a;notlike;x"),
        (where("a", "in", [1, 2, 3]), "a;in;1,2,3"),
        (where("a", "not in", ("x", "y z")), "a;notin;x,y%20z"),
        (where("a", "in", 5), "a;in;5"),
        (where("a", "null"), "a;null;true"),
        (where("a", "null", False), "a;null;false"),
        (where("a", "=", True), "a;equal;true"),
        (where("a", "=", Decimal("1.50")), "a;equal;1.50"),
        (where("a", "=", dt.date(2024, 1, 2)), "a;equal;2024-01-02"),
        (
            where("a", "=", dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)),
            "a;equal;2024-01-02T03%3A04%3A05%2B00%3A00",
        ),
        (where("a", "=", uuid.UUID(int=0)), "a;equal;00000000-0000-0000-0000-000000000000"),
        (where("a", "=", "Zoë"), "a;equal;Zo%C3%AB"),
    ],
)
def test_where_conditions(condition: object, expected: str) -> None:
    assert str(condition) == expected


def test_where_combinations_left_to_right() -> None:
    a, b, c = where("a", "=", 1), where("b", "=", 2), where("c", "=", 3)
    assert str(a & b) == "a;equal;1&b;equal;2"
    assert str(a | b & c) == "a;equal;1|b;equal;2&c;equal;3"
    assert str((a & b) | c) == "a;equal;1&b;equal;2|c;equal;3"
    # Combining doesn't change the operands.
    assert str(a) == "a;equal;1"
    assert a & b == where("a", "=", 1) & where("b", "=", 2)
    assert repr(a) == "Where('a;equal;1')"


@pytest.mark.parametrize(
    "make",
    [
        lambda: where("a", "~", 1),
        lambda: where("", "=", 1),
        lambda: where("a;b", "=", 1),
        lambda: where("a", "=", ""),
        lambda: where("a", "in", []),
        lambda: where("a", "in", ["x,y"]),
    ],
)
def test_invalid_where(make: object) -> None:
    with pytest.raises(ValueError):
        make()  # type: ignore[operator]


def test_join_sort_select() -> None:
    assert join("orders", "customerId", "customers", "id") == "orders;customerId=customers;id"
    assert sort_query("name") == "name;asc"
    assert sort_query("-name") == "name;desc"
    assert sort_query("+name") == "name;asc"
    assert sort_query(("name", "DESC")) == "name;desc"
    assert sort_query(["a", ("b", "desc"), "c;asc"]) == "a;asc,b;desc,c;asc"
    with pytest.raises(ValueError):
        sort_query(("a", "sideways"))
    assert select_query(["a", "b"]) == "a;b"
    assert select_query("a;b") == "a;b"


# --------------------------------------------------------------------------------------------- models


def test_models_ignore_unknown_fields_and_keep_raw() -> None:
    data = {"id": "p1", "name": "P", "isMultitenant": True, "brandNew": [1, 2], "tierId": "3"}
    project = Project.from_dict(data)
    assert project == Project(id="p1", name="P", is_multitenant=True, tier_id=3)
    assert project.raw == data
    assert Project.from_dict(None) == Project()
    assert Project.from_dict("not an object").raw == {}


def test_models_tolerate_wrong_types() -> None:
    webhook = Webhook.from_dict({"id": "12", "tableIds": "everything", "createdAt": "yesterday"})
    assert webhook.id == 12
    values: dict[str, Any] = vars(webhook)
    assert values["table_ids"] == "everything"
    assert values["created_at"] == "yesterday"


def test_nested_models_and_datetimes() -> None:
    procedure = Procedure.from_dict(
        {
            "name": "r",
            "createdAt": "2024-03-04T05:06:07.1234567Z",
            "updatedAt": "2024-03-04T05:06:07",
            "steps": [{"name": "s", "sql": "select 1", "extra": True}],
            "parameters": [{"name": "y", "type": "Int", "required": True}],
        }
    )
    assert procedure.created_at == dt.datetime(2024, 3, 4, 5, 6, 7, 123456, tzinfo=dt.timezone.utc)
    assert procedure.updated_at == dt.datetime(2024, 3, 4, 5, 6, 7)
    assert procedure.steps[0].sql == "select 1"
    assert procedure.parameters[0].required is True
    assert parse_datetime("2024-03-04T05:06:07.5+02:00") == dt.datetime(
        2024, 3, 4, 5, 6, 7, 500000, tzinfo=dt.timezone(dt.timedelta(hours=2))
    )


def test_role_permissions_round_trip() -> None:
    permissions = RolePermissions(
        create_tables=True,
        tables=[TablePermissions(table_name="Orders", read_records=True)],
        default_table_permission=TablePermissions(read_table=True),
    )
    wire = permissions.to_dict()
    assert wire["createTables"] is True
    assert wire["tables"][0]["tableName"] == "Orders"
    assert "tableName" not in wire["defaultTablePermission"]
    assert RolePermissions.from_dict(wire) == permissions


def test_tokens_compute_expiry() -> None:
    now = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)
    tokens = Tokens.from_response({"access_token": "a", "refresh_token": "r", "expires_in": 600}, now=now)
    assert tokens.expires_at == now + dt.timedelta(seconds=600)
    assert tokens.token_type == "Bearer"
