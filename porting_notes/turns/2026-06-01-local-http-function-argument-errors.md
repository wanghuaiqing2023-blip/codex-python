# Local HTTP Function Argument Errors

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:1698`
  - `function:codex-rs/core/src/tools/router.rs#build_tool_call:96`
  - `function:codex-rs/core/src/tools/handlers/mod.rs#parse_arguments`
  - `function:codex-rs/core/src/tools/handlers/shell.rs#shell_command_payload_command`
- Rust source read:
  - `codex/codex-rs/core/src/stream_events_utils.rs`
  - `codex/codex-rs/core/src/tools/router.rs`
  - `codex/codex-rs/core/src/tools/handlers/mod.rs`
  - `codex/codex-rs/core/src/tools/handlers/shell.rs`

## Rust behavior confirmed

- Function tool calls keep raw JSON argument text in `ToolPayload::Function`.
- Core handlers parse that text through `handlers::parse_arguments`.
- JSON parse failures become `FunctionCallError::RespondToModel("failed to parse function arguments: ...")`.
- The turn loop records that response as tool output and follows up with the model instead of executing the tool.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Added a pre-dispatch function-call argument gate for local HTTP function tools.
  - Invalid JSON, missing arguments, or non-object JSON arguments now produce a model-visible `failed to parse function arguments: ...` output.
  - Missing shell command fields now produce a failed tool output instead of silently dropping the tool call.
  - The local runner is not invoked when function-call arguments are invalid.

- `tests/test_exec_local_runtime.py`
  - Added coverage that invalid shell JSON arguments are rejected before execution.
  - Added coverage that shell calls with `{}` return a failed tool output explaining the missing command.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_invalid_json_arguments_before_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_reports_missing_command_argument tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_tool_call_uses_cmd_argument`
- `python -m unittest tests.test_exec_local_runtime`

## Follow-up debt

- Error wording is intentionally Rust-shaped by prefix and user-visible behavior, but not byte-for-byte identical to serde's full type diagnostics for every malformed payload.
