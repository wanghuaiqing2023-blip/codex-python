from types import SimpleNamespace

import pytest

from pycodex.app_server.app_server_tracing import (
    request_span_projection,
    transport_name,
    typed_request_span_projection,
)


def test_transport_name_matches_rust_transport_variants() -> None:
    # Rust: app_server_tracing.rs::transport_name.
    assert transport_name("stdio") == "stdio"
    assert transport_name({"kind": "UnixSocket"}) == "unix_socket"
    assert transport_name(SimpleNamespace(kind="WebSocket")) == "websocket"
    assert transport_name("off") == "off"


def test_request_span_records_template_fields_and_session_client_info() -> None:
    # Rust: app_server_tracing.rs::request_span template and session fallback.
    span = request_span_projection(
        {"method": "thread/start", "id": 42},
        "stdio",
        7,
        {"app_server_client_name": "desktop", "client_version": "1.2.3"},
    )

    assert span.span_name == "app_server.request"
    assert span.otel_kind == "server"
    assert span.otel_name == "thread/start"
    assert span.rpc_system == "jsonrpc"
    assert span.rpc_method == "thread/start"
    assert span.rpc_transport == "stdio"
    assert span.rpc_request_id == "42"
    assert span.app_server_connection_id == "7"
    assert span.app_server_api_version == "v2"
    assert span.app_server_client_name == "desktop"
    assert span.app_server_client_version == "1.2.3"
    assert span.turn_id_recorded is False


def test_request_span_initialize_params_override_session_client_info() -> None:
    # Rust: initialize_client_info wins over ConnectionSessionState client info.
    span = request_span_projection(
        {
            "method": "initialize",
            "id": "init-1",
            "params": {"clientInfo": {"name": "vscode", "version": "9.9.9"}},
        },
        "websocket",
        "conn",
        {"app_server_client_name": "old", "client_version": "0.0.1"},
    )

    assert span.rpc_transport == "websocket"
    assert span.app_server_client_name == "vscode"
    assert span.app_server_client_version == "9.9.9"


def test_request_span_uses_request_trace_before_env_trace() -> None:
    # Rust: request.trace with traceparent attaches parent before env fallback.
    span = request_span_projection(
        {
            "method": "turn/start",
            "id": "req-1",
            "trace": {"traceparent": "00-request", "tracestate": "vendor=request"},
        },
        "unix",
        "conn",
        {},
        env_trace={"traceparent": "00-env", "tracestate": "vendor=env"},
    )

    assert span.parent_context_source == "request_trace"
    assert span.parent_traceparent == "00-request"
    assert span.parent_tracestate == "vendor=request"


def test_request_span_uses_env_trace_when_request_traceparent_is_absent() -> None:
    span = request_span_projection(
        {"method": "turn/start", "id": "req-2", "trace": {"tracestate": "ignored"}},
        "stdio",
        "conn",
        {},
        env_trace={"traceparent": "00-env", "tracestate": "vendor=env"},
    )

    assert span.parent_context_source == "env_trace"
    assert span.parent_traceparent == "00-env"
    assert span.parent_tracestate == "vendor=env"


def test_typed_request_span_uses_in_process_transport_and_typed_initialize_client_info() -> None:
    # Rust: typed_request_span stamps transport as in-process and reads typed Initialize params.
    request = {
        "variant": "Initialize",
        "id": "typed-1",
        "method": "initialize",
        "params": {"client_info": {"name": "embedded", "version": "2.0.0"}},
    }

    span = typed_request_span_projection(
        request,
        "conn",
        {"app_server_client_name": "old", "client_version": "0.0.1"},
    )

    assert span.rpc_transport == "in-process"
    assert span.rpc_request_id == "typed-1"
    assert span.app_server_client_name == "embedded"
    assert span.app_server_client_version == "2.0.0"


def test_transport_name_rejects_unknown_transport() -> None:
    with pytest.raises(ValueError, match="unknown app-server transport"):
        transport_name("pipe")
