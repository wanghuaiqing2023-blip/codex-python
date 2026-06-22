# codex-exec-server/src/rpc.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/rpc.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the independently testable RPC behavior:

- `RpcCallError`
- `RpcClientEvent`
- `RpcServerOutboundMessage`
- `RpcNotificationSender`
- `RpcRouter` request, request-with-id, and notification route registration
- `RpcClient` request id allocation and pending response matching with injected
  JSON-RPC messages
- `encode_server_message(...)`
- RPC error helpers: `invalid_request`, `method_not_found`, `invalid_params`,
  `not_found`, and `internal_error`
- `decode_request_params(...)`, `decode_notification_params(...)`, and the
  `{}`-to-null decode fallback
- `handle_server_message(...)`
- `drain_pending(...)`

Concrete `JsonRpcConnection` integration, transport task ownership, stdio/socket
reader and writer loops, disconnect watch ordering, and drop-time transport
termination remain owned by adjacent connection/transport runtime modules and
are not claimed here.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/rpc.rs`
- Rust test: `rpc_client_matches_out_of_order_responses_by_request_id`
- Python tests: `tests/test_exec_server_rpc_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_rpc_rs.py
python -m pytest tests/test_exec_server_rpc_rs.py -q --tb=short
```

Latest result:

```text
9 passed
```

Completion validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py -q --tb=short
22 passed

python -m pytest tests/test_exec_server_connection_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_transport_rs.py -q --tb=short
38 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_connection_rs.py tests\test_exec_server_rpc_rs.py
passed
```
