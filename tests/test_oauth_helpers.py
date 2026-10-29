from __future__ import annotations

import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from stellards import ApiError, Tokens, oauth

from .conftest import BASE


def test_authorization_url_encodes_everything() -> None:
    url = oauth.authorization_url("cid", "https://app.example.com/cb?x=1&y=2", state="s t&u")
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == oauth.DEFAULT_AUTHORIZE_URL
    assert parse_qs(parts.query) == {
        "response_type": ["code"],
        "client_id": ["cid"],
        "redirect_uri": ["https://app.example.com/cb?x=1&y=2"],
        "state": ["s t&u"],
    }
    assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcb%3Fx%3D1%26y%3D2" in url


def test_authorization_url_custom_and_without_state() -> None:
    url = oauth.authorization_url("cid", "http://localhost:1/cb", authorize_url="https://localhost:7020/oauth?a=b")
    assert url.startswith("https://localhost:7020/oauth?a=b&response_type=code")
    assert "state" not in url


def test_add_state_and_generate_state() -> None:
    assert oauth.add_state("http://127.0.0.1:8080/cb", "abc") == "http://127.0.0.1:8080/cb?state=abc"
    assert oauth.add_state("http://127.0.0.1:8080/cb?x=1", "a b") == "http://127.0.0.1:8080/cb?x=1&state=a+b"
    a, b = oauth.generate_state(), oauth.generate_state()
    assert a != b and len(a) >= 32


def test_exchange_code_and_refresh(mock: respx.MockRouter) -> None:
    route = mock.post("/v1/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "a", "refresh_token": "r", "expires_in": 3570})
    )
    tokens = oauth.exchange_code("cid", "sec", "code-1", "https://app/cb", base_url=BASE)
    assert tokens.access_token == "a" and tokens.refresh_token == "r" and tokens.expires_at is not None
    form = {k: v[0] for k, v in parse_qs(route.calls.last.request.content.decode()).items()}
    assert form == {
        "grant_type": "authorization_code",
        "client_id": "cid",
        "client_secret": "sec",
        "code": "code-1",
        "redirect_uri": "https://app/cb",
    }
    oauth.refresh_tokens("cid", "sec", "r", base_url=BASE)
    form = {k: v[0] for k, v in parse_qs(route.calls.last.request.content.decode()).items()}
    assert form["grant_type"] == "refresh_token" and form["refresh_token"] == "r"


async def test_async_exchange_code(mock: respx.MockRouter) -> None:
    mock.post("/v1/oauth/token").mock(return_value=httpx.Response(200, json={"access_token": "a", "expires_in": 5}))
    tokens = await oauth.exchange_code_async("cid", "sec", "c", "https://app/cb", base_url=BASE)
    assert tokens.access_token == "a"
    tokens = await oauth.refresh_tokens_async("cid", "sec", "r", base_url=BASE)
    assert tokens.access_token == "a"


def test_exchange_code_error(mock: respx.MockRouter) -> None:
    mock.post("/v1/oauth/token").mock(return_value=httpx.Response(400, json="Invalid authorization code"))
    with pytest.raises(ApiError, match="Invalid authorization code"):
        oauth.exchange_code("cid", "sec", "bad", "https://app/cb", base_url=BASE)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_wait_for_callback_returns_the_query() -> None:
    port = _free_port()
    redirect = f"http://127.0.0.1:{port}/callback"
    responses: list[httpx.Response] = []

    def visit() -> None:
        with httpx.Client() as client:
            responses.append(client.get(f"http://127.0.0.1:{port}/favicon.ico"))
            responses.append(client.get(f"{redirect}?state=abc&code=xyz"))

    params = oauth.wait_for_callback(redirect, timeout=10, ready=lambda: threading.Thread(target=visit).start())
    assert params == {"state": ["abc"], "code": ["xyz"]}


def test_authorize_in_browser_checks_state(monkeypatch: pytest.MonkeyPatch) -> None:
    exchanged: dict[str, Any] = {}

    def fake_exchange(client_id: str, client_secret: str, code: str, redirect_uri: str, **kwargs: Any) -> Tokens:
        exchanged.update(client_id=client_id, code=code, redirect_uri=redirect_uri)
        return Tokens(access_token="a")

    monkeypatch.setattr(oauth, "exchange_code", fake_exchange)
    port = _free_port()
    redirect = f"http://127.0.0.1:{port}/cb"

    def browser(url: str) -> None:
        # Act as the sign-in page: redirect to the redirect_uri (which carries the state) with a code,
        # the way the server does today (it appends an empty state of its own).
        target = parse_qs(urlsplit(url).query)["redirect_uri"][0]
        threading.Thread(target=lambda: httpx.get(f"{target}&code=the-code&state=")).start()

    tokens = oauth.authorize_in_browser("cid", "sec", redirect, open_browser=False, on_url=browser, timeout=10)
    assert tokens.access_token == "a"
    assert exchanged["code"] == "the-code"
    assert exchanged["redirect_uri"].startswith(redirect + "?state=")


def test_authorize_in_browser_rejects_wrong_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth, "exchange_code", lambda *a, **k: pytest.fail("must not exchange"))
    port = _free_port()
    redirect = f"http://127.0.0.1:{port}/cb"

    def browser(url: str) -> None:
        threading.Thread(target=lambda: httpx.get(f"{redirect}?state=forged&code=c")).start()

    with pytest.raises(oauth.OAuthCallbackError, match="state"):
        oauth.authorize_in_browser("cid", "sec", redirect, open_browser=False, on_url=browser, timeout=10)


def test_loopback_only() -> None:
    with pytest.raises(ValueError):
        oauth.wait_for_callback("https://example.com:8080/cb", timeout=1)
    with pytest.raises(ValueError):
        oauth.wait_for_callback("http://127.0.0.1/cb", timeout=1)


def test_async_resources_are_generated_from_the_sync_ones() -> None:
    script = Path(__file__).resolve().parent.parent / "scripts" / "generate_async.py"
    result = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
