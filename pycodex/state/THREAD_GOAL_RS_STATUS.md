# `codex-state/src/model/thread_goal.rs` alignment

Status: `complete`

## Rust behavior boundary

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/model/thread_goal.rs`
- Public anchors:
  - `ThreadGoalStatus`
  - `ThreadGoal`
- Internal row anchor:
  - `ThreadGoalRow`

This module owns thread goal status strings, terminal/active predicates, goal
payload validation, row-shaped storage data, and row-to-model conversion.
Runtime goal-store behavior remains a separate `runtime/goals.rs` contract.

## Python mapping

- Module: `pycodex/state/model/thread_goal.py`
- Re-exported through `pycodex/state/model/__init__.py` and
  `pycodex/state/__init__.py`.

The previous package-root implementation was consolidated into the canonical
Rust-coordinate model module to avoid duplicate state model definitions. Python
now mirrors status parsing errors, `as_str`, `is_active`, `is_terminal`,
`ThreadGoalRow.from_mapping`, `ThreadGoalRow.to_thread_goal`, and
epoch-millisecond UTC conversion.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_thread_goal_model_rs.py -q
# 7 passed

python -m py_compile pycodex\state\model\thread_goal.py pycodex\state\model\__init__.py pycodex\state\__init__.py tests\test_state_thread_goal_model_rs.py
```

Coverage includes status wire strings, parsing, active/terminal predicates,
row-to-model conversion, nullable `token_budget`, UTC timestamp conversion,
dataclass status/datetime normalization, and invalid row/timestamp rejection.

## Remaining crate work

Other `codex-state` modules remain open for focused formal validation before
the crate can be promoted from `implemented_candidate` to strict `complete`.
