# codex-exec-server/src/sandboxed_file_system.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/sandboxed_file_system.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the module-local sandboxed filesystem wrapper:

- `SandboxedFileSystem.new(runtime_paths)` builds a wrapper around
  `FileSystemSandboxRunner.new(runtime_paths)`.
- every filesystem operation requires a sandbox context that should run in the
  platform sandbox.
- helper requests omit nested `sandbox` fields, matching the Rust handoff to
  the sandboxed helper process.
- `read_file` decodes helper `dataBase64` and maps invalid base64 to a
  filesystem error with the Rust method/field prefix.
- `write_file`, `create_directory`, `remove`, and `copy` encode options into
  the corresponding helper request params.
- metadata and directory helper responses project back into filesystem-domain
  `FileMetadata` and `ReadDirectoryEntry` values.
- helper `not_found` maps to `FileNotFoundError`, `invalid_request` maps to
  `ValueError`, and other helper errors map to `OSError`.
- unexpected helper payload variants are mapped through the same filesystem
  error path.

Concrete `FileSystemSandboxRunner.run(...)` execution remains owned by
`src/fs_sandbox.rs` and is still an explicit runtime boundary.

## Evidence

- Rust source:
  `codex/codex-rs/exec-server/src/sandboxed_file_system.rs`
- Rust integration fixture:
  `codex/codex-rs/exec-server/tests/file_system.rs::sandboxed_file_system_helper_finds_bwrap_on_preserved_path`
- Python tests:
  `tests/test_exec_server_sandboxed_file_system_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_sandboxed_file_system_rs.py
python -m pytest tests/test_exec_server_sandboxed_file_system_rs.py -q --tb=short
```

Latest result:

```text
8 passed
```

Completion validation on 2026-06-21:

```text
python -m pytest tests/test_exec_server_sandboxed_file_system_rs.py -q --tb=short
8 passed

python -m pytest tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_fs_sandbox_rs.py -q --tb=short
36 passed, 1 skipped

python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_sandboxed_file_system_rs.py
passed
```
