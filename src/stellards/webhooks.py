"""Verifying webhook deliveries.

StellarDS signs every delivery with the webhook's secret. The ``StellarDS-Signature`` header looks like
``t=<unix seconds>,v1=<hex>[,v1=<hex>...]``: ``hex`` is the HMAC-SHA256 of ``"<t>.<raw body>"`` keyed with the whole
``whsec_...`` secret, and during a secret rotation there is one ``v1`` per valid secret.

Always verify the raw body exactly as received, before parsing it. A delivery can arrive more than once: deduplicate
on the ``StellarDS-Event-Id`` header (the same value as the event's ``id``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any

from .errors import WebhookSignatureError

__all__ = [
    "SIGNATURE_HEADER",
    "EVENT_ID_HEADER",
    "DEFAULT_TOLERANCE",
    "verify_signature",
    "construct_event",
    "compute_signature",
]

SIGNATURE_HEADER = "StellarDS-Signature"
EVENT_ID_HEADER = "StellarDS-Event-Id"
#: How far (in seconds) a delivery's timestamp may be from now by default; older ones may be replays.
DEFAULT_TOLERANCE = 300


def _as_bytes(body: bytes | bytearray | memoryview | str) -> bytes:
    if isinstance(body, str):
        return body.encode("utf-8")
    return bytes(body)


def compute_signature(body: bytes | str, secret: str, timestamp: int) -> str:
    """The lowercase hex ``v1`` signature of ``body`` at ``timestamp`` (what StellarDS puts in the header)."""
    payload = str(int(timestamp)).encode("ascii") + b"." + _as_bytes(body)
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _parse_header(header: str) -> tuple[int | None, list[bytes]]:
    timestamp: int | None = None
    signatures: list[bytes] = []
    for part in header.split(","):
        key, sep, value = part.strip().partition("=")
        if not sep or not key:
            continue
        value = value.strip()
        if key == "t" and value.isdigit() and value.isascii():
            timestamp = int(value)
        elif key == "v1" and len(value) == 64:
            try:
                signatures.append(bytes.fromhex(value))
            except ValueError:
                continue  # not a signature; ignore it
    return timestamp, signatures


def _check(
    body: bytes | bytearray | memoryview | str,
    header: str | None,
    secret: str,
    tolerance: float,
    now: float | None,
) -> str | None:
    """None when valid, else why not."""
    if not header:
        return "missing StellarDS-Signature header"
    if not secret:
        return "no webhook secret given"
    timestamp, signatures = _parse_header(header)
    if timestamp is None:
        return "the signature header has no timestamp"
    if not signatures:
        return "the signature header has no v1 signature"
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance:
        return "the delivery's timestamp is outside the tolerance (a replay, or a clock out of sync)"
    expected = bytes.fromhex(compute_signature(_as_bytes(body), secret, timestamp))
    # Compare against every signature (no early exit), each in constant time.
    matched = False
    for signature in signatures:
        matched |= hmac.compare_digest(signature, expected)
    return None if matched else "no signature matches"


def verify_signature(
    body: bytes | bytearray | memoryview | str,
    header: str | None,
    secret: str,
    tolerance: float = DEFAULT_TOLERANCE,
    now: float | None = None,
) -> bool:
    """True when ``header`` holds a valid signature of ``body`` made with ``secret`` within ``tolerance`` seconds.

    Args:
        body: the raw request body, exactly as received (bytes, or the str decoded as UTF-8).
        header: the ``StellarDS-Signature`` header value.
        secret: the webhook's secret (``whsec_...``).
        tolerance: how many seconds the delivery's timestamp may differ from now (default 300).
        now: the current Unix time in seconds; for tests.
    """
    return _check(body, header, secret, tolerance, now) is None


def construct_event(
    body: bytes | bytearray | memoryview | str,
    header: str | None,
    secret: str,
    tolerance: float = DEFAULT_TOLERANCE,
    now: float | None = None,
) -> Any:
    """Verifies the delivery and returns its parsed JSON event.

    Raises:
        WebhookSignatureError: when the signature is missing, expired or doesn't match, or the body isn't JSON.
    """
    problem = _check(body, header, secret, tolerance, now)
    if problem is not None:
        raise WebhookSignatureError(problem)
    try:
        return json.loads(_as_bytes(body))
    except ValueError as error:
        raise WebhookSignatureError(f"the delivery's body isn't valid JSON: {error}") from error
