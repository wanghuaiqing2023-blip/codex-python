## Defer pending input behind model follow-up

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> sampling result -> `model_needs_follow_up` / `has_pending_input` -> `can_drain_pending_input`.
- Rust behavior confirmed from `codex/codex-rs/core/src/session/turn.rs`: after a sampling request, pending input can make the turn continue, but it is not drained ahead of a model/tool continuation. When model continuation is still required, pending input remains queued until the continuation has completed.

### Python change

- `pycodex/core/turn_runtime.py` now skips pending input drain while `needs_model_followup` is true or while ordinary tool outputs need a follow-up request.
- Pending input is still allowed to take over when a local `max_tool_followups` limit blocks further tool follow-up, preserving the Python guardrail behavior.
- This prevents a user steer submitted during a model continuation from being mixed into the immediate continuation request.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_defers_pending_input_behind_model_followup`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_follows_stream_completed_end_turn_false tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_follows_raw_response_completed_end_turn_false tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_model_followup_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_blocks_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_empty_input_drains_pending_before_first_request`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_stream_bad_tool_search_arguments tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_can_limit_tool_followups`
- `python -m unittest tests.test_local_http_core_smoke_suite`

### Notes

- This is still a lightweight Python loop approximation; Rust has an explicit `has_pending_input` check after sampling, while Python uses queued drain timing to preserve the same user-visible ordering on the core path.
