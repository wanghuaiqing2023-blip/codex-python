# codex-exec-server src/client.rs Status

Rust source: `codex/codex-rs/exec-server/src/client.rs`

Python surface: `pycodex.exec_server`

Status: `complete` for the connection-initialization, shared RPC call,
process read/write/terminate, lazy remote client, and session-notification
slices; remaining concrete remote transport and HTTP stream submodules stay
separate boundaries.

## Covered Contract

- `ExecServerClientConnectOptions` default and conversion behavior is covered
  with `client_api.rs` tests, and initialize/initialized handoff is covered
  with `client_transport.rs` tests.
- `ExecServerClient` can register and unregister per-process sessions, rejects
  duplicate process ids, and rejects new sessions after transport disconnect.
- `ExecServerClient.call` allocates connection-local JSON-RPC request ids,
  routes response/error frames from the reader loop to pending calls, maps
  server errors to the Rust `ExecServerError::Server` display shape, and fails
  pending calls with the canonical disconnected message when the transport
  closes.
- `ExecServerClient.read`, `write`, and `terminate` forward to the Rust
  `process/read`, `process/write`, and `process/terminate` method names,
  preserve Rust camelCase/base64 params, and decode typed responses.
- `LazyRemoteExecServerClient.get` caches connected clients, serializes
  concurrent first connection attempts, reconnects disconnected WebSocket
  clients, returns disconnected non-WebSocket clients like Rust, and delegates
  buffered/streamed HTTP helper calls after lazy connection.
- Connection-global server notifications are routed by `processId` to the
  matching session.
- Output, exited, and closed notifications are published in contiguous sequence
  order even when they arrive out of order.
- A published closed event removes the client-side process session route only
  after the terminal event is visible to subscribers.
- Transport disconnect publishes a single failed event for active sessions,
  synthesizes a closed read response with the canonical Rust disconnect
  message, and clears the session registry.
- Noisy process wake notifications do not block other sessions from receiving
  their own wake updates.

## Evidence

- Rust tests in `src/client.rs`:
  `process_events_are_delivered_in_seq_order_when_notifications_are_reordered`,
  `transport_disconnect_fails_sessions_and_rejects_new_sessions`, and
  `wake_notifications_do_not_block_other_sessions`.
- Source-derived Rust contract in `src/client.rs`:
  `ExecServerClient::{call,read,write,terminate}`,
  `LazyRemoteExecServerClient::{new,get,connected_client,cached_client}`, its
  `HttpClient` implementation, and `From<RpcCallError> for ExecServerError`.
- Python parity tests:
  `tests/test_exec_server_client_rs.py`.
- Adjacent initialize/transport evidence:
  `tests/test_exec_server_client_transport_rs.py`.

Focused validation:

```text
python -m pytest tests/test_exec_server_client_rs.py -q --tb=short
```

Result on 2026-06-21: `8 passed`.

Adjacent client/process/protocol validation:

```text
python -m pytest tests/test_exec_server_client_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short
```

Result on 2026-06-21: `30 passed`.

Completion validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_client_rs.py -q --tb=short
8 passed

python -m pytest tests/test_exec_server_client_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short
30 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_client_rs.py
passed
```

Focused RPC validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_client_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short
39 passed
```

Crate-focused validation on 2026-06-21:

```text
$tests = Get-ChildItem tests -Filter 'test_exec_server_*_rs.py' | ForEach-Object { $_.FullName }; python -m pytest $tests -q --tb=short
250 passed, 1 skipped
```

Focused lazy-client validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_client_rs.py tests/test_exec_server_remote_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_rpc_http_client_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_client_api_rs.py -q --tb=short
40 passed
```

Exec-server focused regression:

```text
python -m pytest tests/test_exec_server_client_rs.py tests/test_exec_server_client_transport_rs.py tests/test_exec_server_connection_rs.py tests/test_exec_server_local_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_environment_rs.py tests/test_exec_server_environment_toml_rs.py tests/test_exec_server_environment_provider_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_client_api_rs.py tests/test_exec_server_process_id_runtime_paths_rs.py tests/test_exec_server_protocol_rs.py tests/test_exec_config_plan.py tests/test_thread_manager_sample_main_rs.py tests/test_core_api_lib_rs.py tests/test_app_server_client_lib_rs.py -q --tb=short
```

Result on 2026-06-21: `321 passed, 1 skipped`.

## Remaining Boundaries

Concrete websocket connection replacement, exact HTTP stream runtime timing,
and `client/http_*` live transport submodules remain sibling client boundaries.
Relay/harness transport and concrete remote environment transport remain
crate-level gaps.
