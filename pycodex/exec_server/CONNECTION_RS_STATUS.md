# connection.rs Status

Rust crate: `codex-exec-server`

Rust module: `src/connection.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Rust anchors

- `CHANNEL_CAPACITY`
- `JsonRpcConnectionEvent::{Message, MalformedMessage, Disconnected}`
- `JsonRpcTransport::{Plain, Stdio}` transport-termination surface
- `JsonRpcTransport::from_child_process`
- `StdioTransport::spawn`
- `StdioTransportHandle::terminate`
- `spawn_stdio_child_supervisor`
- `terminate_stdio_child`
- `JsonRpcConnection::from_stdio`
- `JsonRpcConnection::with_child_process`
- `JsonRpcConnection::from_websocket_stream`
- `JsonRpcWebSocketFrame::{Message, Close, Ignore}`
- `JsonRpcWebSocketMessage::{parse_jsonrpc_frame, from_text, ping}`
- `send_disconnected`
- `send_malformed_message`
- `write_jsonrpc_line_message`
- `send_websocket_jsonrpc_message`
- `serialize_jsonrpc_message`

## Python evidence

- `tests/test_exec_server_connection_rs.py::test_stdio_connection_reads_messages_skips_blanks_and_reports_eof`
- `tests/test_exec_server_connection_rs.py::test_stdio_connection_reports_malformed_jsonrpc_message`
- `tests/test_exec_server_connection_rs.py::test_stdio_connection_writes_compact_jsonrpc_lines`
- `tests/test_exec_server_connection_rs.py::test_stdio_connection_reports_write_errors_as_disconnected`
- `tests/test_exec_server_connection_rs.py::test_websocket_connection_sends_configured_ping`
- `tests/test_exec_server_connection_rs.py::test_websocket_connection_ignores_server_pong`
- `tests/test_exec_server_connection_rs.py::test_websocket_connection_reports_server_close`
- `tests/test_exec_server_connection_rs.py::test_websocket_connection_accepts_binary_jsonrpc_message`
- `tests/test_exec_server_connection_rs.py::test_websocket_connection_keeps_outbound_message_while_send_is_backpressured`
- `tests/test_exec_server_connection_rs.py::test_stdio_transport_terminate_is_idempotent_and_requests_child_termination`
- `tests/test_exec_server_connection_rs.py::test_stdio_transport_kills_child_after_termination_grace_timeout`
- `tests/test_exec_server_connection_rs.py::test_stdio_child_supervisor_kills_process_tree_after_child_exit`
- `tests/test_exec_server_connection_rs.py::test_jsonrpc_connection_with_child_process_installs_stdio_transport`
- `tests/test_exec_server_transport_rs.py::test_stdio_listen_transport_serves_initialize`

## Notes

This status covers the dependency-light stdio JSON-RPC transport behavior used
by the `src/server/transport.rs` stdio initialize slice: line parsing,
compact-line writing, malformed-frame events, EOF/read/write disconnect events,
and graceful draining of queued outbound responses before processor shutdown.
It also covers the dependency-light websocket loop behavior from the Rust unit
tests: configured ping frames, ignored pong frames, close/disconnect events,
binary JSON-RPC frames, outbound text serialization, and single-loop
backpressure ordering. The child-supervision slice covers idempotent terminate
requests, graceful termination followed by kill after the grace period,
cleanup after child exit, and `with_child_process` installing the stdio
transport wrapper.

Concrete Axum/tungstenite integration and OS-specific process-tree termination
via Unix process groups or Windows `taskkill` remain explicit runtime
boundaries for later module-scoped work; they are outside this module's
dependency-light JSON-RPC connection behavior contract.

## Validation

- `python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py -q --tb=short`
  passed on 2026-06-21 with `22 passed`.
- `python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_transport_rs.py -q --tb=short`
  passed on 2026-06-21 with `38 passed`.
- `python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_connection_rs.py tests\test_exec_server_rpc_rs.py`
  passed on 2026-06-21.
