# codex-cloud-tasks-mock-client src/lib.rs status

Rust coordinate: `codex/codex-rs/cloud-tasks-mock-client/src/lib.rs`

Python coordinate: `pycodex/cloud_tasks_mock_client/__init__.py`

Status: `complete`

Behavior contract:

- declare the `mock` module as an internal implementation module.
- publicly re-export `mock::MockClient` at the crate root.

Evidence:

- `pycodex/cloud_tasks_mock_client/__init__.py` exposes `MockClient` in its
  package root and `__all__`, matching Rust `pub use mock::MockClient`.
- The implementation details from Rust `src/mock.rs` remain a separate module
  contract and are not certified by this file.

Validation:

- Deferred by project policy until all `codex-cloud-tasks-mock-client`
  functional modules are complete. Remaining module: `src/mock.rs`.
