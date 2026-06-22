# codex-exec-server/src/fs_helper_main.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/fs_helper_main.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the helper subprocess entrypoint wiring:

- reads one complete JSON `FsHelperRequest` from stdin/input bytes.
- deserializes using the same helper request `operation`/`params` envelope.
- calls the already-ported `run_direct_request(...)` helper dispatch.
- wraps successful payloads as `FsHelperResponse::Ok`.
- wraps direct request JSON-RPC errors as `FsHelperResponse::Error`.
- writes compact JSON followed by a newline to stdout/output bytes.
- malformed input prints `fs sandbox helper failed: ...` to stderr and exits
  with code 1.
- successful helper execution exits with code 0.

Tokio runtime construction is adapted to Python's standard-library
`asyncio.run(...)`; no third-party runtime dependency is introduced.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/fs_helper_main.rs`
- Rust export: `codex/codex-rs/exec-server/src/lib.rs`
- Rust integration harness:
  `codex/codex-rs/exec-server/tests/common/mod.rs`
- Python tests: `tests/test_exec_server_fs_helper_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_fs_helper_rs.py
python -m pytest tests/test_exec_server_fs_helper_rs.py -q --tb=short
```

Latest result:

```text
10 passed
```

Completion validation on 2026-06-21:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_fs_helper_rs.py
python -m pytest tests/test_exec_server_fs_helper_rs.py -q --tb=short
10 passed
python -m pytest tests/test_exec_server_fs_helper_rs.py tests/test_exec_server_fs_sandbox_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py -q --tb=short
46 passed, 1 skipped
```
