# codex-state `src/runtime/goals.rs`

Rust module: `codex/codex-rs/state/src/runtime/goals.rs`

Python module: `pycodex/state/runtime/goals.py`

Status: `complete`

## Behavior Contract

- Mirrors the `GoalStore` surface for the independent goals database
  (`goals_1.sqlite`) and `thread_goals` table.
- Provides `GoalUpdate`, `GoalAccountingMode`, and `GoalAccountingOutcome`
  equivalents for update and accounting behavior.
- Preserves replace/insert/delete/get semantics, including duplicate insert
  returning `None` and replacement resetting usage counters.
- Preserves goal-id optimistic concurrency checks via `expected_goal_id`.
- Preserves budget-limit transitions for creation, update, active-only
  accounting, stopped-goal accounting, and the paused/blocked preservation rule
  for already budget-limited goals.
- Preserves `pause_active_thread_goal` and
  `usage_limit_active_thread_goal` status filters.

## Evidence

- Rust source:
  `codex/codex-rs/state/src/runtime/goals.rs`
- Rust schema:
  `codex/codex-rs/state/goals_migrations/0001_thread_goals.sql`
- Rust tests in `runtime/goals.rs` cover replace/update/get, duplicate insert,
  stale goal versions, partial updates, pause/usage-limit status filters,
  budget-limit transitions, and accounting modes.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_runtime_goals_rs.py -q
# 7 passed

python -m py_compile pycodex\state\runtime\goals.py pycodex\state\runtime\__init__.py pycodex\state\__init__.py tests\test_state_runtime_goals_rs.py
```

Coverage includes replace/update/get/delete, insert-or-ignore duplicate
handling, expected-goal-id optimistic concurrency for updates and accounting,
active status filters, immediate budget-limit transitions, budget-limited
pause/block preservation, accounting modes, unchanged token-budget updates, and
path-backed SQLite store reopening.

## Known Gaps

- No known gaps for `src/runtime/goals.rs` module behavior.
- `StateRuntime` construction, DB opening/migration, thread deletion cascade
  through the old state DB, and cross-store orchestration remain separate
  module contracts.
