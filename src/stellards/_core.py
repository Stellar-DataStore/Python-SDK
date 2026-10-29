"""Request building, response handling and token management shared by the sync and async clients."""

from __future__ import annotations

import asyncio
import datetime as _dt
import email.utils
import inspect
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar, Union

import httpx

from . import _json
from ._version import __version__
from .errors import (
    ApiConnectionError,
    ApiError,
    ApiTimeoutError,
    AuthenticationError,
    Message,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    StellarDSError,
)
from .models import Tokens

__all__ = ["ApiRequest", "OAuthCredentials", "SyncCore", "AsyncCore", "DEFAULT_BASE_URL", "DEFAULT_TIMEOUT"]

T = TypeVar("T")

DEFAULT_BASE_URL = "https://api.stellards.io"
DEFAULT_TIMEOUT = 30.0
#: Refresh this long before the access token expires.
REFRESH_MARGIN = _dt.timedelta(seconds=60)

TimeoutTypes = Union[float, httpx.Timeout, None]
ProjectId = Union[str, uuid.UUID]
TokensCallback = Callable[[Tokens], Any]


class _Unset:
    def __repr__(self) -> str:
        return "UNSET"


UNSET: Any = _Unset()


def _identity(value: Any) -> Any:
    return value


@dataclass
class ApiRequest(Generic[T]):
    """Everything needed to make one API call and turn its response into a Python value."""

    method: str
    path: str
    params: Mapping[str, Any] | None = None
    json: Any = UNSET
    form: Mapping[str, str] | None = None
    files: Any = None
    #: Turns the unwrapped ``data`` (or the whole body when ``unwrap`` is false) into the result.
    parse: Callable[[Any], T] = _identity
    #: Hand ``parse`` the envelope's ``data`` (true) or the whole parsed body (false).
    unwrap: bool = True
    #: Return the response body as bytes (blob downloads).
    raw: bool = False
    #: Send the access token.
    authenticated: bool = True


@dataclass
class OAuthCredentials:
    """What the client needs to refresh access tokens by itself.

    ``access_token`` and ``expires_at`` are optional: without them the client refreshes before its first request.
    """

    client_id: str
    client_secret: str
    refresh_token: str
    access_token: str | None = None
    expires_at: _dt.datetime | None = None

    def __repr__(self) -> str:  # keep secrets out of logs and tracebacks
        return f"OAuthCredentials(client_id={self.client_id!r}, client_secret='***', refresh_token='***')"


# --------------------------------------------------------------------------------------------------- helpers


def _param_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, _dt.datetime):
        return _json.format_datetime(value)
    if isinstance(value, _dt.date):
        return value.isoformat()
    return str(value)


def clean_params(params: Mapping[str, Any] | None) -> dict[str, str]:
    return {k: _param_value(v) for k, v in (params or {}).items() if v is not None}


def _messages_from(body: Any) -> list[Message]:
    if isinstance(body, Mapping):
        raw = body.get("messages")
        if isinstance(raw, list):
            return [Message.from_wire(m) for m in raw]
        # ASP.NET's validation problem details: {"title": ..., "errors": {"Field": ["message", ...]}}
        errors = body.get("errors")
        if isinstance(errors, Mapping):
            out = []
            for key, values in errors.items():
                for value in values if isinstance(values, list) else [values]:
                    out.append(Message(message=str(value), code=str(key)))
            return out
        title = body.get("title") or body.get("message") or body.get("error_description") or body.get("error")
        if title:
            return [Message(message=str(title))]
        return []
    if isinstance(body, list):
        return [Message.from_wire(m) for m in body]
    if isinstance(body, str) and body.strip():
        return [Message(message=body.strip()[:1000])]
    return []


def _retry_after(headers: httpx.Headers) -> float | None:
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return max(0.0, (when - _dt.datetime.now(_dt.timezone.utc)).total_seconds())


def error_for(status: int, body: Any, headers: httpx.Headers, reason: str = "") -> ApiError:
    messages = _messages_from(body)
    detail = "; ".join(m.message for m in messages if m.message) or reason or "request failed"
    text = f"{status} {detail}" if status else detail
    kwargs: dict[str, Any] = {"status": status, "messages": messages, "body": body}
    if status == 401:
        return AuthenticationError(text, **kwargs)
    if status == 403:
        return PermissionDeniedError(text, **kwargs)
    if status == 404:
        return NotFoundError(text, **kwargs)
    if status == 429:
        return RateLimitError(text, retry_after=_retry_after(headers), **kwargs)
    return ApiError(text, **kwargs)


