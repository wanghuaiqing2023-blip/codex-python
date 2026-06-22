# codex-exec-server/src/server/registry.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/server/registry.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the server registry route table built by Rust
`build_router()`:

- `INITIALIZED_METHOD` is registered as a notification and calls
  `handler.initialized()`.
- `INITIALIZE_METHOD` is registered as a request and calls
  `handler.initialize(params)`.
- `HTTP_REQUEST_METHOD` is registered with request id forwarding and calls
  `handler.http_request(request_id, params)`, returning no JSON-RPC response on
  success.
- process routes call `exec`, `exec_read`, `exec_write`, and `terminate`.
- filesystem routes call `fs_read_file`, `fs_write_file`,
  `fs_create_directory`, `fs_get_metadata`, `fs_read_directory`, `fs_remove`,
  and `fs_copy`.

This module intentionally stops at registration and dispatch. Concrete handler
state, process execution, filesystem backends, and transport loops remain
separate module-scoped contracts.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/server/registry.rs`
- Adjacent Rust surface: `codex/codex-rs/exec-server/src/server/handler.rs`
- Python tests: `tests/test_exec_server_server_registry_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_server_registry_rs.py
python -m pytest tests/test_exec_server_server_registry_rs.py -q --tb=short
```

Latest result:

```text
4 passed
```

Completion validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_protocol_rs.py tests/test_exec_server_server_registry_rs.py -q --tb=short
10 passed

python -m pytest tests/test_exec_server_protocol_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_rpc_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short
29 passed

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_protocol_rs.py tests\test_exec_server_server_registry_rs.py
passed
```
