from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from typing import Any
from urllib.parse import unquote

import httpx
import pytest
import respx

from stellards import AsyncStellarDS, StellarDS, join, where

from .conftest import PROJECT, ok


def page_server(total: int) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("Offset", "0"))
        take = int(request.url.params.get("Take", "100"))
        records = [{"id": i + 1} for i in range(offset, min(offset + take, total))]
        return ok(records, count=total)

    return handler


def test_query_builds_the_query_string(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/data/table").mock(return_value=ok([{"id": 1, "name": "x"}], count=42))
    page = sds.records.query(
        12,
        where=where("name", "like", "a&b;c|d%+e") & where("age", ">=", 18) | where("city", "in", ["Ghent", "Paris"]),
        join=[join("orders", "customerId", "customers", "id")],
        sort=["-createdAt", "name"],
        offset=20,
        take=10,
        distinct=True,
        select=["name", "age"],
    )
    assert page.count == 42
    assert page.records == [{"id": 1, "name": "x"}]
    assert list(page) == page.records and len(page) == 1 and page[0]["id"] == 1
    params = route.calls.last.request.url.params
    assert params["project"] == PROJECT
    assert params["table"] == "12"
    assert params["Offset"] == "20"
    assert params["Take"] == "10"
    assert params["distinct"] == "true"
    assert params["select"] == "name;age"
    assert params["SortQuery"] == "createdAt;desc,name;asc"
    assert params["JoinQuery"] == "orders;customerId=customers;id"
    where_text = params["WhereQuery"]
    assert where_text == "name;like;a%26b%3Bc%7Cd%25%2Be&age;largerthan_equal;18|city;in;Ghent,Paris"
    # What the server does with it: split on ; & | (outside values), then URL-decode each value.
    assert unquote(where_text.split("&")[0].split(";")[2]) == "a&b;c|d%+e"
    # Every query value is URL-encoded on the wire.
    raw_query = route.calls.last.request.url.query.decode()
    assert "%3B" in raw_query and ";" not in raw_query


def test_query_without_options_sends_only_project_and_table(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/data/table").mock(return_value=ok([], count=0))
    page = sds.records.query(3)
    assert dict(route.calls.last.request.url.params) == {"project": PROJECT, "table": "3"}
    assert page.count == 0 and page.records == []


def test_raw_where_string_is_passed_through(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/data/table").mock(return_value=ok([], count=0))
    sds.records.query(3, where="id;equal;5", sort="id;desc", project="other-project")
    params = route.calls.last.request.url.params
    assert params["WhereQuery"] == "id;equal;5"
    assert params["SortQuery"] == "id;desc"
    assert params["project"] == "other-project"


def test_iter_pages_through_everything(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/data/table").mock(side_effect=page_server(25))
    ids = [r["id"] for r in sds.records.iter(1, page_size=10, where=where("active", "=", True))]
    assert ids == list(range(1, 26))
    assert route.call_count == 3
    assert [c.request.url.params["Offset"] for c in route.calls] == ["0", "10", "20"]
    assert all(c.request.url.params["WhereQuery"] == "active;equal;true" for c in route.calls)


def test_iter_stops_on_empty_page_and_empty_table(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/data/table").mock(return_value=ok([], count=0))
    assert list(sds.records.iter(1)) == []
    assert route.call_count == 1
    with pytest.raises(ValueError):
        list(sds.records.iter(1, page_size=0))


async def test_async_iter(asds: AsyncStellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/data/table").mock(side_effect=page_server(7))
    ids = [r["id"] async for r in asds.records.iter(1, page_size=3)]
    assert ids == list(range(1, 8))


def test_get_record(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/data/table").mock(side_effect=[ok([{"id": 9}], count=1), ok([], count=0)])
    assert sds.records.get(1, 9) == {"id": 9}
    assert route.calls.last.request.url.params["WhereQuery"] == "id;equal;9"
    assert sds.records.get(1, 10) is None


def test_create_one_and_many_with_native_values(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.post("/v1/data/table").mock(
        side_effect=[ok([{"id": 1, "price": 1.5}], status=201), ok([{"id": 2}, {"id": 3}], status=201)]
    )
    created = sds.records.create(
        4,
        {
            "price": Decimal("12345678901234.5678"),
            "day": dt.date(2024, 1, 31),
            "at": dt.time(8, 30),
            "when": dt.datetime(2024, 1, 31, 8, 30, tzinfo=dt.timezone.utc),
            "ref": uuid.UUID(int=1),
        },
    )
    assert created == {"id": 1, "price": 1.5}
    body = route.calls[0].request.content.decode()
    assert '"price":12345678901234.5678' in body
    assert json.loads(body) == {
        "records": [
            {
                "price": 12345678901234.5678,
                "day": "2024-01-31",
                "at": "08:30:00",
                "when": "2024-01-31T08:30:00+00:00",
                "ref": "00000000-0000-0000-0000-000000000001",
            }
        ]
    }
    assert route.calls[0].request.headers["Content-Type"] == "application/json"
    many = sds.records.create(4, [{"a": 1}, {"a": 2}])
    assert many == [{"id": 2}, {"id": 3}]
    assert json.loads(route.calls[1].request.content) == {"records": [{"a": 1}, {"a": 2}]}


def test_update_with_ids_and_force(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.put("/v1/data/table").mock(return_value=ok([{"id": 1, "done": True}]))
    assert sds.records.update(4, {"done": True}, ids=[1, 2]) == [{"id": 1, "done": True}]
    request = route.calls.last.request
    assert json.loads(request.content) == {"record": {"done": True}, "idList": [1, 2]}
    assert "force" not in request.url.params
    sds.records.update(4, {"done": False}, force=True)
    request = route.calls.last.request
    assert request.url.params["force"] == "true"
    assert json.loads(request.content) == {"record": {"done": False}}


def test_delete_one_many_and_clear(sds: StellarDS, mock: respx.MockRouter) -> None:
    one = mock.delete("/v1/data/table").mock(return_value=ok())
    many = mock.post("/v1/data/table/delete").mock(return_value=ok())
    clear = mock.delete("/v1/data/table/clear").mock(return_value=ok())
    sds.records.delete(4, 10)
    assert one.calls.last.request.url.params["record"] == "10"
    sds.records.delete_many(4, [1, 2, 3])
    # The server binds the body to string[], so the ids go as strings.
    assert json.loads(many.calls.last.request.content) == ["1", "2", "3"]
    sds.records.delete_many(4, [])
    assert many.call_count == 1
    sds.records.clear(4)
    assert clear.call_count == 1


def test_blob_upload_and_download(sds: StellarDS, mock: respx.MockRouter) -> None:
    upload = mock.post("/v1/data/table/blob").mock(return_value=ok())
    download = mock.get("/v1/data/table/blob").mock(
        return_value=httpx.Response(200, content=b"\x89PNG\r\n", headers={"Content-Type": "application/octet-stream"})
    )
    sds.records.upload_blob(4, 10, "photo", b"\x89PNG\r\n", filename="photo.png", content_type="image/png")
    request = upload.calls.last.request
    assert request.url.params["field"] == "photo" and request.url.params["record"] == "10"
    assert request.headers["Content-Type"].startswith("multipart/form-data")
    assert b'name="data"; filename="photo.png"' in request.content
    assert b"\x89PNG\r\n" in request.content
    assert sds.records.download_blob(4, 10, "photo") == b"\x89PNG\r\n"
    assert download.calls.last.request.url.params["field"] == "photo"


async def test_async_create_and_blob(asds: AsyncStellarDS, mock: respx.MockRouter) -> None:
    mock.post("/v1/data/table").mock(return_value=ok([{"id": 1}], status=201))
    mock.get("/v1/data/table/blob").mock(return_value=httpx.Response(200, content=b"abc"))
    assert await asds.records.create(1, {"a": Decimal("1.10")}) == {"id": 1}
    assert await asds.records.download_blob(1, 1, "f") == b"abc"


def test_custom_query(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.post("/v1/data/query").mock(
        return_value=ok(
            {
                "columns": [{"name": "city", "type": "NVarChar(100)"}],
                "rows": [{"city": "Ghent"}],
                "count": 1,
                "truncated": False,
                "durationMs": 4,
            }
        )
    )
    result = sds.query.execute("select city from Customers where country = @c", {"c": "BE"})
    assert result.columns[0].name == "city"
    assert result.rows == [{"city": "Ghent"}]
    assert result.duration_ms == 4
    assert json.loads(route.calls.last.request.content) == {
        "query": "select city from Customers where country = @c",
        "parameters": {"c": "BE"},
    }
