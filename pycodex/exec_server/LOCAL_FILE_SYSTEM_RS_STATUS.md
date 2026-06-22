# codex-exec-server/src/local_file_system.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/local_file_system.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the independently testable portion of
`local_file_system.rs`:

- `CopyOptions`, `CreateDirectoryOptions`, `RemoveOptions`, `FileMetadata`, and
  `ReadDirectoryEntry`
- `DirectFileSystem` read/write/create-directory/metadata/read-directory/remove
  and copy behavior
- `UnsandboxedFileSystem` forwarding with platform-sandbox rejection
- `LocalFileSystem` delegation to the unsandboxed filesystem when no sandbox
  context requests a sandboxed backend
- `resolve_existing_path(...)`
- `current_sandbox_cwd(...)`
- `LOCAL_FS`

The `SandboxedFileSystem` backend selected by `LocalFileSystem::with_runtime_paths`
is not implemented in this slice. That remains separate debt with the sandboxed
filesystem/runtime execution path.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/local_file_system.rs`
- Rust test: `resolve_existing_path_handles_symlink_parent_dotdot_escape`
- Python tests: `tests/test_exec_server_local_file_system_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_local_file_system_rs.py
python -m pytest tests/test_exec_server_local_file_system_rs.py -q --tb=short
python -m pytest tests/test_exec_server_local_file_system_rs.py tests/test_exec_server_file_system_handler_rs.py tests/test_exec_server_sandboxed_file_system_rs.py tests/test_exec_server_fs_sandbox_rs.py -q --tb=short
```

Latest result on this platform:

```text
2026-06-21 local-file-system focused validation: 9 passed, 1 skipped
2026-06-21 adjacent filesystem handler/sandbox regression: 36 passed, 1 skipped
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py and tests\test_exec_server_local_file_system_rs.py
```

The skipped test is the symlink-parent Rust parity test when the host platform
does not permit creating directory symlinks.
