# client_transport.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/client_transport.rs`

Python surface: `pycodex.exec_server`

Status: `complete` for stdio subprocess connection creation,
initialization handoff, injected websocket connect timeout/error mapping,
dependency-light standard-library `ws://` websocket dialing, and websocket
connection selection

## Rust anchors

- `ENVIRONMENT_CLIENT_NAME`
- `ExecServerClient::connect_for_transport`
- `ExecServerClient::connect_websocket`
- `ExecServerClient::connect_stdio_command`
- `is_rendezvous_harness_url`
- `stdio_command_process`

## Python evidence

- `tests/test_exec_server_client_transport_rs.py::test_connect_for_transport_projects_websocket_params_to_environment_client`
- `tests/test_exec_server_client_transport_rs.py::test_is_rendezvous_harness_url_matches_rust_query_scan`
- `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_selects_harness_or_plain_connection_from_url_role`
- `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_maps_connect_timeout_like_rust`
- `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_maps_connector_error_like_rust`
- `tests/test_exec_server_client_transport_rs.py::test_connect_websocket_without_injected_connector_uses_stdlib_handshake`
- `tests/test_exec_server_client_transport_rs.py::test_stdlib_websocket_upgrade_response_requires_tungstenite_protocol_headers`
- `tests/test_exec_server_client_transport_rs.py::test_connect_for_transport_projects_stdio_command_to_environment_client`
- `tests/test_exec_server_client_transport_rs.py::test_connect_stdio_command_uses_options_conversion`
- `tests/test_exec_server_client_transport_rs.py::test_connect_stdio_command_spawns_real_json_rpc_client`
- `tests/test_exec_server_client_transport_rs.py::test_connect_stdio_command_spawn_error_matches_rust_prefix`
- `tests/test_exec_server_client_transport_rs.py::test_initialize_connection_sends_initialize_then_initialized`
- `tests/test_exec_server_client_transport_rs.py::test_stdio_command_process_spec_matches_rust_command_builder`

## Notes

This status covers the module-owned branch orchestration, stdio subprocess
spawning, and initialization contract without claiming live websocket transport.
Python mirrors the Rust `codex-environment` client name for environment
transports, forwards connect/initialize timeouts and resume ids through
`ExecServerClientConnectOptions`, performs the JSON-RPC initialize/initialized
handshake over injected or real stdio connections, drains stdio stderr, and
exposes a stdio command process spec for the Rust builder settings.
For websocket streams supplied by an injected connector, Python now mirrors
Rust's `tokio::time::timeout(connect_timeout, connect_async(...))` boundary,
maps injected dial timeouts and dial failures to the Rust
`ExecServerError::{WebSocketConnectTimeout,WebSocketConnect}` display shapes,
mirrors Rust's `role=harness` query-pair scan, and chooses
`harness_connection_from_websocket(...)` for rendezvous harness URLs while
using `JsonRpcConnection.from_websocket(...)` for ordinary websocket URLs.
Without an injected connector, Python now performs a dependency-light
standard-library `ws://` client handshake, validates the 101 response
`Upgrade`, `Connection`, and `Sec-WebSocket-Accept` headers, sends masked
client frames, reads server frames, and routes the stream through the same
initialize/initialized handoff.

Exact tungstenite runtime identity, live `wss://` TLS edge cases, and
rendezvous websocket runtime coverage remain non-blocking operational checks
for the crate.

## Completion validation

2026-06-21:

```text
python -m pytest tests/test_exec_server_client_transport_rs.py -q --tb=short
13 passed

python -m pytest tests/test_exec_server_client_transport_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_transport_rs.py -q --tb=short
34 passed

python -m pytest tests/test_exec_server_client_transport_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_relay_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short
65 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_client_transport_rs.py
passed

$files = Get-ChildItem tests -Filter 'test_exec_server_*_rs.py' | ForEach-Object { $_.FullName }; python -m pytest $files -q --tb=short
254 passed, 1 skipped
```
