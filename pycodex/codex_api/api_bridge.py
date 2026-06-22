"""API-to-protocol error bridge for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/api_bridge.rs``
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import datetime
from datetime import timezone
from typing import Any

from pycodex.codex_client import TransportError
from pycodex.protocol import CodexErr
from pycodex.protocol import RetryLimitReachedError
from pycodex.protocol import UnexpectedResponseError
from pycodex.protocol import UsageLimitReachedError
from pycodex.protocol.auth import PlanType
from pycodex.protocol.protocol import CreditsSnapshot as ProtocolCreditsSnapshot
from pycodex.protocol.protocol import RateLimitReachedType
from pycodex.protocol.protocol import RateLimitSnapshot as ProtocolRateLimitSnapshot
from pycodex.protocol.protocol import RateLimitWindow as ProtocolRateLimitWindow

from .error import ApiError
from .rate_limits import CreditsSnapshot
from .rate_limits import RateLimitSnapshot
from .rate_limits import RateLimitWindow
from .rate_limits import parse_promo_message
from .rate_limits import parse_rate_limit_for_limit
from .rate_limits import parse_rate_limit_reached_type


ACTIVE_LIMIT_HEADER = "x-codex-active-limit"
REQUEST_ID_HEADER = "x-request-id"
OAI_REQUEST_ID_HEADER = "x-oai-request-id"
CF_RAY_HEADER = "cf-ray"
X_OPENAI_AUTHORIZATION_ERROR_HEADER = "x-openai-authorization-error"
X_ERROR_JSON_HEADER = "x-error-json"
CYBER_POLICY_ERROR_CODE = "cyber_policy"
CYBER_POLICY_FALLBACK_MESSAGE = (
    "This request has been flagged for possible cybersecurity risk."
)


def map_api_error(error: ApiError) -> CodexErr:
    if error.kind == "context_window_exceeded":
        return CodexErr.simple("context_window_exceeded")
    if error.kind == "quota_exceeded":
        return CodexErr.simple("quota_exceeded")
    if error.kind == "usage_not_included":
        return CodexErr.simple("usage_not_included")
    if error.kind == "retryable":
        return CodexErr.stream(error.message or "", error.delay)
    if error.kind == "stream":
        return CodexErr.stream(error.message or "", None)
    if error.kind == "server_overloaded":
        return CodexErr.simple("server_overloaded")
    if error.kind == "api":
        return CodexErr.unexpected_status(
            UnexpectedResponseError(
                status=error.status if isinstance(error.status, int) else 0,
                body=error.message or "",
                url=None,
                cf_ray=None,
                request_id=None,
                identity_authorization_error=None,
                identity_error_code=None,
            )
        )
    if error.kind == "invalid_request":
        return CodexErr.invalid_request(error.message or "")
    if error.kind == "cyber_policy":
        return CodexErr.cyber_policy(error.message or CYBER_POLICY_FALLBACK_MESSAGE)
    if error.kind == "transport" and error.transport is not None:
        return _map_transport_error(error.transport)
    if error.kind == "rate_limit":
        return CodexErr.stream(error.message or "", None)
    return CodexErr.stream(str(error), None)


def _map_transport_error(error: TransportError) -> CodexErr:
    if error.kind == "http":
        return _map_http_transport_error(error)
    if error.kind == "retry_limit":
        return CodexErr.retry_limit(RetryLimitReachedError(status=500, request_id=None))
    if error.kind == "timeout":
        return CodexErr.simple("request_timeout")
    if error.kind in {"network", "build"}:
        return CodexErr.stream(error.message or "", None)
    return CodexErr.stream(str(error), None)


def _map_http_transport_error(error: TransportError) -> CodexErr:
    status = int(error.status or 0)
    headers = error.headers
    body_text = error.body or ""

    if status == 503 and _body_error_code(body_text) in {
        "server_is_overloaded",
        "slow_down",
    }:
        return CodexErr.simple("server_overloaded")

    if status == 400:
        code = _body_error_code(body_text)
        if code == CYBER_POLICY_ERROR_CODE:
            return CodexErr.cyber_policy(_cyber_policy_message_from_body(body_text))
        if "The image data you provided does not represent a valid image" in body_text:
            return CodexErr.simple("invalid_image_request")
        return CodexErr.invalid_request(body_text)

    if status == 500:
        return CodexErr.simple("internal_server_error")

    if status == 429:
        usage_error = _parse_usage_error_response(body_text)
        if usage_error is not None:
            if usage_error.get("type") == "usage_limit_reached":
                limit_id = _extract_header(headers, ACTIVE_LIMIT_HEADER)
                rate_limits = _to_protocol_rate_limit_snapshot(
                    parse_rate_limit_for_limit(headers or {}, limit_id)
                    if headers is not None
                    else None
                )
                return CodexErr.usage_limit_reached(
                    UsageLimitReachedError(
                        plan_type=_plan_type(usage_error.get("plan_type")),
                        resets_at=_datetime_from_timestamp(usage_error.get("resets_at")),
                        rate_limits=rate_limits,
                        promo_message=parse_promo_message(headers or {}),
                        rate_limit_reached_type=_rate_limit_reached_type(
                            parse_rate_limit_reached_type(headers or {})
                        ),
                    )
                )
            if usage_error.get("type") == "usage_not_included":
                return CodexErr.simple("usage_not_included")
        return CodexErr.retry_limit(
            RetryLimitReachedError(
                status=status,
                request_id=_extract_request_tracking_id(headers),
            )
        )

    return CodexErr.unexpected_status(
        UnexpectedResponseError(
            status=status,
            body=body_text,
            url=error.url,
            cf_ray=_extract_header(headers, CF_RAY_HEADER),
            request_id=_extract_request_id(headers),
            identity_authorization_error=_extract_header(
                headers,
                X_OPENAI_AUTHORIZATION_ERROR_HEADER,
            ),
            identity_error_code=_extract_x_error_json_code(headers),
        )
    )


def _body_error_code(body_text: str) -> str | None:
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError:
        return None
    error = parsed.get("error") if isinstance(parsed, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _cyber_policy_message_from_body(body_text: str) -> str:
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError:
        return CYBER_POLICY_FALLBACK_MESSAGE
    error = parsed.get("error") if isinstance(parsed, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    if isinstance(message, str) and message.strip():
        return message
    return CYBER_POLICY_FALLBACK_MESSAGE


def _parse_usage_error_response(body_text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body_text)
    except json.JSONDecodeError:
        return None
    error = parsed.get("error") if isinstance(parsed, dict) else None
    return error if isinstance(error, dict) else None


def _extract_request_tracking_id(headers: Mapping[str, object] | None) -> str | None:
    return _extract_request_id(headers) or _extract_header(headers, CF_RAY_HEADER)


def _extract_request_id(headers: Mapping[str, object] | None) -> str | None:
    return _extract_header(headers, REQUEST_ID_HEADER) or _extract_header(
        headers,
        OAI_REQUEST_ID_HEADER,
    )


def _extract_header(headers: Mapping[str, object] | None, name: str) -> str | None:
    if headers is None:
        return None
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() != wanted:
            continue
        if isinstance(value, bytes):
            try:
                return value.decode()
            except UnicodeDecodeError:
                return None
        return str(value)
    return None


def _extract_x_error_json_code(headers: Mapping[str, object] | None) -> str | None:
    encoded = _extract_header(headers, X_ERROR_JSON_HEADER)
    if encoded is None:
        return None
    try:
        decoded = base64.b64decode(encoded)
        parsed = json.loads(decoded)
    except Exception:
        return None
    error = parsed.get("error") if isinstance(parsed, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, str) else None


def _datetime_from_timestamp(value: object) -> datetime | None:
    if not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _plan_type(value: object) -> PlanType | None:
    if not isinstance(value, str):
        return None
    return PlanType.from_raw_value(value)


def _rate_limit_reached_type(value: str | None) -> RateLimitReachedType | None:
    if value is None:
        return None
    try:
        return RateLimitReachedType.parse(value)
    except ValueError:
        return None


def _to_protocol_rate_limit_snapshot(
    snapshot: RateLimitSnapshot | None,
) -> ProtocolRateLimitSnapshot | None:
    if snapshot is None:
        return None
    return ProtocolRateLimitSnapshot(
        limit_id=snapshot.limit_id,
        limit_name=snapshot.limit_name,
        primary=_to_protocol_rate_limit_window(snapshot.primary),
        secondary=_to_protocol_rate_limit_window(snapshot.secondary),
        credits=_to_protocol_credits(snapshot.credits),
        plan_type=None,
        rate_limit_reached_type=_rate_limit_reached_type(snapshot.rate_limit_reached_type),
    )


def _to_protocol_rate_limit_window(
    window: RateLimitWindow | None,
) -> ProtocolRateLimitWindow | None:
    if window is None:
        return None
    return ProtocolRateLimitWindow(
        used_percent=window.used_percent,
        window_minutes=window.window_minutes,
        resets_at=window.resets_at,
    )


def _to_protocol_credits(
    credits: CreditsSnapshot | None,
) -> ProtocolCreditsSnapshot | None:
    if credits is None:
        return None
    return ProtocolCreditsSnapshot(
        has_credits=credits.has_credits,
        unlimited=credits.unlimited,
        balance=credits.balance,
    )


__all__ = [
    "ACTIVE_LIMIT_HEADER",
    "CF_RAY_HEADER",
    "CYBER_POLICY_ERROR_CODE",
    "CYBER_POLICY_FALLBACK_MESSAGE",
    "OAI_REQUEST_ID_HEADER",
    "REQUEST_ID_HEADER",
    "X_ERROR_JSON_HEADER",
    "X_OPENAI_AUTHORIZATION_ERROR_HEADER",
    "map_api_error",
]
