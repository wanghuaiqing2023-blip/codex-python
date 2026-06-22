# request_processors/fs_processor.rs Status

Rust module: `codex-app-server/src/request_processors/fs_processor.rs`

Python module: `pycodex/app_server/request_processors_fs_processor.py`

Status: `complete`

## Covered Contract

- Processor construction preserves Rust's injected environment manager and
  filesystem watch manager boundary.
- `file_system()` requires a local environment and maps missing local
  filesystem to `internal_error("local filesystem is not configured")`.
- `read_file` delegates to the executor filesystem with no sandbox and returns
  base64-encoded bytes.
- `write_file` validates `dataBase64`, maps invalid base64 to Rust's
  invalid-request message, and delegates decoded bytes to the filesystem.
- `create_directory`, `remove`, and `copy` preserve Rust default options:
  create recursive defaults to true, remove recursive/force default to true,
  and copy passes the explicit recursive flag.
- `get_metadata` and `read_directory` project executor filesystem metadata and
  directory entries into app-server protocol response types.
- Filesystem errors map invalid-input-like failures to invalid request and all
  other errors to internal error.
- `watch`, `unwatch`, and `connection_closed` delegate to `FsWatchManager`
  after checking that the local filesystem is configured.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/fs_processor.rs`
- Python parity tests staged in
  `tests/test_app_server_request_processors_fs_processor_rs.py`.
- Focused validation completed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_fs_processor_rs.py -q`
  -> 7 passed.
- Syntax validation completed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_fs_processor.py tests/test_app_server_request_processors_fs_processor_rs.py`.

## Known Gaps

- Concrete filesystem access, sandbox enforcement, and file watching remain
  injected environment/watch-manager responsibilities.
