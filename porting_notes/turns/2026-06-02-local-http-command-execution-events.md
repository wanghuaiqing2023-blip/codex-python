# Local HTTP Command Execution Events

## Scope

- Continued the core `exec -> tool dispatch -> user-visible events -> final answer` slice.
- Local HTTP shell calls now render as command execution timeline items when the corresponding call and output can be paired.

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/core/src/tools/events.rs#emit_exec_command_begin`
  - `class:codex-rs/core/src/tools/events.rs#ToolEmitter`
  - `function:codex-rs/core/src/tools/events.rs#emit_exec_stage`
  - `function:codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#handle`
- Rust source read:
  - `codex/codex-rs/core/src/tools/events.rs`
  - `codex/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs`
  - `codex/codex-rs/app-server-protocol/src/protocol/item_builders.rs`
  - `codex/codex-rs/app-server-protocol/src/protocol/thread_history.rs`

## Rust behavior confirmed

- `ToolEmitter::UnifiedExec` emits `ExecCommandBegin` at tool start.
- On success or output failure, Rust emits `ExecCommandEnd` with aggregated output, exit code, and `completed` or `failed` status based on exit code.
- Rejected command execution is represented as a declined command execution item.
- App-server thread history maps exec begin/end events to `CommandExecution` items rather than MCP tool items.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Added command-execution timeline helpers for local HTTP shell-family tools.
  - Paired shell calls and outputs now emit `command_execution` items with stable call IDs, command text, aggregated output, exit code, and status.
  - Approval-required or forbidden shell outputs now surface as `declined` command execution items.
  - Output-only tool results still fall back to `mcp_tool_call` because there is no call payload from which to recover the command.
- `tests/test_exec_local_runtime.py`
  - Updated local HTTP JSON event coverage to expect `command_execution` for paired shell calls.
  - Added approval-required timeline coverage for declined shell command execution.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_requires_approval_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_maps_function_call_json_event_without_execution`
- `python -m unittest tests.test_exec_local_runtime`

## Known gaps

- The local HTTP output-only fallback remains an MCP-shaped item because the raw Responses payload lacks the original shell command. A future session-level event replay path could avoid that fallback when command metadata is available elsewhere.
