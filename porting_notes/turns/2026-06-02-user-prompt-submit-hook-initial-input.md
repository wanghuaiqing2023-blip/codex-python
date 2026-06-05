## User prompt submit hook for initial input

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> `run_hooks_and_record_inputs` -> `hook_runtime::inspect_pending_input`.
- Rust behavior confirmed from `codex/codex-rs/core/src/session/turn.rs` and `codex/codex-rs/core/src/hook_runtime.rs`: `TurnInput::UserInput` is inspected by the UserPromptSubmit hook before it is recorded. A blocking hook records only additional context and stops the turn; a continuing hook records the user input and then records any additional context.

### Python change

- `pycodex/core/turn_runtime.py` now runs a lightweight UserPromptSubmit compatibility hook for the sampling path before initial user input is recorded.
- Supported session/turn-context hook names include `run_user_prompt_submit_hook`, `run_user_prompt_submit`, and `user_prompt_submit_hook`.
- Hook outcomes are normalized to `HookRuntimeOutcome`; mappings, bools, objects, and `None` are accepted for lightweight compatibility.
- The pure request-builder path remains unchanged and does not run hooks.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_blocks_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_records_context_after_input`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_turn_lifecycle_events tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_returns_streamed_last_agent_message`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_stream_bad_tool_search_arguments tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_mailbox_preemption_follows_up_after_commentary`

### Notes

- `pytest` is not installed in the current shell or bundled Python, so this turn used stdlib `unittest` for targeted validation.
- A full `python -m unittest tests.test_core_turn_runtime` run was attempted, but it stalled in the pre-existing long-running `test_run_user_turn_sampling_projects_sampler_stream_events` path and was stopped after targeted coverage had passed.
