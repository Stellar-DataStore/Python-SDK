"""The OAuth 2.0 authorization-code flow.

1. Send the user to :func:`authorization_url`. They sign in on StellarDS and are redirected to your
   ``redirect_uri`` with ``?code=...``.
2. Exchange the code with :func:`exchange_code` (or :func:`exchange_code_async`) for :class:`~stellards.Tokens`.
3. Create the client with ``oauth=OAuthCredentials(client_id, client_secret, tokens.refresh_token, ...)`` and an
   ``on_tokens`` callback that stores the new tokens whenever the client refreshes them.

For scripts and desktop tools, :func:`authorize_in_browser` does steps 1 and 2 with a short-lived local web server.

The SDK never writes tokens to disk: persisting them (e.g. in your OS keychain or database) is up to ``on_tokens``.
"""

from __future__ import annotations

import html
import http.server
import secrets
import threading
import webbrowser
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

from ._core import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    TimeoutTypes,
    _transport_error,
    process_response,
    token_request,
)
from .errors import StellarDSError
from .models import Tokens

__all__ = [
    "DEFAULT_AUTHORIZE_URL",
    "generate_state",
    "authorization_url",
    "add_state",
    "exchange_code",
    "exchange_code_async",
    "refresh_tokens",
    "refresh_tokens_async",
    "authorize_in_browser",
    "OAuthCallbackError",
]

#: StellarDS's sign-in page for OAuth clients.
DEFAULT_AUTHORIZE_URL = "https://stellards.io/oauth"


class OAuthCallbackError(StellarDSError):
    """The redirect back from the sign-in page was missing its code, or its ``state`` didn't match."""


def generate_state() -> str:
    """A random, URL-safe value for the ``state`` parameter."""
    return secrets.token_urlsafe(24)


def authorization_url(
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
    *,
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
) -> str:
    """The URL of StellarDS's sign-in page for your OAuth client.

    ``redirect_uri`` must match one of the client's registered redirect URLs. Pass a ``state`` (see
    :func:`generate_state`) and check it when the user comes back.

    Note: the StellarDS server currently doesn't send a ``state`` parameter back to the redirect URI. To get one
    back, put it in the redirect URI itself with :func:`add_state` (it still matches the registered URL, which only
    has to be part of it) and use that same redirect URI when exchanging the code.
    """
    query = {"response_type": "code", "client_id": str(client_id), "redirect_uri": redirect_uri}
    if state is not None:
        query["state"] = state
    separator = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{separator}{urlencode(query)}"


def add_state(redirect_uri: str, state: str) -> str:
    """``redirect_uri`` with ``state=<state>`` added to its query."""
    parts = urlsplit(redirect_uri)
    query = parts.query + ("&" if parts.query else "") + urlencode({"state": state})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _code_form(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, str]:
    return {
        "grant_type": "authorization_code",
        "client_id": str(client_id),
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }


def _refresh_form(client_id: str, client_secret: str, refresh_token: str) -> dict[str, str]:
    return {
        "grant_type": "refresh_token",
        "client_id": str(client_id),
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }


def _post_sync(form: dict[str, str], base_url: str, timeout: TimeoutTypes, http_client: httpx.Client | None) -> Tokens:
    request = token_request(form)
    client = http_client or httpx.Client(timeout=timeout)
    try:
        response = client.post(base_url.rstrip("/") + request.path, data=form, headers={"Accept": "application/json"})
    except httpx.TransportError as error:
        raise _transport_error(error) from error
    finally:
        if http_client is None:
            client.close()
    return process_response(request, response)


async def _post_async(
    form: dict[str, str], base_url: str, timeout: TimeoutTypes, http_client: httpx.AsyncClient | None
) -> Tokens:
    request = token_request(form)
    client = http_client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await client.post(
            base_url.rstrip("/") + request.path, data=form, headers={"Accept": "application/json"}
        )
    except httpx.TransportError as error:
        raise _transport_error(error) from error
    finally:
        if http_client is None:
            await client.aclose()
    return process_response(request, response)


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: TimeoutTypes = DEFAULT_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> Tokens:
    """Exchanges an authorization code for tokens. ``redirect_uri`` must be the one used for the sign-in."""
    return _post_sync(_code_form(client_id, client_secret, code, redirect_uri), base_url, timeout, http_client)


async def exchange_code_async(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: TimeoutTypes = DEFAULT_TIMEOUT,
    http_client: httpx.AsyncClient | None = None,
) -> Tokens:
    """The async version of :func:`exchange_code`."""
    return await _post_async(_code_form(client_id, client_secret, code, redirect_uri), base_url, timeout, http_client)


