# codex-state `src/model/backfill_state.rs`

Rust module: `codex/codex-rs/state/src/model/backfill_state.rs`

Python module: `pycodex/state/model/backfill_state.py`

Status: `complete`

## Alignment

- Added `BackfillStatus` with Rust wire values `pending`, `running`, and
  `complete`, plus `as_str()` and `parse()`.
- Added `BackfillState` with Rust defaults: `Pending`, no watermark, and no
  last success timestamp.
- Added row/mapping conversion for `status`, `last_watermark`, and
  `last_success_at`.
- Added `epoch_seconds_to_datetime()` matching Rust's UTC timestamp conversion
  and invalid timestamp error behavior.
- Re-exported the model from `pycodex.state`.

## Validation

```powershell
python -m py_compile pycodex\state\model\backfill_state.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_backfill_state_rs.py
python -m pytest tests\test_state_backfill_state_rs.py -q
```

Result on 2026-06-17: `7 passed`.

Formal parity tests cover persisted status strings and parsing, unknown status
rejection, Rust default state, row conversion with UTC epoch-second timestamp
hydration, nullable optional fields, invalid field types, and invalid Unix
timestamp rejection.

## Remaining

- No known gaps for `src/model/backfill_state.rs`.
- `codex-state` remains pending focused full-crate validation before strict
  crate-complete promotion.
