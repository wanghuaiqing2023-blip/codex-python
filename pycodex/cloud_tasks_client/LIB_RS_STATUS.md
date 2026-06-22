# codex-cloud-tasks-client src/lib.rs status

Rust module: `codex/codex-rs/cloud-tasks-client/src/lib.rs`

Python module: `pycodex/cloud_tasks_client/__init__.py`

Status: `complete`

## Contract

Rust `src/lib.rs` declares the private `api` and `http` modules, then publicly
re-exports:

- `ApplyOutcome`
- `ApplyStatus`
- `AttemptStatus`
- `CloudBackend`
- `CloudTaskError`
- `CreatedTask`
- `DiffSummary`
- `Result`
- `TaskId`
- `TaskListPage`
- `TaskStatus`
- `TaskSummary`
- `TaskText`
- `TurnAttempt`
- `HttpClient`

The Python package root exposes the same names in `__all__` and re-exports
`HttpClient` from the completed `src/http.rs` mapping.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks-client/src/lib.rs`
- Python source: `pycodex/cloud_tasks_client/__init__.py`
- Python test: `tests/test_cloud_tasks_client_lib_rs.py`

- Focused validation: `python -m pytest tests/test_cloud_tasks_client_lib_rs.py tests/test_cloud_tasks_client_api_rs.py tests/test_cloud_tasks_client_http_rs.py -q` -> `12 passed`
