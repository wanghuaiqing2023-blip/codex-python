# codex-app-server src/request_processors.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors.rs`

Python module: `pycodex/app_server/request_processors.py`

Status: `complete`

## Scope

This file tracks only the parent Rust module. The concrete request handlers in
`src/request_processors/*.rs` remain separate module-scoped work.

Covered behavior:

- Rust child module declaration inventory and declaration order.
- Rust crate-local request processor re-export inventory.
- Rust crate-local helper re-export inventory, with `#[cfg(test)]` helpers kept
  in a separate Python constant.
- `build_api_turns_from_rollout_items(...)` replay behavior: filter rollout
  entries through `codex_rollout::is_persisted_rollout_item` with
  `EventPersistenceMode::Limited`, feed persisted items into
  `ThreadHistoryBuilder`, and return `finish()`.

Deferred/out of module:

- Concrete request processor implementations in child modules.
- Tokio runtime routing, JSON-RPC dispatch, and transport interaction.
- Child-module Rust tests and fixtures.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors.rs`

Python parity tests:

- `tests/test_app_server_request_processors_rs.py`

Focused validation passed on 2026-06-19:

- `python -m pytest tests/test_app_server_request_processors_rs.py -q` -> 4 passed.
- `python -m py_compile pycodex/app_server/request_processors.py tests/test_app_server_request_processors_rs.py`
