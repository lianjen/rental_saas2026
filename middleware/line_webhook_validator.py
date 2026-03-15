"""
LINE webhook validator - v1.0.0
Validate LINE webhook signatures before any business logic runs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import streamlit as st  # type: ignore
except ImportError:
    st = None  # type: ignore


logger = logging.getLogger("rental_app")


HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_FORBIDDEN = 403


def get_line_channel_secret(explicit_secret: Optional[str] = None) -> str:
    """Load the LINE channel secret from runtime config."""
    if explicit_secret:
        return explicit_secret

    secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    if secret:
        return secret

    if st is not None and hasattr(st, "secrets"):
        try:
            secret = str(st.secrets.get("LINE_CHANNEL_SECRET", "")).strip()
            if secret:
                return secret
        except Exception:
            pass

    return ""


def _validate_with_line_sdk(
    channel_secret: str,
    body: bytes,
    signature: str,
) -> Optional[bool]:
    """Try LINE's official parser first when the SDK is available."""
    try:
        from linebot.v3.exceptions import InvalidSignatureError
        from linebot.v3.webhook import WebhookParser
    except ImportError:
        return None

    parser = WebhookParser(channel_secret)
    body_text = body.decode("utf-8")

    try:
        try:
            parser.parse(body_text, signature)
        except TypeError:
            parser.parse(body_text, signature, as_payload=True)
        return True
    except InvalidSignatureError:
        return False


def validate_line_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """
    Validate LINE webhook X-Line-Signature.

    Reference:
    https://developers.line.biz/en/docs/messaging-api/receiving-messages/#verifying-signatures
    """
    if not channel_secret or not signature:
        return False

    if isinstance(body, str):
        body = body.encode("utf-8")

    sdk_result = _validate_with_line_sdk(channel_secret, body, signature)
    if sdk_result is not None:
        return sdk_result

    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected_signature = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected_signature, signature)


def validate_line_webhook_request(
    body: bytes,
    signature: str,
    channel_secret: Optional[str] = None,
) -> Tuple[bool, str, int]:
    """Return a standard validation result for webhook entry points."""
    resolved_secret = get_line_channel_secret(channel_secret)
    if not resolved_secret:
        logger.error("[LINE] Missing LINE_CHANNEL_SECRET - webhook rejected")
        return False, "LINE_CHANNEL_SECRET is not configured", HTTP_BAD_REQUEST

    if not signature:
        logger.warning("[LINE] Invalid signature - 可能是偽造請求")
        return False, "Missing X-Line-Signature header", HTTP_FORBIDDEN

    if not validate_line_signature(resolved_secret, body, signature):
        logger.warning("[LINE] Invalid signature - 可能是偽造請求")
        return False, "Invalid LINE signature", HTTP_FORBIDDEN

    return True, "LINE signature verified", HTTP_OK


def parse_line_webhook_events(
    body: bytes,
    signature: str,
    channel_secret: Optional[str] = None,
) -> Tuple[bool, str, List[Dict[str, Any]], int]:
    """Validate a LINE webhook request and return parsed events."""
    ok, msg, status_code = validate_line_webhook_request(
        body=body,
        signature=signature,
        channel_secret=channel_secret,
    )
    if not ok:
        return False, msg, [], status_code

    resolved_secret = get_line_channel_secret(channel_secret)
    body_text = body.decode("utf-8")

    try:
        try:
            from linebot.v3.webhook import WebhookParser
        except ImportError:
            payload = json.loads(body_text)
            events = payload.get("events", [])
            return True, "LINE webhook accepted", events, HTTP_OK

        parser = WebhookParser(resolved_secret)
        try:
            parsed_payload = parser.parse(body_text, signature, as_payload=True)
        except TypeError:
            parsed_payload = parser.parse(body_text, signature)

        if hasattr(parsed_payload, "events"):
            raw_events = parsed_payload.events
        else:
            raw_events = parsed_payload

        events: List[Dict[str, Any]] = []
        for event in raw_events:
            if hasattr(event, "as_json_dict"):
                events.append(event.as_json_dict())
            elif isinstance(event, dict):
                events.append(event)
            else:
                events.append({"raw_event": str(event)})

        return True, "LINE webhook accepted", events, HTTP_OK
    except json.JSONDecodeError as exc:
        logger.error("[LINE] Webhook payload decode failed: %s", exc)
        return False, f"Invalid LINE webhook payload: {exc}", HTTP_BAD_REQUEST
    except Exception as exc:
        logger.error("[LINE] Webhook parse failed: %s", exc)
        return False, f"Failed to parse LINE webhook payload: {exc}", HTTP_BAD_REQUEST


def require_valid_line_signature(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator for webhook handlers that accept body/signature arguments.

    The decorated function must receive `body` and `signature` keyword arguments,
    or provide them as the first two positional arguments after `self`.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        body = kwargs.get("body")
        signature = kwargs.get("signature")
        channel_secret = kwargs.get("channel_secret")

        if body is None or signature is None:
            offset = 1 if args and hasattr(args[0], "__class__") else 0
            if body is None and len(args) > offset:
                body = args[offset]
            if signature is None and len(args) > offset + 1:
                signature = args[offset + 1]

        if body is None:
            body = b""
        if isinstance(body, str):
            body = body.encode("utf-8")
        if signature is None:
            signature = ""

        ok, msg, status_code = validate_line_webhook_request(
            body=body,
            signature=signature,
            channel_secret=channel_secret,
        )
        if not ok:
            return False, msg, [], status_code

        kwargs["body"] = body
        kwargs["signature"] = signature
        return func(*args, **kwargs)

    return wrapper
