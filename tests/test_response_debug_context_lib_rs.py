from pycodex.response_debug_context import (
    ResponseDebugContext,
    extract_response_debug_context,
    extract_response_debug_context_from_api_error,
    telemetry_api_error_message,
    telemetry_transport_error_message,
)


def test_extract_response_debug_context_decodes_identity_headers() -> None:
    # Rust crate: codex-response-debug-context
    # Rust module: src/lib.rs
    # Rust test: extract_response_debug_context_decodes_identity_headers
    transport = {
        "type": "Http",
        "status": 401,
        "url": "https://chatgpt.com/backend-api/codex/models",
        "headers": {
            "x-oai-request-id": "req-auth",
            "cf-ray": "ray-auth",
            "x-openai-authorization-error": "missing_authorization_header",
            "x-error-json": "eyJlcnJvciI6eyJjb2RlIjoidG9rZW5fZXhwaXJlZCJ9fQ==",
        },
        "body": '{"error":{"message":"plain text error"},"status":401}',
    }

    assert extract_response_debug_context(transport) == ResponseDebugContext(
        request_id="req-auth",
        cf_ray="ray-auth",
        auth_error="missing_authorization_header",
        auth_error_code="token_expired",
    )
    assert (
        extract_response_debug_context_from_api_error({"type": "Transport", "transport": transport})
        == extract_response_debug_context(transport)
    )


def test_request_id_header_takes_precedence_and_invalid_error_json_is_ignored() -> None:
    # Rust source contract: x-request-id is tried before x-oai-request-id, and
    # invalid x-error-json/base64 simply yields no auth_error_code.
    transport = {
        "type": "Http",
        "status": 401,
        "headers": {
            "x-request-id": "req-primary",
            "x-oai-request-id": "req-secondary",
            "x-error-json": "not-base64-json",
        },
    }

    assert extract_response_debug_context(transport) == ResponseDebugContext(
        request_id="req-primary",
        auth_error_code=None,
    )


def test_non_http_transport_and_non_transport_api_error_return_default_context() -> None:
    # Rust source contract: only TransportError::Http and ApiError::Transport
    # carry response debug context.
    assert extract_response_debug_context({"type": "Timeout"}) == ResponseDebugContext()
    assert extract_response_debug_context_from_api_error({"type": "QuotaExceeded"}) == ResponseDebugContext()


def test_telemetry_error_messages_omit_http_bodies() -> None:
    # Rust crate: codex-response-debug-context
    # Rust module: src/lib.rs
    # Rust test: telemetry_error_messages_omit_http_bodies
    transport = {
        "type": "Http",
        "status": 401,
        "url": "https://chatgpt.com/backend-api/codex/responses",
        "headers": None,
        "body": '{"error":{"message":"secret token leaked"}}',
    }

    assert telemetry_transport_error_message(transport) == "http 401"
    assert telemetry_api_error_message({"type": "Transport", "transport": transport}) == "http 401"


def test_telemetry_error_messages_preserve_non_http_details() -> None:
    # Rust crate: codex-response-debug-context
    # Rust module: src/lib.rs
    # Rust test: telemetry_error_messages_preserve_non_http_details
    assert telemetry_transport_error_message({"type": "Network", "error": "dns lookup failed"}) == "dns lookup failed"
    assert telemetry_transport_error_message({"type": "Build", "error": "invalid header value"}) == "invalid header value"
    assert telemetry_api_error_message({"type": "Stream", "error": "socket closed"}) == "socket closed"


def test_fixed_telemetry_messages_match_rust_variants() -> None:
    # Rust source contract: fixed ApiError variants have body-free stable strings.
    assert telemetry_transport_error_message({"type": "RetryLimit"}) == "retry limit reached"
    assert telemetry_transport_error_message({"type": "Timeout"}) == "timeout"
    assert telemetry_api_error_message({"type": "Api", "status": 500}) == "api error 500"
    assert telemetry_api_error_message({"type": "ContextWindowExceeded"}) == "context window exceeded"
    assert telemetry_api_error_message({"type": "QuotaExceeded"}) == "quota exceeded"
    assert telemetry_api_error_message({"type": "UsageNotIncluded"}) == "usage not included"
    assert telemetry_api_error_message({"type": "Retryable"}) == "retryable error"
    assert telemetry_api_error_message({"type": "RateLimit"}) == "rate limit"
    assert telemetry_api_error_message({"type": "InvalidRequest"}) == "invalid request"
    assert telemetry_api_error_message({"type": "CyberPolicy"}) == "cyber policy"
    assert telemetry_api_error_message({"type": "ServerOverloaded"}) == "server overloaded"
