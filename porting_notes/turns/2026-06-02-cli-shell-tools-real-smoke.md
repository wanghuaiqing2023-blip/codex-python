# CLI local HTTP shell tools smoke

## Graph-guided slice

- Upstream graph entrypoint: `codex-rs/exec/src/lib.rs#run_exec_session`.
- Tool execution nodes: `codex-rs/core/src/tools/handlers/shell.rs#run_exec_like`,
  `codex-rs/core/src/tools/handlers/shell_spec.rs#create_exec_command_tool`,
  and `codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`.
- Python target slice: `pycodex.cli.parser` dispatches `codex exec` into the
  local HTTP runtime; `pycodex.exec.local_runtime` turns Responses
  `exec_command` calls into local command execution and feeds
  `function_call_output` items into the follow-up model request.

## Progress

- Added a CLI-level smoke test that runs `main(["exec", ...])` with local HTTP
  shell tools enabled.
- The fake Responses endpoint first returns an `exec_command` tool call, then a
  final assistant message.
- The test lets the Python runtime execute a real safe subprocess command and
  asserts that its output is included in the follow-up Responses request.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_posts_expected_request tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_default_tool_rounds_are_unbounded tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_passes_output_schema_to_tool_loop`
- `python -m py_compile tests\test_cli_parser.py`

## Deferred

- Broader approval/sandbox parity for command execution.
- Streaming/event parity around shell output begin/delta/end events.
- Full interactive CLI smoke coverage with real model credentials.
