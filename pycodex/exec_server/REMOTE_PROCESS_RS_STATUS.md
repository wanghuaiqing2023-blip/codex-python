# codex-exec-server src/remote_process.rs Status

Rust source: `codex/codex-rs/exec-server/src/remote_process.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Scope

This module adapts the `ExecBackend` and `ExecProcess` interfaces to an
already-connected remote exec-server client.  Python mirrors the module-owned
behavior without implementing the transport that creates the client:

- `RemoteProcessBoundary.new(...)` accepts a `LazyRemoteExecServerClient`
  dependency.
- `RemoteProcessBoundary.start(...)` gets the client, registers the process
  session, calls `client.exec(params)`, unregisters the session if exec fails,
  and returns a `StartedExecProcess`.
- `RemoteExecProcess` delegates `process_id`, wake subscriptions, event
  subscriptions, read, write, and terminate to the client session.
- `RemoteExecProcess.unregister(...)` exposes the Rust drop-time cleanup path
  deterministically for Python tests; `__del__` attempts best-effort async
  unregister when an event loop is active.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/remote_process.rs`
- Adjacent Rust source: `codex/codex-rs/exec-server/src/client.rs` session API
- Python tests:
  - `tests/test_exec_server_remote_process_rs.py::test_remote_process_start_registers_session_then_execs`
  - `tests/test_exec_server_remote_process_rs.py::test_remote_process_start_unregisters_session_when_exec_fails`
  - `tests/test_exec_server_remote_process_rs.py::test_remote_exec_process_delegates_session_methods`

## Validation

```powershell
python -m pytest tests/test_exec_server_remote_process_rs.py -q --tb=short
python -m pytest tests/test_exec_server_remote_process_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_process_rs.py
```

Completion validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_remote_process_rs.py -q --tb=short
3 passed

python -m pytest tests/test_exec_server_remote_process_rs.py tests/test_exec_server_client_rs.py tests/test_exec_server_process_rs.py tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_environment_rs.py -q --tb=short
31 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_process_rs.py
passed
```

The concrete remote connection lifecycle, relay/websocket transport, and
environment orchestration remain owned by `src/remote.rs`, `src/relay.rs`, and
client transport modules.
