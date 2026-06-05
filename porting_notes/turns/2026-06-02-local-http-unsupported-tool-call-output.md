# Local HTTP unsupported tool-call output

## Source slice

- Used the upstream graph around the core tool dispatch path:
  - `codex-rs/core/src/tools/router.rs`
  - `codex-rs/core/src/tools/registry.rs`
- Confirmed Rust builds tool calls from `function_call` and `custom_tool_call` response items, then returns a model-visible `FunctionCallError::RespondToModel` when the registry has no matching tool.
- Rust messages:
  - Function payload: `unsupported call: <tool>`
  - Custom payload: `unsupported custom tool call: <tool>`

## Python changes

- `shell_tool_outputs_from_local_http_exec_result` no longer silently ignores unknown `function_call` / `custom_tool_call` items.
- Unknown function tools now produce a failed `function_call_output`.
- Unknown custom tools now produce a failed `custom_tool_call_output`.
- The local HTTP shell-tool loop can feed that error into the next model request, preserving the normal tool dispatch -> follow-up answer path.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_unknown_function_tool_returns_model_visible_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_unknown_custom_tool_returns_model_visible_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_follows_up_after_unknown_tool_error`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_stream_events_utils`

## Deferred

- This does not implement extension/MCP/custom tool handlers. It only keeps the core runtime from dropping an unexpected tool call on the floor.
