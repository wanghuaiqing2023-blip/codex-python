# codex-cloud-tasks-client

Python package for Rust crate `codex-cloud-tasks-client`.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/lib.rs` | `pycodex/cloud_tasks_client/__init__.py` | `complete` | Crate-root public re-export surface for API value types, `CloudBackend`, `CloudTaskError`, and `HttpClient`. |
| `src/api.rs` | `pycodex/cloud_tasks_client/api.py` | `complete` | Error display strings, status enums, value dataclasses, default values, and `CloudBackend` protocol are mapped. |
| `src/http.rs` | `pycodex/cloud_tasks_client/http.py` | `complete` | `HttpClient`, backend response projection helpers, apply/preflight mapping, and create-task request shaping are mapped with injectable adapters. |

Focused validation passed: `python -m pytest tests/test_cloud_tasks_client_lib_rs.py tests/test_cloud_tasks_client_api_rs.py tests/test_cloud_tasks_client_http_rs.py -q` -> `12 passed`.
