## User prompt turn item events

### Upstream slice

- Graph-guided core path: `hook_runtime::record_pending_input` -> `Session::record_user_prompt_and_emit_turn_item`.
- Rust behavior confirmed from `codex/codex-rs/core/src/hook_runtime.rs` and `codex/codex-rs/core/src/session/mod.rs`: user input is persisted as a `ResponseItem`, then emitted from the original `UserInput` as a `TurnItem::UserMessage` via `ItemStarted` and `ItemCompleted`. Emitting from `UserInput` preserves UI-only fields such as text elements that are not carried by the persisted response item.

### Python change

- `InMemoryCodexSession` now exposes `record_user_prompt_and_emit_turn_item`, `emit_turn_item_started`, and `emit_turn_item_completed`.
- `turn_runtime.py` now prefers `record_user_prompt_and_emit_turn_item` when recording initial or pending user input, while retaining the old `record_conversation_items` fallback for lightweight session test doubles.
- User prompt events use existing protocol `TurnItem.user_message`, `ItemStartedEvent`, and `ItemCompletedEvent` shapes; no new dependency was added.

### Validation

- `python -m py_compile pycodex\core\session_runtime.py pycodex\core\turn_runtime.py`
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_record_user_prompt_emits_turn_item_events`
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_emits_turn_lifecycle_events tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_record_user_prompt_emits_turn_item_events tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_http_sampling_uses_pending_input_followup`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_empty_input_drains_pending_before_first_request`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_compacts_before_draining_pending_only_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_defers_pending_input_behind_model_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
- `python -m unittest tests.test_local_http_core_smoke_suite`

### Notes

- Python still emits these user item events during request preparation, before the current Python task-start lifecycle event. The event payloads now match Rust's user prompt item shape; lifecycle ordering can be aligned in a later turn if needed.
