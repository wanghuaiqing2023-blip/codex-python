# MCP ResponseInput Conversion

## Source slice

- Graph query pointed to the response/tool-call boundary around `ToolRouter::build_tool_call` and `response_input_to_response_item`.
- Authoritative Rust behavior confirmed in:
  - `codex/codex-rs/core/src/tools/router.rs`
  - `codex/codex-rs/core/src/stream_events_utils.rs`
  - `codex/codex-rs/core/src/tools/context.rs`

## Confirmed Rust behavior

- `ToolRouter::build_tool_call` only executes function calls, client-side tool search calls with a call id, and custom tool calls.
- `response_input_to_response_item` maps `ResponseInputItem::McpToolCallOutput` to a `ResponseItem::FunctionCallOutput`.
- The MCP result is first converted through `as_function_call_output_payload()`, rather than storing the raw MCP result object as the model-facing function output.

## Python change

- Added `call_tool_result_to_function_payload` in `pycodex/core/tool_context.py` as a public lightweight wrapper around the existing MCP result-to-function-payload conversion.
- Updated `pycodex/core/stream_events_utils.py` so `mcp_tool_call_output` is converted to a `function_call_output` with a proper `FunctionCallOutputPayload`.
- Added focused coverage for structured MCP output and MCP error success flags.

## Validation

- `python -m py_compile pycodex/core/tool_context.py pycodex/core/stream_events_utils.py tests/test_core_stream_events_utils.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_stream_events_utils.py tests/test_core_tool_context.py -q`
  - `147 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_turn_runtime.py tests/test_core_client.py -q`
  - `199 passed, 1 warning`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_router.py tests/test_core_tool_parallel.py -q`
  - `187 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`

## Deferred

- MCP runtime and external server integration remain out of active scope. This is a small compatibility shim on the shared response conversion path because core tool result replay can encounter MCP-shaped output items.
