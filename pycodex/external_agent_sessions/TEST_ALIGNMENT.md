# codex-external-agent-sessions test alignment

Rust crate: `codex-external-agent-sessions`

Python package: `pycodex/external_agent_sessions`

Status: `complete`

## Certified Modules

- `codex/codex-rs/external-agent-sessions/src/detect.rs` -> `pycodex/external_agent_sessions/__init__.py`
- `codex/codex-rs/external-agent-sessions/src/export.rs` -> `pycodex/external_agent_sessions/__init__.py`
- `codex/codex-rs/external-agent-sessions/src/ledger.rs` -> `pycodex/external_agent_sessions/__init__.py`
- `codex/codex-rs/external-agent-sessions/src/lib.rs` -> `pycodex/external_agent_sessions/__init__.py`
- `codex/codex-rs/external-agent-sessions/src/records.rs` -> `pycodex/external_agent_sessions/__init__.py`

## Rust Tests And Contracts

- Rust `src/records.rs` tests are migrated in `tests/test_external_agent_sessions_rs.py`.
- Rust `src/detect.rs` tests are migrated in `tests/test_external_agent_sessions_rs.py`.
- Rust `src/export.rs` tests are migrated in `tests/test_external_agent_sessions_rs.py`.
- Rust `src/lib.rs` tests are migrated in `tests/test_external_agent_sessions_rs.py`.
- Rust `src/ledger.rs` has no direct inline tests; it is covered through migrated `detect.rs` and `lib.rs` import-ledger behavior.

## Python Tests

- `tests/test_external_agent_sessions_rs.py`

## Validation

- `python -m pytest tests/test_external_agent_sessions_rs.py -q --tb=short` (`18 passed`)
- `python -m py_compile pycodex/external_agent_sessions/__init__.py tests/test_external_agent_sessions_rs.py` passed

## Remaining Gaps

No known crate-local gaps. Python uses stable dict projections for Rust `RolloutItem`/`EventMsg`/`ResponseItem` values because the local app-server protocol model is not the owner of this crate's behavior.
