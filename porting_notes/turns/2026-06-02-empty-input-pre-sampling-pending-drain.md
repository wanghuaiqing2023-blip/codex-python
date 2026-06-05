## Empty input pre-sampling pending drain

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> `can_drain_pending_input` -> turn loop pending input drain -> first `run_sampling_request`.
- Rust behavior confirmed from `codex/codex-rs/core/src/session/turn.rs`: when a turn starts without fresh input, `can_drain_pending_input` is true, so pending input is drained, inspected by hooks, and recorded before the first sampling request is constructed. When fresh input exists, pending input is deferred until after the first sampling request.

### Python change

- `pycodex/core/turn_runtime.py` now drains pending input before building the first sampling request when `run_user_turn_sampling_from_session` is invoked with empty input.
- Pre-sampling pending user input uses the existing UserPromptSubmit compatibility hook path.
- If the pre-sampling pending user input is blocked and no pending user input is accepted, the turn completes without calling the sampler.
- The pure request-builder path remains unchanged and does not drain pending input.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_empty_input_drains_pending_before_first_request tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_empty_input_pending_hook_blocks_first_request`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_blocks_followup`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_blocks_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_stream_bad_tool_search_arguments tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
- `python -m unittest tests.test_local_http_core_smoke_suite`

### Notes

- This keeps the implementation on the core turn loop path. The remaining Rust/Python structural difference is that Rust checks `has_pending_input` after sampling and drains on the next loop iteration, while Python still drains at the loop decision point to emulate follow-up behavior.
