# codex-exec-server src/remote_file_system.rs Status

Rust source: `codex/codex-rs/exec-server/src/remote_file_system.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Scope

This module adapts the `ExecutorFileSystem` interface to an already-connected
remote exec-server client.  Python mirrors the module-owned behavior without
implementing the transport that creates the client:

- `RemoteFileSystemBoundary.new(...)` accepts a `LazyRemoteExecServerClient`
  dependency and implements read/write/create/metadata/directory/remove/copy.
- Filesystem calls project to the Rust `fs/*` protocol parameter dataclasses.
- File contents are encoded and decoded through base64.
- Metadata and directory responses are projected back to local filesystem value
  dataclasses.
- `remote_sandbox_context(...)` drops `cwd` when permissions are not
  cwd-dependent and preserves it for dynamic project-root permissions.
- `map_remote_error(...)` maps JSON-RPC not-found, invalid-request, and
  transport-closed errors to Python filesystem exceptions.

## Evidence

- Rust tests:
  - `remote_sandbox_context_drops_unused_cwd`
  - `remote_sandbox_context_preserves_required_cwd`
  - `transport_errors_map_to_broken_pipe`
- Python tests:
  - `tests/test_exec_server_remote_file_system_rs.py`

## Validation

```powershell
python -m pytest tests/test_exec_server_remote_file_system_rs.py -q --tb=short
python -m pytest tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_file_system_rs.py
```

Completion validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_remote_file_system_rs.py -q --tb=short
6 passed

python -m pytest tests/test_exec_server_remote_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short
42 passed, 1 skipped

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_remote_file_system_rs.py
passed
```

The concrete remote connection, websocket/relay transport, and lazy client
connection lifecycle remain owned by `src/remote.rs`, `src/relay.rs`, and
client transport modules.
