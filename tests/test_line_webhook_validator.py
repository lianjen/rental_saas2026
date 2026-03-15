"""
LINE webhook validator tests - v1.0.0
"""

import base64
import hashlib
import hmac
import json

from middleware.line_webhook_validator import (
    HTTP_FORBIDDEN,
    HTTP_OK,
    parse_line_webhook_events,
    validate_line_signature,
    validate_line_webhook_request,
)


def _build_signature(secret: str, body: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def test_validate_line_signature_accepts_valid_signature():
    secret = "unit-test-secret"
    body = b'{"events":[{"type":"message"}]}'
    signature = _build_signature(secret, body)

    assert validate_line_signature(secret, body, signature) is True


def test_validate_line_webhook_request_rejects_missing_signature():
    body = b'{"events":[]}'

    ok, msg, status_code = validate_line_webhook_request(
        body=body,
        signature="",
        channel_secret="unit-test-secret",
    )

    assert ok is False
    assert status_code == HTTP_FORBIDDEN
    assert "signature" in msg.lower()


def test_validate_line_webhook_request_rejects_invalid_signature():
    body = b'{"events":[]}'

    ok, msg, status_code = validate_line_webhook_request(
        body=body,
        signature="invalid-signature",
        channel_secret="unit-test-secret",
    )

    assert ok is False
    assert status_code == HTTP_FORBIDDEN
    assert "invalid" in msg.lower()


def test_parse_line_webhook_events_accepts_valid_signature():
    secret = "unit-test-secret"
    payload = {"events": [{"type": "follow", "source": {"userId": "U1234567890"}}]}
    body = json.dumps(payload).encode("utf-8")
    signature = _build_signature(secret, body)

    ok, msg, events, status_code = parse_line_webhook_events(
        body=body,
        signature=signature,
        channel_secret=secret,
    )

    assert ok is True
    assert status_code == HTTP_OK
    assert msg == "LINE webhook accepted"
    assert events == payload["events"]
