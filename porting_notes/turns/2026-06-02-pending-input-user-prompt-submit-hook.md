## Pending input UserPromptSubmit hook

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> turn loop pending input drain -> `run_hooks_and_record_inputs` -> `hook_runtime::inspect_pending_input` / `record_pending_input`.
- Rust behavior confirmed from `codex/codex-rs/core/src/session/turn.rs` and `codex/codex-rs/core/src/hook_runtime.rs`: pending `TurnInput::UserInput` is inspected by the UserPromptSubmit hook before recording. A blocking pending input records only additional context and stops the current turn when no user input was accepted; a continuing pending input records user input and then hook additional context. Pending `TurnInput::ResponseItem` bypasses UserPromptSubmit and is recorded directly.

### Python change

- `pycodex/core/turn_runtime.py` now drains pending input through a small TurnInput-shaped normalization layer instead of converting everything to response items up front.
- Pending user inputs run the same lightweight UserPromptSubmit compatibility hook used for initial input.
- Pending response items continue to be recorded directly.
- The main turn loop now stops before building a follow-up request when pending user input is blocked and no pending user input was accepted, matching the Rust `blocked_input && !accepted_user_input` rule.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_blocks_followup`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_blocks_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_records_context_after_input`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_stream_bad_tool_search_arguments tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_mailbox_preemption_follows_up_after_commentary`
- `python -m unittest tests.test_local_http_core_smoke_suite`

### Notes

- This keeps the work on the common turn/runtime path and does not expand plugin, marketplace, MCP, cloud, or daemon behavior.
