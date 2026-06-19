# `codex-state/src/lib.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/lib.rs`
- Public anchors:
  - DB filename constants: `LOGS_DB_FILENAME`, `GOALS_DB_FILENAME`,
    `MEMORIES_DB_FILENAME`, `STATE_DB_FILENAME`
  - SQLite home override: `SQLITE_HOME_ENV`
  - DB telemetry metric constants:
    `DB_ERROR_METRIC`, `DB_METRIC_BACKFILL`,
    `DB_METRIC_BACKFILL_DURATION_MS`, `DB_INIT_METRIC`,
    `DB_INIT_DURATION_METRIC`, `DB_FALLBACK_METRIC`
  - Crate-root re-export surface for currently ported state models and helpers.

Runtime store types, audit/extract functions, migrations, and telemetry
functions are re-exported by Rust `lib.rs`, but their behavior belongs to their
own modules and remains outside this crate-root pass.

## Python mapping

- Module: `pycodex/state/__init__.py`

The Python package root mirrors Rust crate-root constants and re-exports the
state model/path surfaces that have module-level Python parity evidence.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_lib_rs.py -q
# 3 passed

python -m py_compile pycodex\state\__init__.py tests\test_state_lib_rs.py
```

Coverage includes DB filename/env/metric constants, crate-root DB path helper
filenames, and selected Rust public `pub use` anchors re-exported from child
state modules.

## Remaining crate work

Other `codex-state` modules remain open for focused formal validation before
the crate can be promoted from `implemented_candidate` to strict `complete`.
