# codex-cloud-tasks-client src/http.rs status

Rust module: `codex/codex-rs/cloud-tasks-client/src/http.rs`

Python module: `pycodex/cloud_tasks_client/http.py`

Status: `complete`

## Contract

Rust `src/http.rs` owns:

- `HttpClient` construction and builder methods
- `CloudBackend` method forwarding for list, details, text, attempts, apply,
  preflight, and create-task behavior
- Backend task-list/detail response projection into API structs
- Assistant message, prompt, error, turn-attempt, diff, status, timestamp,
  attempt-count, and diff-summary helper logic
- Apply/preflight outcome mapping from git-apply result status
- Create-task request body construction including `CODEX_STARTING_DIFF` and
  `best_of_n` metadata

Python maps this with a standard-library implementation that accepts injectable
backend and git-apply adapters, avoiding live cloud/network dependencies while
preserving the Rust module-scoped behavior contract.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks-client/src/http.rs`
- Python source: `pycodex/cloud_tasks_client/http.py`
- Python test: `tests/test_cloud_tasks_client_http_rs.py`
- Focused validation: `python -m pytest tests/test_cloud_tasks_client_lib_rs.py tests/test_cloud_tasks_client_api_rs.py tests/test_cloud_tasks_client_http_rs.py -q` -> `12 passed`
