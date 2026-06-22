# codex-cloud-tasks-mock-client

Rust crate: `codex-cloud-tasks-mock-client`

Rust anchor: `codex/codex-rs/cloud-tasks-mock-client`

Current certified modules:

- `cloud-tasks-mock-client/src/lib.rs`
- `cloud-tasks-mock-client/src/mock.rs`

The crate root module is represented by the package-level export surface in
`pycodex/cloud_tasks_mock_client/__init__.py`: it exposes `MockClient`, matching
Rust `pub use mock::MockClient`.

The mock backend module is also represented in `__init__.py`: it provides the
Rust mock task rows, environment-specific labels, diff summaries, apply and
preflight outcomes, task text/messages, sibling attempts, and local task
creation ids.

Remaining Rust modules: none.
