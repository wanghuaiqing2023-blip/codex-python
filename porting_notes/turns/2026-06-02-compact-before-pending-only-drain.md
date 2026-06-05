## Compact before pending-only drain

### Upstream slice

- Graph-guided core path: `session/turn.rs` -> post-sampling `has_pending_input` -> `token_limit_reached && needs_follow_up` -> mid-turn `run_auto_compact` -> `can_drain_pending_input`.
- Rust behavior confirmed from `codex/codex-rs/core/src/session/turn.rs`: pending input can cause `needs_follow_up`, but token-limit auto-compact runs before pending input is drained into history. After compaction succeeds, `can_drain_pending_input` is set from `!model_needs_follow_up`, so pending-only follow-up drains on the next loop iteration.

### Python change

- `pycodex/core/turn_runtime.py` now checks pending-only follow-up for mid-turn auto-compact before draining queued pending input.
- `_run_auto_compact_if_needed` now reports whether compaction actually ran, while preserving the existing success/failure behavior for callers.
- Pending input is drained immediately only when compaction is not needed; when compaction runs, the loop continues and drains pending input afterward.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_compacts_before_draining_pending_only_followup`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_runs_mid_turn_auto_compact_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_mid_turn_auto_compact_usage_limit_completes_without_error_event`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_empty_input_drains_pending_before_first_request tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_defers_pending_input_behind_model_followup`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_user_prompt_submit_hook_blocks_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_records_context_after_input tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_hook_blocks_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_stream_bad_tool_search_arguments tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_can_limit_tool_followups`
- `python -m unittest tests.test_local_http_core_smoke_suite`

### Notes

- This keeps the work on the common turn loop and compaction path. No MCP, plugin, marketplace, cloud, or daemon behavior was expanded.
