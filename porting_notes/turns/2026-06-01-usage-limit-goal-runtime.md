# Usage Limit Goal Runtime Side Effect

## Graph slice

- `codex-rs/core/src/session/turn.rs#run_turn:133`
- `codex-rs/core/src/goals.rs#GoalRuntimeEvent:139`
- `codex-rs/core/src/goals.rs#goal_runtime_apply:341`
- `codex-rs/protocol/src/error.rs#to_codex_protocol_error:220`

The dependency graph shows `GoalRuntimeEvent::UsageLimitReached` directly connected to the common `run_turn` terminal-error path.

## Rust behavior confirmed

- `run_turn` converts terminal `CodexErr` values into `CodexErrorInfo`.
- When the converted error is `UsageLimitExceeded`, Rust applies `GoalRuntimeEvent::UsageLimitReached { turn_context }`.
- That goal-runtime side effect is best-effort: failures are warned about but do not replace the user-facing turn error.
- The same usage-limit hook appears on pre-sampling compact and mid-turn auto-compact error paths, which remain broader follow-up work in Python.

## Python changes

- `pycodex/core/turn_runtime.py`
  - `_handle_terminal_sampling_error` now computes protocol error info once, emits turn error lifecycle, applies a best-effort `goal_runtime_apply` shim for usage-limit errors, then sends the terminal error event.
  - The shim sends `{"type": "usage_limit_reached", "turn_context": turn_context}` when a session or mapping session exposes `goal_runtime_apply`.
  - Goal-runtime failures are swallowed so the original terminal error still reaches the user, matching Rust's best-effort behavior.
- `tests/test_core_turn_runtime.py`
  - The usage-limit terminal error test now asserts the goal-runtime usage-limit event.
  - Added coverage that a failing goal runtime does not prevent a completed terminal-error turn for another `UsageLimitExceeded` source (`quota_exceeded`).

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_usage_limit_rate_limits_on_terminal_error tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_goal_runtime_usage_limit_errors_are_best_effort tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_usage_limit_error_lifecycle`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_http_transport tests.test_exec_local_runtime`
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`

## Deferred

- Pre-sampling compact and mid-turn auto-compact usage-limit branches still need their own graph-guided Python slice.
- This is a compatibility shim for goal-runtime notification, not a full Python port of Rust's goal accounting engine.
