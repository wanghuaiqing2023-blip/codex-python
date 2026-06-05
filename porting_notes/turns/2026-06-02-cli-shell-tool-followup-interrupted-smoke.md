# CLI shell-tool follow-up interrupted smoke

## Upstream slice

- Continued the core `exec -> shell tool call -> tool output follow-up -> interrupted turn -> CLI/rollout` path.
- Rust behavior treats an interrupted follow-up as an interrupted turn: partial assistant output is not rendered as a final answer, while completed tool artifacts remain part of conversation history.

## Python slice

- Added a CLI-level local HTTP smoke where the first model response requests `exec_command`, the command is executed through the real shell-tool path, and the tool-output follow-up returns `UserTurnSamplingResult(turn_status="interrupted")`.
- Verifies stdout stays empty, stderr reports `turn interrupted`, and the partial follow-up assistant text is not rendered.
- Verifies rollout preserves the prompt-visible function call and function-call output, then appends the `<turn_aborted>` marker and `turn_aborted` event.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tool_followup_interrupted_persists_tool_and_marker tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_merge_preserves_followup_interrupted_status tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_interrupted_prints_human_without_partial_and_persists_marker`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tool_followup_interrupted_persists_tool_and_marker tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_exec_command_apply_patch_heredoc_smoke tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up

- Start consolidating the core local HTTP CLI smoke suite into a documented regression subset, now that normal, provider-error, interrupted, resume, and shell-tool interrupted paths have focused coverage.