def _decode_body(response: httpx.Response, parse_decimals: bool) -> Any:
    content = response.content
    if not content or not content.strip():
        return None
    try:
        return _json.loads(content, parse_decimals=parse_decimals)
    except ValueError:
        try:
            return content.decode(response.encoding or "utf-8", errors="replace")
        except LookupError:
            return content.decode("utf-8", errors="replace")


def process_response(request: ApiRequest[T], response: httpx.Response, parse_decimals: bool = False) -> T:
    """Unwraps the envelope, or raises the matching :class:`~stellards.StellarDSError`."""
    status = response.status_code
    if request.raw and 200 <= status < 300:
        return request.parse(response.content)
    body = _decode_body(response, parse_decimals)
    if status >= 400 or status < 200:
        raise error_for(status, body, response.headers, response.reason_phrase)
    if isinstance(body, Mapping) and body.get("isSuccess") is False:
        raise error_for(status, body, response.headers, "the server reported the request as failed")
    if not request.unwrap:
        return request.parse(body)
    if isinstance(body, Mapping) and ("isSuccess" in body or "messages" in body) and "data" in body:
        return request.parse(body["data"])
    if isinstance(body, Mapping) and "isSuccess" in body:
        return request.parse(None)
    return request.parse(body)


# --------------------------------------------------------------------------------------------------- token state


@dataclass
class _TokenState:
    access_token: str | None
    credentials: OAuthCredentials | None
    on_tokens: TokensCallback | None
    expires_at: _dt.datetime | None = None
    refresh_token: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.credentials is not None:
            self.refresh_token = self.credentials.refresh_token
            self.access_token = self.credentials.access_token or self.access_token
            self.expires_at = self.credentials.expires_at

    @property
    def can_refresh(self) -> bool:
        return self.credentials is not None and bool(self.refresh_token)

    def needs_refresh(self, now: _dt.datetime | None = None) -> bool:
        if not self.can_refresh:
            return False
        if not self.access_token:
            return True
        if self.expires_at is None:
            return False
        moment = now or _dt.datetime.now(_dt.timezone.utc)
        expires = self.expires_at if self.expires_at.tzinfo else self.expires_at.replace(tzinfo=_dt.timezone.utc)
        return moment >= expires - REFRESH_MARGIN

    def refresh_request(self) -> ApiRequest[Tokens]:
        assert self.credentials is not None and self.refresh_token
        return token_request(
            {
                "grant_type": "refresh_token",
                "client_id": str(self.credentials.client_id),
                "client_secret": self.credentials.client_secret,
                "refresh_token": self.refresh_token,
            }
        )

    def apply(self, tokens: Tokens) -> None:
        self.access_token = tokens.access_token
        if tokens.refresh_token:
            self.refresh_token = tokens.refresh_token
            if self.credentials is not None:
                self.credentials.refresh_token = tokens.refresh_token
        self.expires_at = tokens.expires_at
        if self.credentials is not None:
            self.credentials.access_token = tokens.access_token
            self.credentials.expires_at = tokens.expires_at


def token_request(form: Mapping[str, str]) -> ApiRequest[Tokens]:
    return ApiRequest(
        "POST",
        "/v1/oauth/token",
        form=dict(form),
        parse=Tokens.from_response,
        unwrap=False,
        authenticated=False,
    )


def _refresh_failed(error: StellarDSError) -> AuthenticationError:
    return AuthenticationError(
        f"Refreshing the access token failed: {error.message}",
        status=error.status,
        messages=error.messages,
        body=error.body,
    )


# --------------------------------------------------------------------------------------------------- cores


class _BaseCore:
    def __init__(
        self,
        *,
        access_token: str | None,
        oauth: OAuthCredentials | None,
        base_url: str,
        timeout: TimeoutTypes,
        on_tokens: TokensCallback | None,
        project: ProjectId | None,
        parse_decimals: bool,
        headers: Mapping[str, str] | None,
    ) -> None:
        if access_token is None and oauth is None:
            raise ValueError("pass access_token=... or oauth=OAuthCredentials(...)")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.project = None if project is None else str(project)
        self.parse_decimals = parse_decimals
        self.headers = {
            "Accept": "application/json",
            "User-Agent": f"stellards-python/{__version__}",
            **(headers or {}),
        }
        self.tokens = _TokenState(access_token=access_token, credentials=oauth, on_tokens=on_tokens)

    def build(self, request: ApiRequest[Any], token: str | None) -> httpx.Request:
        headers = dict(self.headers)
        if request.authenticated and token:
            headers["Authorization"] = f"Bearer {token}"
        content: bytes | None = None
        if request.json is not UNSET:
            content = _json.dumps(request.json).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if request.raw:
            headers["Accept"] = "*/*"
        return httpx.Request(
            request.method,
            self.base_url + request.path,
            params=clean_params(request.params),
            headers=headers,
            content=content,
            data=dict(request.form) if request.form is not None else None,
            files=request.files,
            extensions={"timeout": httpx.Timeout(self.timeout).as_dict()},
        )


