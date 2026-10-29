"""Exceptions raised by the StellarDS SDK."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Message",
    "StellarDSError",
    "ApiError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "RateLimitError",
    "ApiConnectionError",
    "ApiTimeoutError",
    "WebhookSignatureError",
]


@dataclass(frozen=True)
class Message:
    """One entry of the ``messages`` list StellarDS returns with every response."""

    message: str | None = None
    code: str | None = None
    type: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_wire(cls, value: Any) -> Message:
        if isinstance(value, Mapping):
            code = value.get("code")
            type_ = value.get("type")
            message = value.get("message")
            return cls(
                message=None if message is None else str(message),
                code=None if code is None else str(code),
                type=type_ if isinstance(type_, int) and not isinstance(type_, bool) else None,
                raw=dict(value),
            )
        return cls(message=str(value))


class StellarDSError(Exception):
    """Base class of every error the SDK raises.

    Attributes:
        status: the HTTP status code, or ``None`` when no response was received.
        messages: the ``messages`` StellarDS returned, if any.
        body: the raw response body (parsed JSON when it was JSON, else text), or ``None``.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        messages: Sequence[Message] = (),
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.messages: list[Message] = list(messages)
        self.body = body

    @property
    def message(self) -> str:
        return str(self.args[0]) if self.args else ""


class ApiError(StellarDSError):
    """StellarDS answered with an error status, or with ``isSuccess: false``."""


class AuthenticationError(ApiError):
    """401: the access token is missing, invalid or expired and could not be refreshed."""


class PermissionDeniedError(ApiError):
    """403: the token is valid but lacks the permission for this operation."""


class NotFoundError(ApiError):
    """404: the project, table, field, record or other object doesn't exist (or isn't visible to you)."""


class RateLimitError(ApiError):
    """429: too many requests for the project's tier.

    ``retry_after`` holds the ``Retry-After`` header in seconds when the server sent one.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        messages: Sequence[Message] = (),
        body: Any = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status=status, messages=messages, body=body)
        self.retry_after = retry_after


class ApiConnectionError(StellarDSError):
    """The request could not be sent or no response came back (DNS, refused connection, TLS, ...)."""


class ApiTimeoutError(ApiConnectionError):
    """The request took longer than the configured timeout."""


class WebhookSignatureError(StellarDSError):
    """A webhook delivery's signature is missing, malformed, expired or doesn't match."""
