# Pre-Sampling Auto-Compact Hook Boundary

## Graph slice

- `codex-rs/core/src/session/turn.rs#run_turn:133`
- `codex-rs/core/src/session/turn.rs#run_pre_sampling_compact:711`
- `codex-rs/core/src/session/turn.rs#auto_compact_token_status:659`
- `codex-rs/core/src/session/turn.rs#run_auto_compact:789`

The graph places `run_pre_sampling_compact` at the start of the common `run_turn` path, before context updates and turn input are recorded.

## Rust behavior confirmed

- `run_turn` calls `run_pre_sampling_compact` before `record_context_updates_and_set_reference_context_item`.
- Pre-sampling compact first offers a previous-model inline compact opportunity for model downshift, then checks `auto_compact_token_status`.
- If the token limit is reached, Rust runs auto compact with:
  - `InitialContextInjection::DoNotInject`
  - `CompactionReason::ContextLimit`
  - `CompactionPhase::PreTurn`
- If pre-sampling compact fails, Rust emits turn error lifecycle, applies the usage-limit goal-runtime side effect when applicable, and returns `None`.

## Python changes

- `pycodex/core/turn_runtime.py`
  - Added a pre-sampling auto-compact hook boundary after the turn context is created and before context/user input is recorded.
  - Optional previous-model hooks are recognized as `maybe_run_previous_model_inline_compact` or `run_previous_model_inline_compact`.
  - Optional compact status hooks are recognized as `auto_compact_token_status` or `get_auto_compact_token_status`.
  - Optional compact execution hooks are recognized as `run_auto_compact` or `auto_compact`.
  - Pre-sampling compact failures now complete the user turn with `last_agent_message=None` after lifecycle/goal side effects, without recording the new user input or sampling.
- `tests/test_core_turn_runtime.py`
  - Added coverage that pre-sampling compact runs before context/user input recording.
  - Added coverage that pre-sampling usage-limit compact failure does not sample, does not record the new user input, and completes the turn.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_runs_pre_sampling_auto_compact_before_recording_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pre_sampling_auto_compact_error_completes_before_input_recording tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_runs_mid_turn_auto_compact_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_mid_turn_auto_compact_usage_limit_completes_without_error_event`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_http_transport tests.test_exec_local_runtime`
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`

## Deferred

- This is still a hook boundary, not a complete local/remote compaction engine port.
- Previous-model downshift decision logic remains delegated to an optional session hook instead of being implemented inside `turn_runtime.py`.
