# codex-exec-server src/server.rs Status

Rust source: `codex/codex-rs/exec-server/src/server.rs`

Python surface: `pycodex.exec_server`

Status: `complete`

## Scope

This module is the server facade for the exec-server crate.  Rust keeps the
implementation intentionally thin: it declares the server submodules, re-exports
`DEFAULT_LISTEN_URL` and `ExecServerListenUrlParseError`, and forwards
`run_main(listen_url, runtime_paths)` to `transport::run_transport(...)`.

Python now mirrors that boundary with an async `run_main(...)` that delegates to
`run_transport(...)` without changing the listen URL or runtime paths.  Concrete
websocket serving, Axum routing, and socket lifetime management remain owned by
`src/server/transport.rs` and the remaining runtime gaps tracked for the crate.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/server.rs`
- Adjacent Rust source: `codex/codex-rs/exec-server/src/server/transport.rs`
- Python tests:
  - `tests/test_exec_server_server_rs.py::test_server_reexports_transport_public_surface`
  - `tests/test_exec_server_server_rs.py::test_run_main_forwards_to_transport`

## Validation

```powershell
python -m pytest tests/test_exec_server_server_rs.py tests/test_exec_server_transport_rs.py -q --tb=short
python -m pytest tests/test_exec_server_server_rs.py tests/test_exec_server_transport_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_process_handler_rs.py -q --tb=short
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_server_rs.py
```

Latest result:

```text
2026-06-21 server/transport focused validation: 9 passed
2026-06-21 adjacent processor/registry/process-handler regression: 17 passed
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py, tests\test_exec_server_server_rs.py, and tests\test_exec_server_transport_rs.py
```
