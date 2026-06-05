# 2026-06-02 local HTTP local_shell_call timeline

## Upstream slice

- Used the graph-guided core replay path and confirmed the authoritative Rust behavior in:
  - `codex/codex-rs/protocol/src/models.rs`
  - `codex/codex-rs/core/src/context_manager/normalize.rs`
  - `codex/codex-rs/app-server-protocol/src/protocol/item_builders.rs`
- Rust treats `ResponseItem::LocalShellCall` as a core history item. Its output is represented by a matching `FunctionCallOutput`, and app-server command execution items display the shell argv with `shlex_join`.

## Python change

- Updated `pycodex/exec/local_runtime.py` so local HTTP timeline reconstruction treats `local_shell_call` as a `command_execution` item.
- Added local-shell action helpers to read `action.command` argv and `action.working_directory`, render the display command with standard-library `shlex.join`, and reuse the existing `command_actions_from_argv` path.
- Kept `tool_call_items_from_local_http_exec_result` from reporting `local_shell_call` as a generic MCP tool call by making local-shell inclusion timeline-only.

## Tests

- Added `test_local_http_tool_timeline_maps_local_shell_call_to_command_execution`.
- Existing rollout normalization coverage for missing local-shell outputs remains in place and was re-run.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_uses_response_item_calls_when_raw_payload_is_absent tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_uses_response_item_outputs_when_raw_payload_is_absent tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_maps_local_shell_call_to_command_execution`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_inserts_missing_output_for_local_shell_call tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_can_preload_resume_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_reconstructed_model_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds`

## Known gaps

- This only maps already-present `local_shell_call` history/response items into user-visible command execution events. It does not implement a new model-facing local-shell tool runtime.
- Output-less local-shell calls still need a recoverable output or synthetic output from normalization to render a completed item.
