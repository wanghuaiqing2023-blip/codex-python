# codex-exec-server/src/server/file_system_handler.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/server/file_system_handler.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the module-local filesystem RPC handler behavior:

- `FileSystemHandler.new(runtime_paths)` builds a handler around
  `LocalFileSystem.with_runtime_paths(runtime_paths)`.
- `read_file` returns `FsReadFileResponse.data_base64` from filesystem bytes.
- `write_file` validates `data_base64`, maps invalid base64 to
  `invalid_request`, and writes decoded bytes.
- `create_directory` defaults omitted `recursive` to `true`.
- `get_metadata` projects backend metadata into `FsGetMetadataResponse`.
- `read_directory` projects backend directory entries into protocol entries.
- `remove` defaults omitted `recursive` and `force` to `true`.
- `copy` forwards `recursive` through `CopyOptions`.
- filesystem errors use the Rust module's not-found, invalid-request, and
  internal-error mapping.

The module does not claim the concrete sandboxed filesystem backend or helper
subprocess wiring; those remain separate contracts under `local_file_system.rs`
and fs-helper/runtime orchestration.

## Evidence

- Rust source:
  `codex/codex-rs/exec-server/src/server/file_system_handler.rs`
- Rust test:
  `no_platform_sandbox_policies_do_not_require_configured_sandbox_helper`
- Python tests:
  `tests/test_exec_server_file_system_handler_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_file_system_handler_rs.py
python -m pytest tests/test_exec_server_file_system_handler_rs.py -q --tb=short
python -m pytest tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_protocol_rs.py -q --tb=short
```

Latest result:

```text
2026-06-21 file-system-handler focused validation: 6 passed
2026-06-21 adjacent handler/registry/protocol regression: 20 passed
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py and tests\test_exec_server_file_system_handler_rs.py
```
