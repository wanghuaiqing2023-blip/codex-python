# codex-exec-server/src/fs_helper.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/fs_helper.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the module-scoped helper contract from Rust:

- `CODEX_FS_HELPER_ARG1`
- `FsHelperRequest` serde tag/content shape with fs method names as
  `operation`
- `FsHelperResponse` `status`/`payload` shape
- `FsHelperPayload` `operation`/`response` shape and `expect_*` typed
  response checks
- `unexpected_response(...)` JSON-RPC internal-error text
- `run_direct_request(...)` direct filesystem request handling for
  read/write/create-directory/metadata/read-directory/remove/copy
- `map_fs_error(...)` mapping for not-found, invalid-input/permission, and
  internal errors

The Rust module's child-process entrypoint wiring is owned by sibling module
`src/fs_helper_main.rs` and tracked in `FS_HELPER_MAIN_RS_STATUS.md`.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/fs_helper.rs`
- Rust test: `helper_requests_use_fs_method_names`
- Adjacent Rust source: `codex/codex-rs/exec-server/src/local_file_system.rs`
  for `DirectFileSystem` operation semantics
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
