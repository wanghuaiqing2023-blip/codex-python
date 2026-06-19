# `codex-state/src/model/log.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/model/log.rs`
- Public model anchors:
  - `LogEntry`
  - `LogRow`
  - `LogQuery`

This module owns the log data shapes used by the state crate. SQLite querying,
filter compilation, and persistence belong to `src/log_db.rs` and runtime
modules, and are intentionally outside this module pass.

## Python mapping

- Module: `pycodex/state/model/log.py`
- Re-exported through `pycodex/state/model/__init__.py` and
  `pycodex/state/__init__.py`.

The Python port mirrors Rust field names and default values. Integer fields are
validated as signed 64-bit values where Rust uses `i64`; `LogQuery.limit`
mirrors Rust `Option<usize>` as a non-negative optional integer.

## Validation

```powershell
python -m py_compile pycodex\state\model\log.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_log_model_rs.py
python -m pytest tests\test_state_log_model_rs.py -q
```

Result on 2026-06-17: `6 passed`. Re-run during status correction also passed:

```text
python -m pytest tests\test_state_log_model_rs.py -q
6 passed

python -m py_compile pycodex\state\model\log.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_log_model_rs.py
```

Formal parity tests cover `LogEntry` mapping shape, Rust `i64` and string
field boundaries, `LogRow.from_mapping`, invalid row fields, `LogQuery`
defaults, sequence normalization, `Option<usize>` limit validation, and bool
field validation.

## Remaining crate work

No known gaps for `src/model/log.rs`. `codex-state` remains pending focused
full-crate validation before strict crate-complete promotion.
