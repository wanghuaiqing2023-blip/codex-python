# Exec Resume Shell Tools Output Schema CLI Coverage

Date: 2026-06-02

## Scope

Continued the graph-guided `codex exec` core path, this time on the resume branch:

- `codex-rs/exec/src/lib.rs::run_exec_session`
- `codex-rs/exec/src/lib.rs::load_output_schema`
- Python local HTTP resume runner and shell-tool loop handoff

This remains in the common CLI/runtime path and avoids MCP, plugin, marketplace, cloud, and daemon work.

## Behavior

Rust keeps `--output-schema` on the user-turn `InitialOperation`, including resumed turns. The Python resume path already passes the prepared `ExecRunPlan` into `run_exec_resume_user_turn_http_sampling`, and that runner can route through `run_exec_user_turn_with_shell_tools_http_sampling`.

## Python Change

Added CLI-level coverage proving that:

- `codex exec resume --last --output-schema <file> ...`
- with `PYCODEX_EXEC_LOCAL_HTTP=1`
- and `PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS=1`

preserves the parsed schema on `plan.initial_operation.output_schema` while routing through the resume shell-tool loop.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_passes_output_schema tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_passes_tool_loop_options tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_last_uses_resume_runner`
- `python -m unittest tests.test_exec_run tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_passes_output_schema_to_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_passes_output_schema tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer`
- `python -m py_compile tests\test_cli_parser.py`

## Known Gaps

This strengthens the CLI contract for the local HTTP resume path. It is not a substitute for later live end-to-end validation against a real model stream.