def refresh_tokens(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: TimeoutTypes = DEFAULT_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> Tokens:
    """New tokens for a refresh token. (A client created with ``oauth=...`` does this by itself.)"""
    return _post_sync(_refresh_form(client_id, client_secret, refresh_token), base_url, timeout, http_client)


async def refresh_tokens_async(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: TimeoutTypes = DEFAULT_TIMEOUT,
    http_client: httpx.AsyncClient | None = None,
) -> Tokens:
    """The async version of :func:`refresh_tokens`."""
    return await _post_async(_refresh_form(client_id, client_secret, refresh_token), base_url, timeout, http_client)


# --------------------------------------------------------------------------------------------------- loopback


_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}

_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{title}</title></head>
<body style="font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem">
<h1>{title}</h1><p>{text}</p></body></html>"""


def wait_for_callback(
    redirect_uri: str, *, timeout: float = 300.0, ready: Callable[[], Any] | None = None
) -> dict[str, list[str]]:
    """Serves one request on the loopback ``redirect_uri`` and returns its query parameters.

    ``ready`` is called once the server listens (e.g. to open the browser).
    """
    parts = urlsplit(redirect_uri)
    host = parts.hostname or ""
    if parts.scheme != "http" or host not in _LOOPBACK_HOSTS:
        raise ValueError("the redirect URI must be http://localhost:<port>/..., http://127.0.0.1:<port>/... or [::1]")
    if parts.port is None:
        raise ValueError("the redirect URI needs an explicit port, e.g. http://127.0.0.1:8080/callback")
    path = parts.path or "/"
    result: dict[str, list[str]] = {}
    done = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlsplit(self.path)
            if request.path != path:
                self.send_error(404)
                return
            result.update(parse_qs(request.query, keep_blank_values=False))
            ok = "code" in result
            title = "Signed in" if ok else "Sign-in failed"
            text = (
                "You can close this window and go back to the application."
                if ok
                else "No authorization code came back."
            )
            body = _PAGE.format(title=html.escape(title), text=html.escape(text)).encode("utf-8")
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, format: str, *args: Any) -> None:
            return

    bind_host = "::1" if host in ("::1", "[::1]") else ("127.0.0.1" if host == "localhost" else host)
    server_class = http.server.HTTPServer
    if ":" in bind_host:
        import socket

        class V6Server(http.server.HTTPServer):
            address_family = socket.AF_INET6

        server_class = V6Server
    with server_class((bind_host, parts.port), Handler) as server:
        server.timeout = 0.5
        if ready is not None:
            ready()
        thread_deadline = threading.Timer(timeout, done.set)
        thread_deadline.daemon = True
        thread_deadline.start()
        try:
            while not done.is_set():
                server.handle_request()
        finally:
            thread_deadline.cancel()
    if not result:
        raise OAuthCallbackError(f"No redirect arrived on {redirect_uri} within {timeout:g} seconds")
    return result


def authorize_in_browser(
    client_id: str,
    client_secret: str,
    redirect_uri: str = "http://127.0.0.1:8080/callback",
    *,
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
    base_url: str = DEFAULT_BASE_URL,
    open_browser: bool = True,
    timeout: float = 300.0,
    http_timeout: TimeoutTypes = DEFAULT_TIMEOUT,
    on_url: Callable[[str], Any] | None = None,
) -> Tokens:
    """Signs the user in through their browser and returns the tokens (for scripts and desktop tools).

    Listens on the loopback ``redirect_uri`` (which must be registered for the client, with its port), opens the
    sign-in page (or hands its URL to ``on_url``), checks the ``state`` that comes back and exchanges the code.
    """
    state = generate_state()
    # The server doesn't return the state parameter, so it travels inside the redirect URI.
    redirect_with_state = add_state(redirect_uri, state)
    url = authorization_url(client_id, redirect_with_state, state, authorize_url=authorize_url)

    def ready() -> None:
        if on_url is not None:
            on_url(url)
        if open_browser:
            webbrowser.open(url)

    params = wait_for_callback(redirect_uri, timeout=timeout, ready=ready)
    if state not in params.get("state", []):
        raise OAuthCallbackError("The state that came back doesn't match: the redirect wasn't for this sign-in")
    codes = params.get("code")
    if not codes:
        raise OAuthCallbackError("The redirect has no authorization code")
    return exchange_code(
        client_id, client_secret, codes[0], redirect_with_state, base_url=base_url, timeout=http_timeout
    )
