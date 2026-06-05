# Mid-Turn Auto-Compact Hook Boundary

## Graph slice

- `codex-rs/core/src/session/turn.rs#run_turn:133`
- `codex-rs/core/src/session/turn.rs#auto_compact_token_status:659`
- `codex-rs/core/src/session/turn.rs#run_auto_compact:789`
- `codex-rs/core/src/goals.rs#GoalRuntimeEvent:139`

The graph shows mid-turn auto-compaction directly on the common `run_turn` loop after sampling and before follow-up model requests.

## Rust behavior confirmed

- After a sampling request, Rust checks `auto_compact_token_status`.
- If the token limit is reached and the turn still needs follow-up work, Rust runs `run_auto_compact` with:
  - `InitialContextInjection::BeforeLastUserMessage`
  - `CompactionReason::ContextLimit`
  - `CompactionPhase::MidTurn`
- If mid-turn compaction fails, Rust emits turn error lifecycle, applies the usage-limit goal-runtime side effect when the compact error maps to `UsageLimitExceeded`, and returns `None` without sending the ordinary terminal error event.
- If compaction succeeds, the turn continues toward the follow-up request.

## Python changes

- `pycodex/core/turn_runtime.py`
  - Added an optional mid-turn auto-compact hook boundary.
  - If a session exposes `auto_compact_token_status` or `get_auto_compact_token_status`, the turn runner checks `token_limit_reached` before a follow-up request.
  - If a session exposes `run_auto_compact` or `auto_compact`, the runner calls it with Python string equivalents of the Rust compaction settings.
  - Compaction `CodexErr` failures emit turn error lifecycle and best-effort usage-limit goal-runtime side effects, then complete the turn with `last_agent_message=None`.
- `tests/test_core_turn_runtime.py`
  - Added coverage that mid-turn auto-compact runs before a tool follow-up.
  - Added coverage that a usage-limit compaction failure completes the turn without sending a normal terminal error event.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_runs_mid_turn_auto_compact_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_mid_turn_auto_compact_usage_limit_completes_without_error_event`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_http_transport tests.test_exec_local_runtime`
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`

## Deferred

- Pre-sampling compaction still needs a separate Python slice because the current request-preparation structure records context/user input earlier than Rust's pre-sampling compact point.
- This hook boundary does not implement the compacting engine itself; it lets existing or future Python session runtimes plug in local/remote compaction without changing the core turn loop again.
