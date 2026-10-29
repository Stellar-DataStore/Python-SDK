from __future__ import annotations

import asyncio
import datetime as dt
import threading
import time
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from stellards import AsyncStellarDS, AuthenticationError, OAuthCredentials, StellarDS, Tokens

from .conftest import BASE, PROJECT, ok

CLIENT_ID = "8c3e9d7a-2b1f-4e5c-a6d8-9f1e2b3c4d5e"


def token_response(n: int, expires_in: int = 3600) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "access_token": f"access-{n}",
            "refresh_token": f"refresh-{n}",
            "expires_in": expires_in,
            "token_type": "Bearer",
        },
    )


def credentials(**kwargs: object) -> OAuthCredentials:
    return OAuthCredentials(client_id=CLIENT_ID, client_secret="secret", refresh_token="refresh-0", **kwargs)  # type: ignore[arg-type]


def form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_refreshes_before_the_first_request_without_access_token(mock: respx.MockRouter) -> None:
    token_route = mock.post("/v1/oauth/token").mock(return_value=token_response(1))
    api = mock.get("/v1/schema/table").mock(return_value=ok([]))
    seen: list[Tokens] = []
    with StellarDS(oauth=credentials(), base_url=BASE, project=PROJECT, on_tokens=seen.append) as client:
        client.tables.list()
        assert client.access_token == "access-1"
    sent = form(token_route.calls.last.request)
    assert sent == {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": "secret",
        "refresh_token": "refresh-0",
    }
    assert token_route.calls.last.request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert "Authorization" not in token_route.calls.last.request.headers
    assert api.calls.last.request.headers["Authorization"] == "Bearer access-1"
    assert [t.access_token for t in seen] == ["access-1"]
    assert seen[0].refresh_token == "refresh-1"
    assert seen[0].expires_at is not None
    assert seen[0].expires_at > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=59)


def test_refreshes_shortly_before_expiry(mock: respx.MockRouter) -> None:
    token_route = mock.post("/v1/oauth/token").mock(return_value=token_response(2))
    api = mock.get("/v1/schema/table").mock(return_value=ok([]))
    soon = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30)
    later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    with StellarDS(oauth=credentials(access_token="access-1", expires_at=later), base_url=BASE, project=PROJECT) as c:
        c.tables.list()
        assert token_route.call_count == 0
        assert api.calls.last.request.headers["Authorization"] == "Bearer access-1"
    with StellarDS(oauth=credentials(access_token="access-1", expires_at=soon), base_url=BASE, project=PROJECT) as c:
        c.tables.list()
        assert token_route.call_count == 1
        assert api.calls.last.request.headers["Authorization"] == "Bearer access-2"


def test_refreshes_once_on_401_and_retries(mock: respx.MockRouter) -> None:
    mock.post("/v1/oauth/token").mock(return_value=token_response(2))
    api = mock.get("/v1/schema/table").mock(side_effect=[httpx.Response(401), ok([{"id": 1, "name": "A"}])])
    stored: list[str] = []
    with StellarDS(
        oauth=credentials(access_token="access-1"),
        base_url=BASE,
        project=PROJECT,
        on_tokens=lambda t: stored.append(t.refresh_token or ""),
    ) as client:
        tables = client.tables.list()
    assert tables[0].name == "A"
    assert [c.request.headers["Authorization"] for c in api.calls] == ["Bearer access-1", "Bearer access-2"]
    assert stored == ["refresh-2"]


def test_a_second_401_is_raised(mock: respx.MockRouter) -> None:
    token_route = mock.post("/v1/oauth/token").mock(return_value=token_response(2))
    api = mock.get("/v1/schema/table").mock(return_value=httpx.Response(401))
    with (
        StellarDS(oauth=credentials(access_token="access-1"), base_url=BASE, project=PROJECT) as client,
        pytest.raises(AuthenticationError),
    ):
        client.tables.list()
    assert api.call_count == 2
    assert token_route.call_count == 1


