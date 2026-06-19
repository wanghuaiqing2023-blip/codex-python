"""Port of Rust ``codex-response-debug-context`` public API.

Rust source:
- ``codex/codex-rs/response-debug-context/src/lib.rs``
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


REQUEST_ID_HEADER = "x-request-id"
OAI_REQUEST_ID_HEADER = "x-oai-request-id"
CF_RAY_HEADER = "cf-ray"
AUTH_ERROR_HEADER = "x-openai-authorization-error"
X_ERROR_JSON_HEADER = "x-error-json"


@dataclass(frozen=True)
class ResponseDebugContext:
    request_id: str | None = None
    cf_ray: str | None = None
    auth_error: str | None = None
    auth_error_code: str | None = None


def extract_response_debug_context(transport: Any) -> ResponseDebugContext:
    if _variant_name(transport) != "http":
        return ResponseDebugContext()
    headers = _headers(transport)
    return ResponseDebugContext(
        request_id=_header(headers, REQUEST_ID_HEADER) or _header(headers, OAI_REQUEST_ID_HEADER),
        cf_ray=_header(headers, CF_RAY_HEADER),
        auth_error=_header(headers, AUTH_ERROR_HEADER),
        auth_error_code=_auth_error_code(_header(headers, X_ERROR_JSON_HEADER)),
    )


def extract_response_debug_context_from_api_error(error: Any) -> ResponseDebugContext:
    transport = getattr(error, "transport", None)
    if transport is None and isinstance(error, Mapping):
        transport = error.get("transport")
    if transport is None and _variant_name(error) == "transport":
        transport = error.get("error", error) if isinstance(error, Mapping) else getattr(error, "error", error)
    if transport is None:
        return ResponseDebugContext()
    return extract_response_debug_context(transport)


def telemetry_transport_error_message(error: Any) -> str:
    variant = _variant_name(error)
    if variant == "http":
        return f"http {_status_code(getattr(error, 'status', None) if not isinstance(error, Mapping) else error.get('status'))}"
    if variant == "retry_limit":
        return "retry limit reached"
    if variant == "timeout":
        return "timeout"
    if variant in {"network", "build"}:
        detail = getattr(error, "error", None)
        if detail is None and isinstance(error, Mapping):
            detail = error.get("error") or error.get("message")
        return str(detail)
    return str(error)


def telemetry_api_error_message(error: Any) -> str:
    variant = _variant_name(error)
    if variant == "transport":
        transport = getattr(error, "transport", None)
        if transport is None and isinstance(error, Mapping):
            transport = error.get("transport")
        return telemetry_transport_error_message(transport)
    if variant == "api":
        status = getattr(error, "status", None)
        if status is None and isinstance(error, Mapping):
            status = error.get("status")
        return f"api error {_status_code(status)}"
    if variant == "stream":
        detail = getattr(error, "error", None)
        if detail is None and isinstance(error, Mapping):
            detail = error.get("error") or error.get("message")
        return str(detail)
    fixed = {
        "context_window_exceeded": "context window exceeded",
        "quota_exceeded": "quota exceeded",
        "usage_not_included": "usage not included",
        "retryable": "retryable error",
        "rate_limit": "rate limit",
        "invalid_request": "invalid request",
        "cyber_policy": "cyber policy",
        "server_overloaded": "server overloaded",
    }
    return fixed.get(variant, str(error))


def _headers(value: Any) -> Mapping[str, Any] | None:
    headers = getattr(value, "headers", None)
    if headers is None and isinstance(value, Mapping):
        headers = value.get("headers")
    return headers if isinstance(headers, Mapping) else None


def _header(headers: Mapping[str, Any] | None, name: str) -> str | None:
    if headers is None:
        return None
    for key, value in headers.items():
        if str(key).lower() == name:
            return str(value)
    return None


def _auth_error_code(encoded: str | None) -> str | None:
    if not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded)
        parsed = json.loads(decoded)
        code = parsed.get("error", {}).get("code")
    except (ValueError, TypeError, AttributeError):
        return None
    return code if isinstance(code, str) else None


def _variant_name(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("kind", "type", "variant"):
        raw = getattr(value, attr, None)
        if raw is not None:
            return _normalize_variant_name(str(getattr(raw, "value", raw)))
    if isinstance(value, Mapping):
        for key in ("kind", "type", "variant"):
            if key in value:
                return _normalize_variant_name(str(value[key]))
    return _normalize_variant_name(value.__class__.__name__)


def _status_code(value: Any) -> str:
    code = getattr(value, "value", value)
    code = getattr(code, "status_code", code)
    return str(code)


def _normalize_variant_name(value: str) -> str:
    if not value:
        return ""
    with_separators = value.replace("-", "_").replace(" ", "_")
    with_separators = re.sub(r"(?<!^)(?=[A-Z])", "_", with_separators)
    return with_separators.lower()


__all__ = [
    "ResponseDebugContext",
    "extract_response_debug_context",
    "extract_response_debug_context_from_api_error",
    "telemetry_api_error_message",
    "telemetry_transport_error_message",
]
