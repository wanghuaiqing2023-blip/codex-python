# `codex-state/src/migrations.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/migrations.rs`
- Anchors:
  - `STATE_MIGRATOR`
  - `LOGS_MIGRATOR`
  - `GOALS_MIGRATOR`
  - `MEMORIES_MIGRATOR`
  - `runtime_migrator`
  - `runtime_state_migrator`
  - `runtime_logs_migrator`
  - `runtime_goals_migrator`
  - `runtime_memories_migrator`

This module owns embedded migration-set selection and the runtime wrapper that
sets `ignore_missing=true` so older binaries can open databases migrated by
newer binaries. It does not own actual database migration execution.

## Python mapping

- Module: `pycodex/state/migrations.py`
- Re-exported through `pycodex/state/__init__.py`.

The Python port mirrors the four migration directory anchors and keeps a
dependency-light `Migrator` value object with the same runtime wrapper
semantics: preserve the base configuration while setting `ignore_missing` to
`True`.

## Validation

```powershell
python -m py_compile pycodex\state\migrations.py pycodex\state\__init__.py tests\test_state_migrations_rs.py
python -m pytest tests\test_state_migrations_rs.py -q
```

Result on 2026-06-17: `4 passed`. Re-run during status correction also passed:

```text
python -m pytest tests\test_state_migrations_rs.py -q
4 passed

python -m py_compile pycodex\state\migrations.py pycodex\state\__init__.py tests\test_state_migrations_rs.py
```

Formal parity tests cover the four base migration directory anchors,
`runtime_migrator` preserving base configuration while setting
`ignore_missing=True`, non-`Migrator` type rejection, and helper-to-base
mapping for state/logs/goals/memories runtime migrators.

## Remaining crate work

No remaining work is known for this module. `codex-state` remains pending
focused full-crate validation before strict crate-complete promotion.
