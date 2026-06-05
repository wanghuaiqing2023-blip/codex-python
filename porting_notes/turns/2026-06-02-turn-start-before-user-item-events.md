## TurnStarted before user item events

### Upstream slice

- Graph-guided core path: `tasks/regular.rs` -> `TurnStarted` -> `session/turn.rs::run_turn` -> `run_hooks_and_record_inputs` -> `record_user_prompt_and_emit_turn_item`.
- Rust behavior confirmed from `codex/codex-rs/core/src/tasks/regular.rs`: regular turns emit `TurnStarted` before entering `run_turn`. User input is then recorded inside `run_turn`, which emits `UserMessage` item lifecycle events.

### Python change

- `pycodex/core/turn_runtime.py` now emits `task_started` inside the sampling prepare path immediately after creating the turn context, before pre-sampling compaction, context recording, or user prompt recording.
- The normal sampling path no longer emits `task_started` after prepare, and pre-sampling compact/user-input-blocked error paths no longer emit a duplicate lifecycle event.
- This aligns InMemory session event ordering to `task_started -> item_started(UserMessage) -> item_completed(UserMessage) -> task_complete`.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py pycodex\core\session_runtime.py`
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_emits_turn_lifecycle_events tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_record_user_prompt_emits_turn_item_events`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_turn_lifecycle_events tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_blocks_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pre_sampling_auto_compact_error_completes_before_input_recording`
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_http_sampling_uses_pending_input_followup tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_record_user_prompt_emits_turn_item_events`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_empty_input_drains_pending_before_first_request tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_defers_pending_input_behind_model_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_compacts_before_draining_pending_only_followup`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_stream_bad_tool_search_arguments tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
- `python -m unittest tests.test_local_http_core_smoke_suite`

### Notes

- Pure request construction remains side-effect-light and does not emit turn lifecycle events.
- This keeps the work on the regular core turn lifecycle path and does not expand extension behavior.
