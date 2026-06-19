# codex-cloud-tasks-client test alignment

Rust crate: `codex-cloud-tasks-client`

Python package: `pycodex/cloud_tasks_client`

Status: `complete`

Certified modules:

- `codex/codex-rs/cloud-tasks-client/src/lib.rs` -> `pycodex/cloud_tasks_client/__init__.py`
- `codex/codex-rs/cloud-tasks-client/src/api.rs` -> `pycodex/cloud_tasks_client/api.py`
- `codex/codex-rs/cloud-tasks-client/src/http.rs` -> `pycodex/cloud_tasks_client/http.py`

Remaining Rust modules:

- None.

Rust tests and fixtures:

- No standalone Rust test functions are registered for this crate; source
  contracts are derived from `src/lib.rs`, `src/api.rs`, and `src/http.rs`.

Validation:

- `python -m pytest tests/test_cloud_tasks_client_lib_rs.py tests/test_cloud_tasks_client_api_rs.py tests/test_cloud_tasks_client_http_rs.py -q` (`12 passed`)
- `python -m py_compile pycodex/cloud_tasks_client/__init__.py pycodex/cloud_tasks_client/api.py pycodex/cloud_tasks_client/http.py tests/test_cloud_tasks_client_lib_rs.py tests/test_cloud_tasks_client_api_rs.py tests/test_cloud_tasks_client_http_rs.py` (passed)
