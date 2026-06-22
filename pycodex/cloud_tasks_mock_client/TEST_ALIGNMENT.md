# codex-cloud-tasks-mock-client test alignment

Rust crate: `codex-cloud-tasks-mock-client`

Python package: `pycodex/cloud_tasks_mock_client`

Status: `complete`

Certified modules:

- `codex/codex-rs/cloud-tasks-mock-client/src/lib.rs` -> `pycodex/cloud_tasks_mock_client/__init__.py`
- `codex/codex-rs/cloud-tasks-mock-client/src/mock.rs` -> `pycodex/cloud_tasks_mock_client/__init__.py`

Remaining Rust modules: none.

Rust tests and fixtures:

- No standalone Rust test functions are registered for this crate; source
  contract is derived from `src/lib.rs` and `src/mock.rs`.

Validation:

- `python -m pytest tests/test_cloud_tasks_mock_client.py -q` (`5 passed`)
- `python -m py_compile pycodex/cloud_tasks_mock_client/__init__.py tests/test_cloud_tasks_mock_client.py` (passed)