def test_static_token_401_is_not_retried(sds: StellarDS, mock: respx.MockRouter) -> None:
    api = mock.get("/v1/schema/table").mock(return_value=httpx.Response(401))
    with pytest.raises(AuthenticationError):
        sds.tables.list()
    assert api.call_count == 1


def test_failed_refresh_raises_authentication_error(mock: respx.MockRouter) -> None:
    mock.post("/v1/oauth/token").mock(return_value=httpx.Response(400, json="invalid refresh token"))
    with (
        StellarDS(oauth=credentials(), base_url=BASE, project=PROJECT) as client,
        pytest.raises(AuthenticationError) as info,
    ):
        client.tables.list()
    assert "invalid refresh token" in str(info.value)
    assert info.value.status == 400


def test_concurrent_401s_share_one_refresh(mock: respx.MockRouter) -> None:
    def token_endpoint(request: httpx.Request) -> httpx.Response:
        time.sleep(0.05)  # let the other threads pile up behind the lock
        return token_response(2)

    token_route = mock.post("/v1/oauth/token").mock(side_effect=token_endpoint)

    def api(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer access-1":
            return httpx.Response(401)
        return ok([])

    mock.get("/v1/schema/table").mock(side_effect=api)
    errors: list[BaseException] = []
    with StellarDS(oauth=credentials(access_token="access-1"), base_url=BASE, project=PROJECT) as client:
        barrier = threading.Barrier(8)

        def work() -> None:
            try:
                barrier.wait()
                client.tables.list()
            except BaseException as error:  # pragma: no cover - reported below
                errors.append(error)

        threads = [threading.Thread(target=work) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert errors == []
    assert token_route.call_count == 1


async def test_async_concurrent_requests_share_one_refresh(mock: respx.MockRouter) -> None:
    async def token_endpoint(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return token_response(2)

    token_route = mock.post("/v1/oauth/token").mock(side_effect=token_endpoint)

    def api(request: httpx.Request) -> httpx.Response:
        if request.headers["Authorization"] == "Bearer access-1":
            return httpx.Response(401)
        return ok([])

    mock.get("/v1/schema/table").mock(side_effect=api)
    stored: list[str] = []

    async def on_tokens(tokens: Tokens) -> None:
        await asyncio.sleep(0)
        stored.append(tokens.access_token)

    async with AsyncStellarDS(
        oauth=credentials(access_token="access-1"), base_url=BASE, project=PROJECT, on_tokens=on_tokens
    ) as client:
        await asyncio.gather(*(client.tables.list() for _ in range(10)))
    assert token_route.call_count == 1
    assert stored == ["access-2"]


async def test_async_proactive_refresh(mock: respx.MockRouter) -> None:
    token_route = mock.post("/v1/oauth/token").mock(return_value=token_response(1))
    api = mock.get("/v1/schema/table").mock(return_value=ok([]))
    async with AsyncStellarDS(oauth=credentials(), base_url=BASE, project=PROJECT) as client:
        await asyncio.gather(client.tables.list(), client.tables.list(), client.tables.list())
    assert token_route.call_count == 1
    assert {c.request.headers["Authorization"] for c in api.calls} == {"Bearer access-1"}


def test_oauth_refresh_and_revoke(mock: respx.MockRouter) -> None:
    mock.post("/v1/oauth/token").mock(return_value=token_response(5))
    revoke = mock.post("/v1/oauth/revoke").mock(return_value=httpx.Response(200))
    with StellarDS(oauth=credentials(access_token="a"), base_url=BASE) as client:
        tokens = client.oauth.refresh()
        assert tokens.access_token == "access-5"
        client.oauth.revoke()
    import json

    assert json.loads(revoke.calls.last.request.content) == {
        "refresh_token": "refresh-5",
        "client_id": CLIENT_ID,
        "client_secret": "secret",
    }


def test_refresh_without_credentials_raises(sds: StellarDS) -> None:
    with pytest.raises(AuthenticationError):
        sds.oauth.refresh()


def test_credentials_repr_hides_secrets() -> None:
    text = repr(credentials())
    assert "secret" not in text.replace("client_secret", "")
    assert "refresh-0" not in text
