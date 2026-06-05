# 2026-06-02 local HTTP response-item tool-call timeline

## Upstream slice

- Used `codex/.understand-anything/knowledge-graph.json` to narrow this turn back to the core tool-event path instead of peripheral MCP/plugin work.
- Relevant upstream areas are the app-server protocol event mapping and TUI replay/command lifecycle paths, where command tool calls replay as `CommandExecution` items rather than generic MCP cells when command metadata is available.

## Python change

- Updated `pycodex/exec/local_runtime.py` so local HTTP tool call extraction and timeline reconstruction also read tool calls from `UserTurnSamplingResult.response_items`.
- The normal raw HTTP payload path remains the preferred source. Response-item calls are appended only when their `call_id`/`id` is not already present, which keeps live local HTTP output stable while improving resume/rollout-shaped results.
- Added a regression test covering a history-shaped result with no raw HTTP payload, a `ResponseItem.function_call("exec_command", ...)`, and raw tool output. The timeline now reconstructs the pair as `command_execution` in-progress/completed items.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_uses_response_item_calls_when_raw_payload_is_absent tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_can_preload_resume_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_reconstructed_model_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_groups_same_turn_tool_outputs tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch`

## Known gaps

- Output-only results with no recoverable call metadata still fall back to generic tool output rendering; there is no command text to reconstruct without a call item.
- MCP/plugin/marketplace behavior remains intentionally deferred unless the core runtime needs a compatibility shim.