def _transport_error(error: httpx.TransportError) -> StellarDSError:
    if isinstance(error, httpx.TimeoutException):
        return ApiTimeoutError(f"The request timed out: {error}")
    return ApiConnectionError(f"Could not reach StellarDS: {error}")


class SyncCore(_BaseCore):
    def __init__(self, *, http_client: httpx.Client | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._owns_client = http_client is None
        self.http = http_client or httpx.Client(timeout=self.timeout)
        self._lock = threading.Lock()

    def close(self) -> None:
        if self._owns_client:
            self.http.close()

    def _send(self, request: ApiRequest[Any], token: str | None) -> httpx.Response:
        try:
            return self.http.send(self.build(request, token))
        except httpx.TransportError as error:
            raise _transport_error(error) from error

    def _notify(self, tokens: Tokens) -> None:
        if self.tokens.on_tokens is not None:
            self.tokens.on_tokens(tokens)

    def _do_refresh(self) -> Tokens:
        request = self.tokens.refresh_request()
        try:
            tokens = process_response(request, self._send(request, None))
        except AuthenticationError:
            raise
        except ApiError as error:
            raise _refresh_failed(error) from error
        self.tokens.apply(tokens)
        self._notify(tokens)
        return tokens

    def refresh(self, failed_token: str | None = None, *, force: bool = False) -> Tokens | None:
        """Refreshes the access token, once for all callers that saw the same token fail."""
        if not self.tokens.can_refresh:
            if force:
                raise AuthenticationError("No OAuth credentials to refresh with: pass oauth=OAuthCredentials(...)")
            return None
        with self._lock:
            if not force:
                if failed_token is not None and self.tokens.access_token != failed_token:
                    return None  # another request refreshed it meanwhile
                if failed_token is None and not self.tokens.needs_refresh():
                    return None
            return self._do_refresh()

    def request(self, request: ApiRequest[T]) -> T:
        if request.authenticated and self.tokens.needs_refresh():
            self.refresh()
        token = self.tokens.access_token
        response = self._send(request, token)
        if response.status_code == 401 and request.authenticated and self.tokens.can_refresh:
            response.close()
            self.refresh(failed_token=token or "")
            response = self._send(request, self.tokens.access_token)
        return process_response(request, response, self.parse_decimals)


class AsyncCore(_BaseCore):
    def __init__(self, *, http_client: httpx.AsyncClient | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._owns_client = http_client is None
        self.http = http_client or httpx.AsyncClient(timeout=self.timeout)
        self._lock: asyncio.Lock | None = None

    async def close(self) -> None:
        if self._owns_client:
            await self.http.aclose()

    def _get_lock(self) -> asyncio.Lock:
        # Created on first use, inside the running loop (asyncio.Lock binds to a loop on Python 3.9).
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def _send(self, request: ApiRequest[Any], token: str | None) -> httpx.Response:
        try:
            return await self.http.send(self.build(request, token))
        except httpx.TransportError as error:
            raise _transport_error(error) from error

    async def _notify(self, tokens: Tokens) -> None:
        if self.tokens.on_tokens is not None:
            result = self.tokens.on_tokens(tokens)
            if inspect.isawaitable(result):
                await result

    async def _do_refresh(self) -> Tokens:
        request = self.tokens.refresh_request()
        try:
            tokens = process_response(request, await self._send(request, None))
        except AuthenticationError:
            raise
        except ApiError as error:
            raise _refresh_failed(error) from error
        self.tokens.apply(tokens)
        await self._notify(tokens)
        return tokens

    async def refresh(self, failed_token: str | None = None, *, force: bool = False) -> Tokens | None:
        if not self.tokens.can_refresh:
            if force:
                raise AuthenticationError("No OAuth credentials to refresh with: pass oauth=OAuthCredentials(...)")
            return None
        async with self._get_lock():
            if not force:
                if failed_token is not None and self.tokens.access_token != failed_token:
                    return None
                if failed_token is None and not self.tokens.needs_refresh():
                    return None
            return await self._do_refresh()

    async def request(self, request: ApiRequest[T]) -> T:
        if request.authenticated and self.tokens.needs_refresh():
            await self.refresh()
        token = self.tokens.access_token
        response = await self._send(request, token)
        if response.status_code == 401 and request.authenticated and self.tokens.can_refresh:
            await response.aclose()
            await self.refresh(failed_token=token or "")
            response = await self._send(request, self.tokens.access_token)
        return process_response(request, response, self.parse_decimals)
