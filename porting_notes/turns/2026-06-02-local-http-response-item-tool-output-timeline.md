# 2026-06-02 local HTTP response-item tool-output timeline

## Upstream slice

- Continued the graph-selected core tool replay path: command/tool calls should reappear as user-visible command execution timeline items when enough call/output metadata is available.
- This stays on the common `exec -> tool dispatch -> rollout/resume -> event rendering` path and does not expand MCP/plugin/marketplace behavior.

## Python change

- Updated `pycodex/exec/local_runtime.py` so local HTTP tool output extraction and timeline reconstruction can recover tool outputs from `UserTurnSamplingResult.response_items` when no raw HTTP payload, raw tool outputs, or separate `tool_response_items` are available.
- This matches rollout/history-shaped data returned by `read_response_items_from_rollout`/`read_model_history_from_rollout`, where model-visible history is reconstructed as `ResponseItem` values.
- The fallback is intentionally conservative: live raw payloads and explicit tool response collections remain higher priority.

## Tests

- Added `test_local_http_tool_timeline_uses_response_item_outputs_when_raw_payload_is_absent`.
- Kept the earlier response-item call test in place so the pair now covers both halves of history-shaped command execution replay.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_uses_response_item_calls_when_raw_payload_is_absent tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_uses_response_item_outputs_when_raw_payload_is_absent`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_can_preload_resume_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_reconstructed_model_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_groups_same_turn_tool_outputs tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds`

## Known gaps

- If a persisted output has no matching recoverable call metadata, it still cannot be rendered as command execution because the command text is missing.
- Full app-server/TUI parity remains outside the active core slice.
