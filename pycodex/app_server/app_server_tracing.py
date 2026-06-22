"""Tracing span projections for Rust ``codex-app-server/src/app_server_tracing.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class AppServerRequestSpanProjection:
    """Metadata recorded by Rust's ``app_server.request`` tracing span."""

    span_name: str
    otel_kind: str
    otel_name: str
    rpc_system: str
    rpc_method: str
    rpc_transport: str
    rpc_request_id: str
    app_server_connection_id: str
    app_server_api_version: str
    app_server_client_name: str | None = None
    app_server_client_version: str | None = None
    turn_id_recorded: bool = False
    parent_context_source: str | None = None
    parent_traceparent: str | None = None
    parent_tracestate: str | None = None


def request_span_projection(
    request: Any,
    transport: Any,
    connection_id: Any,
    session: Any,
    *,
    env_trace: Mapping[str, str] | None = None,
) -> AppServerRequestSpanProjection:
    """Mirror Rust ``request_span`` metadata and parent-context decisions."""

    method = str(_field(request, "method", ""))
    request_id = _field(request, "id", "")
    initialize_client_info = _initialize_client_info(request)
    parent_trace = _request_parent_trace(request)

    return _app_server_request_span_template(
        method=method,
        transport=transport_name(transport),
        request_id=request_id,
        connection_id=connection_id,
        client_name=_client_info_field(initialize_client_info, "name")
        or _session_client_name(session),
        client_version=_client_info_field(initialize_client_info, "version")
        or _session_client_version(session),
        parent_trace=parent_trace,
        env_trace=env_trace,
    )


def typed_request_span_projection(
    request: Any,
    connection_id: Any,
    session: Any,
    *,
    env_trace: Mapping[str, str] | None = None,
) -> AppServerRequestSpanProjection:
    """Mirror Rust ``typed_request_span`` for in-process client requests."""

    method = _call_or_field(request, "method", "")
    request_id = _call_or_field(request, "id", "")
    initialize_client_info = _initialize_client_info_from_typed_request(request)
    return _app_server_request_span_template(
        method=str(method),
        transport="in-process",
        request_id=request_id,
        connection_id=connection_id,
        client_name=_client_info_field(initialize_client_info, "name")
        or _session_client_name(session),
        client_version=_client_info_field(initialize_client_info, "version")
        or _session_client_version(session),
        parent_trace=None,
        env_trace=env_trace,
    )


def transport_name(transport: Any) -> str:
    """Mirror Rust ``transport_name`` for app-server transports."""

    value = _transport_discriminant(transport)
    if value in {"stdio", "Stdio"}:
        return "stdio"
    if value in {"unix", "unix_socket", "UnixSocket"}:
        return "unix_socket"
    if value in {"websocket", "WebSocket"}:
        return "websocket"
    if value in {"off", "Off"}:
        return "off"
    raise ValueError(f"unknown app-server transport: {transport!r}")


def _app_server_request_span_template(
    *,
    method: str,
    transport: str,
    request_id: Any,
    connection_id: Any,
    client_name: str | None,
    client_version: str | None,
    parent_trace: Mapping[str, str | None] | None,
    env_trace: Mapping[str, str] | None,
) -> AppServerRequestSpanProjection:
    parent_source = None
    traceparent = None
    tracestate = None
    if parent_trace is not None and parent_trace.get("traceparent") is not None:
        parent_source = "request_trace"
        traceparent = parent_trace.get("traceparent")
        tracestate = parent_trace.get("tracestate")
    elif env_trace and env_trace.get("traceparent"):
        parent_source = "env_trace"
        traceparent = env_trace.get("traceparent")
        tracestate = env_trace.get("tracestate")

    return AppServerRequestSpanProjection(
        span_name="app_server.request",
        otel_kind="server",
        otel_name=method,
        rpc_system="jsonrpc",
        rpc_method=method,
        rpc_transport=transport,
        rpc_request_id=str(request_id),
        app_server_connection_id=str(connection_id),
        app_server_api_version="v2",
        app_server_client_name=client_name,
        app_server_client_version=client_version,
        turn_id_recorded=False,
        parent_context_source=parent_source,
        parent_traceparent=traceparent,
        parent_tracestate=tracestate,
    )


def _initialize_client_info(request: Any) -> Mapping[str, Any] | None:
    if _field(request, "method") != "initialize":
        return None
    params = _field(request, "params")
    if params is None:
        return None
    return _client_info_from_params(params)


def _initialize_client_info_from_typed_request(request: Any) -> Mapping[str, Any] | None:
    variant = _field(request, "variant", _field(request, "type", _field(request, "method", None)))
    method = _call_or_field(request, "method", variant)
    if str(method) != "initialize" and str(variant) not in {"Initialize", "initialize"}:
        return None
    return _client_info_from_params(_field(request, "params"))


def _client_info_from_params(params: Any) -> Mapping[str, Any] | None:
    client_info = _field(params, "client_info", _field(params, "clientInfo", None))
    return client_info if client_info is not None else None


def _request_parent_trace(request: Any) -> Mapping[str, str | None] | None:
    trace = _field(request, "trace")
    if trace is None:
        return None
    traceparent = _field(trace, "traceparent")
    if traceparent is None:
        return None
    return {"traceparent": traceparent, "tracestate": _field(trace, "tracestate")}


def _client_info_field(client_info: Any, name: str) -> str | None:
    value = _field(client_info, name) if client_info is not None else None
    return None if value is None else str(value)


def _session_client_name(session: Any) -> str | None:
    value = _call_or_field(session, "app_server_client_name", None)
    return None if value is None else str(value)


def _session_client_version(session: Any) -> str | None:
    value = _call_or_field(session, "client_version", None)
    return None if value is None else str(value)


def _transport_discriminant(transport: Any) -> str:
    if isinstance(transport, str):
        return transport
    for name in ("kind", "type", "variant"):
        value = _field(transport, name)
        if value is not None:
            return str(value)
    return transport.__class__.__name__


def _call_or_field(value: Any, name: str, default: Any = None) -> Any:
    item = _field(value, name, default)
    if callable(item):
        return item()
    return item


def _field(value: Any, name: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


__all__ = [
    "AppServerRequestSpanProjection",
    "request_span_projection",
    "transport_name",
    "typed_request_span_projection",
]
