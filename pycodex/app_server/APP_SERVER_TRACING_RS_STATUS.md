# codex-app-server src/app_server_tracing.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/app_server_tracing.rs`

Python module:

- `pycodex/app_server/app_server_tracing.py`

## Covered contract

- `transport_name(...)` preserves Rust transport labels for stdio,
  Unix socket, websocket, and off modes.
- `request_span_projection(...)` mirrors the local `app_server.request` span
  template fields: server kind/name, JSON-RPC system/method/transport/request
  id, connection id, API version `v2`, empty `turn.id`, and optional client
  name/version records.
- Initialize request params override existing session client info, while
  non-initialize requests fall back to `ConnectionSessionState` client info.
- Request W3C trace context with a `traceparent` takes precedence over the
  environment trace fallback.
- `typed_request_span_projection(...)` mirrors the in-process typed request
  path by stamping `rpc.transport = "in-process"` and deriving initialize
  client info from the typed request params.

## Deferred

- Real `tracing::Span`, OpenTelemetry parent attachment, invalid carrier
  warnings, and global environment trace extraction remain runtime/telemetry
  dependencies outside this pure projection.

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_tracing_rs.py -q`
  -> `7 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/app_server_tracing.py
  tests/test_app_server_tracing_rs.py`.
