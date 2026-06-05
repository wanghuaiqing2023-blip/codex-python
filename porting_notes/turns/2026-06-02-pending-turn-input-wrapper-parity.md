# Pending turn input wrapper parity

## Upstream slice

- Graph-guided target: `codex-rs/core/src/session/turn.rs#run_turn` and `run_hooks_and_record_inputs`.
- Rust source confirmed:
  - Pending input is represented as `TurnInput::UserInput(Vec<UserInput>)` or `TurnInput::ResponseItem(ResponseItem)`.
  - `inspect_pending_input` runs the user-prompt-submit hook only for `TurnInput::UserInput`.
  - A blocked input stops the drain only when no later non-empty user input was accepted in the same batch.
  - `TurnInput::ResponseItem` is recorded directly and does not run the user prompt hook.

## Python port

- Extended `pycodex.core.turn_runtime` pending input parsing to recognize explicit wrapper shapes:
  - `{"type": "user_input" | "UserInput", "items"/"input"/"content": ...}`
  - `{"type": "response_item" | "ResponseItem", "item"/"response_item": ...}`
- Kept existing support for bare `UserInput`, bare `ResponseItem`, and response-item mappings.
- Added a focused mixed pending-input test proving that a blocked user input plus a later accepted user input continues to a follow-up model request, while response-item wrappers are recorded directly.

## Validation

- `python -m py_compile pycodex\core\turn_runtime.py tests\test_core_turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_mixed_pending_input_continues_when_later_user_input_accepted tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_blocks_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_records_context_after_input`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_defers_pending_input_behind_model_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call`
- `python -m unittest tests.test_local_http_core_smoke_suite`

## Known gaps

- This is a compatibility slice for the core in-memory/runtime path.
- Full app-server input transport parity remains deferred unless the core CLI path directly depends on it.
