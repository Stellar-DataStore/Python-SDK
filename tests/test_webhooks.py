from __future__ import annotations

import pytest

from stellards import WebhookSignatureError
from stellards.webhooks import compute_signature, construct_event, verify_signature

BODY = '{"id":"evt_0192","type":"record.created","data":{"record":{"id":1,"price":12.5}}}'
SECRET = "whsec_test_secret_123"
OLD_SECRET = "whsec_old_secret_456"
T = 1730000000
# Computed independently with: printf '%s' "$T.$BODY" | openssl dgst -sha256 -hmac "$SECRET"
SIGNATURE = "055d015ecf32860112b22ecfcfb0bfa03a4fa52abc40c6f47503cb71fc31deb6"
OLD_SIGNATURE = "e7278100a89fee718f77e5e1906358d68c6fc4332206c10f50683310a8982606"


def test_known_vector() -> None:
    assert compute_signature(BODY, SECRET, T) == SIGNATURE
    assert compute_signature(BODY.encode(), OLD_SECRET, T) == OLD_SIGNATURE


@pytest.mark.parametrize("body", [BODY, BODY.encode(), bytearray(BODY.encode()), memoryview(BODY.encode())])
def test_valid_signature(body: str | bytes) -> None:
    assert verify_signature(body, f"t={T},v1={SIGNATURE}", SECRET, now=T + 10)


def test_tampered_body_or_signature_fails() -> None:
    assert not verify_signature(BODY.replace("12.5", "99.5"), f"t={T},v1={SIGNATURE}", SECRET, now=T)
    flipped = ("0" if SIGNATURE[0] != "0" else "1") + SIGNATURE[1:]
    assert not verify_signature(BODY, f"t={T},v1={flipped}", SECRET, now=T)
    assert not verify_signature(BODY, f"t={T},v1={SIGNATURE}", "whsec_wrong", now=T)
    # The timestamp is part of what is signed.
    assert not verify_signature(BODY, f"t={T + 1},v1={SIGNATURE}", SECRET, now=T)


def test_expired_or_future_timestamp_fails() -> None:
    header = f"t={T},v1={SIGNATURE}"
    assert verify_signature(BODY, header, SECRET, now=T + 300)
    assert not verify_signature(BODY, header, SECRET, now=T + 301)
    assert not verify_signature(BODY, header, SECRET, now=T - 301)
    assert verify_signature(BODY, header, SECRET, tolerance=3600, now=T + 3000)


def test_rotated_secrets_either_matches() -> None:
    header = f"t={T},v1={OLD_SIGNATURE},v1={SIGNATURE}"
    assert verify_signature(BODY, header, SECRET, now=T)
    assert verify_signature(BODY, header, OLD_SECRET, now=T)
    assert not verify_signature(BODY, header, "whsec_other", now=T)


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "garbage",
        f"v1={SIGNATURE}",
        f"t={T}",
        f"t=abc,v1={SIGNATURE}",
        f"t={T},v1=xyz",
        f"t={T},v1={'z' * 64}",
        f"t={T},v0={SIGNATURE}",
    ],
)
def test_malformed_headers_fail(header: str | None) -> None:
    assert not verify_signature(BODY, header, SECRET, now=T)


def test_header_with_spaces_and_unknown_parts() -> None:
    assert verify_signature(BODY, f" t={T} , v1={SIGNATURE} , v2=whatever ", SECRET, now=T)


def test_empty_secret_fails() -> None:
    assert not verify_signature(BODY, f"t={T},v1={SIGNATURE}", "", now=T)


def test_construct_event() -> None:
    event = construct_event(BODY.encode(), f"t={T},v1={SIGNATURE}", SECRET, now=T)
    assert event["type"] == "record.created"
    assert event["data"]["record"]["price"] == 12.5
    with pytest.raises(WebhookSignatureError, match="tolerance"):
        construct_event(BODY, f"t={T},v1={SIGNATURE}", SECRET, now=T + 1000)
    with pytest.raises(WebhookSignatureError, match="no signature matches"):
        construct_event(BODY, f"t={T},v1={OLD_SIGNATURE}", SECRET, now=T)


def test_construct_event_rejects_non_json() -> None:
    body = "not json"
    header = f"t={T},v1={compute_signature(body, SECRET, T)}"
    with pytest.raises(WebhookSignatureError, match="JSON"):
        construct_event(body, header, SECRET, now=T)
