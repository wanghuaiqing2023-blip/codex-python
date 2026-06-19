# codex-cloud-tasks-client src/api.rs status

Rust module: `codex/codex-rs/cloud-tasks-client/src/api.rs`

Python module: `pycodex/cloud_tasks_client/api.py`

Status: `complete`

## Contract

Rust `src/api.rs` owns:

- `Result<T> = std::result::Result<T, CloudTaskError>`
- `CloudTaskError` variants and display strings:
  - `Unimplemented("x")` -> `unimplemented: x`
  - `Http("x")` -> `http error: x`
  - `Io("x")` -> `io error: x`
  - `Msg("x")` -> `x`
- `TaskId` transparent string wrapper
- `TaskStatus` serialized with kebab-case names
- `AttemptStatus` with `Unknown` as the default
- `ApplyStatus` serialized with lowercase names
- `TaskSummary`, `TurnAttempt`, `ApplyOutcome`, `CreatedTask`,
  `TaskListPage`, `DiffSummary`, and `TaskText`
- `TaskText::default()` with `attempt_status = AttemptStatus::Unknown`
- `CloudBackend` async method surface

Python mirrors these as immutable dataclasses, string enums, error helper
constructors, and a runtime-checkable `Protocol`.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks-client/src/api.rs`
- Python source: `pycodex/cloud_tasks_client/api.py`
- Python test: `tests/test_cloud_tasks_client_api_rs.py`

- Focused validation: `python -m pytest tests/test_cloud_tasks_client_lib_rs.py tests/test_cloud_tasks_client_api_rs.py tests/test_cloud_tasks_client_http_rs.py -q` -> `12 passed`
