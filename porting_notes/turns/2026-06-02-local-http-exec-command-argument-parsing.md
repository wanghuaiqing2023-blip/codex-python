# Local HTTP exec_command argument parsing

## Upstream graph and source slice

- Graph node: `class:codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#ExecCommandHandler`
- Graph node: `class:codex-rs/core/src/tools/handlers/unified_exec.rs#ExecCommandArgs`
- Graph node: `class:codex-rs/protocol/src/models.rs#ShellCommandToolCallParams`
- Source: `codex/codex-rs/core/src/tools/handlers/unified_exec.rs`
- Source: `codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
- Source: `codex/codex-rs/protocol/src/models.rs`

Rust's unified `exec_command` handler parses function arguments as
`ExecCommandArgs`, where the command field is `cmd: String`. The legacy
`shell_command` path uses `ShellCommandToolCallParams`, where the command field
is `command: String`. That means `exec_command` should not execute a payload
that only supplies the legacy `command` field.

## Python changes

- Added `exec_command`-specific argument validation to the local HTTP tool
  output path before shell execution.
- Kept legacy `shell` / `shell_command` compatibility separate so existing
  `command`-based shell calls continue to work.
- Added regression coverage proving malformed `exec_command` arguments return
  `failed to parse function arguments: ...` and never reach the shell runner.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_tool_call_uses_cmd_argument tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_rejects_command_alias_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_rejects_invalid_yield_time_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_accepts_cwd_alias tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_reports_missing_command_argument`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_tool_events tests.test_core_apply_patch tests.test_core_spec_plan`
