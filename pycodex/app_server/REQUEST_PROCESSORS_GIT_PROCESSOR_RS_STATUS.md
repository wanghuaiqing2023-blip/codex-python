# codex-app-server request_processors/git_processor.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors/git_processor.rs`

Python module: `pycodex/app_server/request_processors_git_processor.py`

Status: `complete`

## Scope

Covered behavior:

- `GitRequestProcessor::new()` returns a stateless processor.
- `git_diff_to_remote(...)` delegates to `git_diff_to_origin(...)`.
- Successful `git_diff_to_remote(cwd)` results are projected to
  `GitDiffToRemoteResponse { sha, diff }`.
- Missing diff results are converted to `invalid_request` with the Rust-shaped
  cwd debug message.

Deferred/out of module:

- Actual git graph/diff computation remains owned by `codex-git-utils`.
- MessageProcessor JSON-RPC dispatch and response-envelope wrapping remain
  neighboring runtime boundaries.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors/git_processor.rs`

Python parity tests:

- `tests/test_app_server_request_processors_git_processor_rs.py`

Focused validation passed on 2026-06-19:

- `python -m pytest tests/test_app_server_request_processors_git_processor_rs.py -q`
  -> 4 passed.
- `python -m py_compile pycodex/app_server/request_processors_git_processor.py tests/test_app_server_request_processors_git_processor_rs.py`
