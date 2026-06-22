# src/request_processors/thread_goal_processor.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_goal_processor.rs`

Python mapping:

- `pycodex/app_server/request_processors_thread_goal_processor.py`
- `tests/test_app_server_request_processors_thread_goal_processor_rs.py`

Behavior covered:

- `ThreadGoalRequestProcessor` dependency storage, constructor shape, and
  public `thread_goal_set`, `thread_goal_get`, `thread_goal_clear`,
  `emit_resume_goal_snapshot_and_continue`, and `pending_resume_goal_state`
  entrypoints are mirrored with injectable runtime boundaries.
- Goals feature gating maps disabled calls to invalid-request errors matching
  Rust's `"goals feature is disabled"` branch.
- Thread id parsing, ephemeral running-thread rejection, state DB
  materialization fallback, rollout-path lookup, and missing sqlite state DB
  errors are projected.
- Goal status conversion, positive budget validation, objective trimming and
  validation call-sites, state-goal to protocol-goal projection, and snapshot
  updated/cleared notification projection are covered.
- Set/get/clear request paths preserve the Rust response-before-notification
  ordering, listener-command preferred delivery, fallback server
  notifications, set preview update, and running-thread external-goal mutation
  hooks.

Intentional boundaries:

- Concrete rollout reconciliation, rollout file discovery, `codex_state`
  sqlite implementation, `ThreadManager` runtime objects, Tokio channels, and
  actual spawned continuation execution remain injected dependencies owned by
  neighboring crates/modules.
- This module is complete for its module-scoped behavior contract; concrete
  sibling-owned runtime effects remain boundaries until broader crate-level
  validation/integration.

Validation status:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_goal_processor_rs.py -q`
  -> 10 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_goal_processor.py tests/test_app_server_request_processors_thread_goal_processor_rs.py`.
