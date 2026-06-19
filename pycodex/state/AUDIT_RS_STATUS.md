# `codex-state/src/audit.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/audit.rs`
- Public anchors:
  - `ThreadStateAuditRow`
  - `read_thread_state_audit_rows`

This module owns read-only diagnostic access to persisted thread rows. It must
not create, migrate, or repair the state database.

## Python mapping

- Module: `pycodex/state/audit.py`
- Re-exported through `pycodex/state/__init__.py`.

The Python port mirrors the row shape, opens SQLite using standard-library
`sqlite3` in read-only URI mode, queries `id`, `rollout_path`, `archived`,
`source`, and `model_provider` from `threads`, and converts the integer
`archived` column to a boolean. The async Rust API shape is preserved with an
`async` wrapper around a worker-thread read.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_audit_rs.py -q
# 4 passed

python -m py_compile pycodex\state\audit.py pycodex\state\__init__.py tests\test_state_audit_rs.py
```

Coverage includes audit row validation/path normalization, read-only SQLite
column selection, integer-to-bool `archived` conversion, missing DB
non-creation, and invalid archived storage type rejection.

## Remaining crate work

Other `codex-state` modules remain open for focused formal validation before
the crate can be promoted from `implemented_candidate` to strict `complete`.
