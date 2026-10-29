from __future__ import annotations

import httpx
import pytest
import respx

from stellards import (
    ApiConnectionError,
    ApiError,
    ApiTimeoutError,
    AsyncStellarDS,
    AuthenticationError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    StellarDS,
    StellarDSError,
    Table,
)

from .conftest import BASE, PROJECT, envelope, ok


def test_unwraps_data_and_sends_auth_and_headers(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/schema/table").mock(
        return_value=ok([{"id": 7, "name": "Orders", "isMultitenant": True, "unknownNewField": {"x": 1}}])
    )
    tables = sds.tables.list()
    assert tables == [Table(id=7, name="Orders", description=None, is_multitenant=True)]
    assert tables[0].raw["unknownNewField"] == {"x": 1}
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer static-token"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-Agent"].startswith("stellards-python/")
    assert request.url.params["project"] == PROJECT


async def test_async_unwraps_data(asds: AsyncStellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/table").mock(return_value=ok([{"id": 1, "name": "A"}]))
    tables = await asds.tables.list()
    assert [t.name for t in tables] == ["A"]


def test_is_success_false_raises_even_with_200(sds: StellarDS, mock: respx.MockRouter) -> None:
    body = envelope(None, success=False, messages=[{"code": "400", "message": "Name is taken", "type": 30}])
    mock.post("/v1/schema/table").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(ApiError) as info:
        sds.tables.create("Orders")
    assert info.value.status == 200
    assert info.value.messages[0].message == "Name is taken"
    assert info.value.messages[0].code == "400"
    assert info.value.messages[0].type == 30
    assert info.value.body == body


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (400, ApiError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ApiError),
        (429, RateLimitError),
        (500, ApiError),
    ],
)
def test_status_codes_map_to_typed_errors(
    sds: StellarDS, mock: respx.MockRouter, status: int, error_type: type[ApiError]
) -> None:
    body = envelope(None, success=False, messages=[{"code": str(status), "message": "nope", "type": 30}])
    mock.get("/v1/schema/table").mock(return_value=httpx.Response(status, json=body))
    with pytest.raises(error_type) as info:
        sds.tables.list()
    assert type(info.value) is error_type
    assert isinstance(info.value, StellarDSError)
    assert info.value.status == status
    assert [m.message for m in info.value.messages] == ["nope"]
    assert str(info.value) == f"{status} nope"


def test_rate_limit_reads_retry_after(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/table").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "12"}, json=envelope(success=False))
    )
    with pytest.raises(RateLimitError) as info:
        sds.tables.list()
    assert info.value.retry_after == 12.0


def test_non_json_error_page_does_not_crash(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/table").mock(
        return_value=httpx.Response(
            502, text="<html><body>Bad gateway</body></html>", headers={"Content-Type": "text/html"}
        )
    )
    with pytest.raises(ApiError) as info:
        sds.tables.list()
    assert info.value.status == 502
    assert "Bad gateway" in str(info.value.body)


def test_plain_string_error_body(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.post("/v1/oauth/revoke").mock(return_value=httpx.Response(400, json="Refresh token not found"))
    with pytest.raises(ApiError) as info:
        sds.oauth.revoke("r", client_id="c", client_secret="s")
    assert info.value.messages[0].message == "Refresh token not found"


def test_validation_problem_details(sds: StellarDS, mock: respx.MockRouter) -> None:
    problem = {"title": "One or more validation errors occurred.", "status": 400, "errors": {"Name": ["Required"]}}
    mock.post("/v1/schema/table").mock(return_value=httpx.Response(400, json=problem))
    with pytest.raises(ApiError) as info:
        sds.tables.create("")
    assert info.value.messages[0].code == "Name"
    assert info.value.messages[0].message == "Required"


def test_empty_body_and_204(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.delete("/v1/schema/table").mock(return_value=httpx.Response(204))
    sds.tables.delete(5)
    mock.delete("/v1/data/table/clear").mock(return_value=httpx.Response(200, content=b""))
    sds.records.clear(5)


def test_empty_error_body(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/table").mock(return_value=httpx.Response(404))
    with pytest.raises(NotFoundError) as info:
        sds.tables.get(5)
    assert info.value.body is None
    assert info.value.messages == []


def test_envelope_without_data(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.delete("/v1/webhooks/3").mock(return_value=httpx.Response(200, json={"isSuccess": True, "messages": []}))
    sds.webhooks.delete(3)


def test_ping_returns_the_bare_string(sds: StellarDS, mock: respx.MockRouter) -> None:
    route = mock.get("/v1/ping").mock(return_value=httpx.Response(200, json="pong"))
    assert sds.ping() == "pong"
    assert "Authorization" not in route.calls.last.request.headers


def test_connection_errors_are_wrapped(sds: StellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/table").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(ApiConnectionError):
        sds.tables.list()
    mock.get("/v1/schema/project").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ApiTimeoutError):
        sds.projects.list()


async def test_async_errors(asds: AsyncStellarDS, mock: respx.MockRouter) -> None:
    mock.get("/v1/schema/table").mock(return_value=httpx.Response(403, json=envelope(success=False)))
    with pytest.raises(PermissionDeniedError):
        await asds.tables.list()
    mock.get("/v1/schema/project").mock(side_effect=httpx.ConnectTimeout("slow"))
    with pytest.raises(ApiTimeoutError):
        await asds.projects.list()


def test_default_timeout_and_custom_timeout(mock: respx.MockRouter) -> None:
    route = mock.get("/v1/ping").mock(return_value=httpx.Response(200, json="pong"))
    with StellarDS("t", base_url=BASE) as client:
        client.ping()
    assert route.calls.last.request.extensions["timeout"]["read"] == 30.0
    with StellarDS("t", base_url=BASE, timeout=2.5) as client:
        client.ping()
    assert route.calls.last.request.extensions["timeout"]["read"] == 2.5


def test_missing_credentials_and_project() -> None:
    with pytest.raises(ValueError):
        StellarDS()
    with StellarDS("t", base_url=BASE) as client, pytest.raises(ValueError, match="project"):
        client.tables.list()


def test_parse_decimals_option(mock: respx.MockRouter) -> None:
    from decimal import Decimal

    mock.get("/v1/data/table").mock(
        return_value=httpx.Response(
            200, content=b'{"data":[{"id":1,"price":12345678901234.5678}],"count":1,"isSuccess":true}'
        )
    )
    with StellarDS("t", base_url=BASE, project=PROJECT, parse_decimals=True) as client:
        page = client.records.query(1)
    assert page.records[0]["price"] == Decimal("12345678901234.5678")


def test_uses_a_supplied_http_client_and_leaves_it_open(mock: respx.MockRouter) -> None:
    mock.get("/v1/ping").mock(return_value=httpx.Response(200, json="pong"))
    http = httpx.Client()
    with StellarDS("t", base_url=BASE, http_client=http) as client:
        assert client.ping() == "pong"
    assert not http.is_closed
    http.close()
