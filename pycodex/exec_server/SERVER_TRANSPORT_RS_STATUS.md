# server/transport.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/server/transport.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Rust anchors

- `DEFAULT_LISTEN_URL`
- `ExecServerListenTransport::{WebSocket, Stdio}`
- `ExecServerListenUrlParseError::{UnsupportedListenUrl, InvalidWebSocketListenUrl}`
- `parse_listen_url`
- `run_websocket_listener`
- `readiness_handler`
- `websocket_upgrade_handler`
- `run_stdio_connection_with_io`
- `ConnectionProcessor::run_connection` through `build_router` for the stdio initialize path
- `JsonRpcConnection::from_axum_websocket` through the websocket upgrade path
- `src/server/transport_tests.rs` parse tests and `stdio_listen_transport_serves_initialize`

## Python evidence

- `tests/test_exec_server_transport_rs.py::test_parse_listen_url_accepts_default_websocket_url`
- `tests/test_exec_server_transport_rs.py::test_parse_listen_url_accepts_stdio_forms`
- `tests/test_exec_server_transport_rs.py::test_parse_listen_url_accepts_websocket_url`
- `tests/test_exec_server_transport_rs.py::test_parse_listen_url_rejects_invalid_websocket_url`
- `tests/test_exec_server_transport_rs.py::test_parse_listen_url_rejects_unsupported_url`
- `tests/test_exec_server_transport_rs.py::test_parse_listen_url_rejects_bad_ports_and_missing_ports`
- `tests/test_exec_server_transport_rs.py::test_stdio_listen_transport_serves_initialize`
- `tests/test_exec_server_transport_rs.py::test_websocket_http_handler_serves_readyz_and_initialize`

## Notes

This status covers the pure listen URL parser, user-facing parse errors, the
newline-framed stdio transport path far enough to process `initialize` and
`initialized` through the server router/handler, and a dependency-light
standard-library websocket HTTP handler slice. The websocket slice serves
`GET /readyz` with 200, upgrades `GET /`, decodes masked client frames, writes
server frames, and routes an `initialize` request through the existing
`JsonRpcConnection`/`ConnectionProcessor` path.

Exact Axum routing, tokio/tungstenite socket timing, and live network serving
remain non-blocking operational checks; the Python implementation intentionally
keeps the core behavior dependency-light.

## Validation

Focused validation:

```text
python -m pytest tests/test_exec_server_server_rs.py tests/test_exec_server_transport_rs.py -q --tb=short
python -m pytest tests/test_exec_server_transport_rs.py tests/test_exec_server_server_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_relay_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_server_rs.py tests\test_exec_server_transport_rs.py
```

Latest result:

```text
2026-06-21 server/transport focused validation after websocket handler slice: 8 passed
2026-06-21 adjacent transport/connection/processor/client/relay regression: 53 passed
2026-06-21 exec-server crate-focused validation: 251 passed, 1 skipped
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py and tests\test_exec_server_transport_rs.py
```
