# codex-state `src/runtime/backfill.rs`

Rust module: `codex/codex-rs/state/src/runtime/backfill.rs`

Python module: `pycodex/state/runtime/backfill.py`

Status: `complete`

## Behavior Contract

- Mirrors `StateRuntime` backfill lifecycle helpers for the singleton
  `backfill_state` row.
- Ensures row `id = 1` exists with Rust migration defaults before each public
  operation.
- Reads `status`, `last_watermark`, and `last_success_at` through the ported
  `BackfillState.try_from_row` model conversion.
- Implements claim semantics from Rust: a claim succeeds unless the backfill is
  complete or currently running with a non-expired `updated_at` lease.
- Mirrors running/checkpoint/complete updates, including
  `COALESCE(?, last_watermark)` for completion without a new watermark.

## Evidence

- Rust source:
  `codex/codex-rs/state/src/runtime/backfill.rs`
- Rust migration:
  `codex/codex-rs/state/migrations/0008_backfill_state.sql`
- Rust tests:
  `backfill_state_persists_progress_and_completion`
  and `backfill_claim_is_singleton_until_stale_and_blocked_when_complete`

## Validation

Formal parity validation passed on 2026-06-17:

```text
python -m pytest tests\test_state_runtime_backfill_rs.py -q
5 passed

python -m py_compile pycodex\state\runtime\backfill.py pycodex\state\runtime\__init__.py pycodex\state\__init__.py tests\test_state_runtime_backfill_rs.py
```

The pytest suite maps Rust's two in-module tests and adds focused coverage for
`COALESCE(?, last_watermark)`, negative lease clamping to zero seconds, and the
Python path-based SQLite compatibility shim.

## Known Gaps

- No known gaps for `src/runtime/backfill.rs`.
- Broader `StateRuntime` initialization, migrations, thread stores, log DB, and
  other runtime modules remain separate contracts.
