# 2026-06-02 - CLI SSE streamed tool-call execution

## Upstream slice

- Used the graph-guided core streaming/tool path:
  - `codex-rs/core/tests/common/responses.rs`
  - `codex-rs/core/tests/suite/unified_exec.rs`
  - `codex-rs/core/src/tools/handlers/unified_exec.rs`
- Confirmed Rust tests model function tools as Responses `response.output_item.*` events, with `exec_command` on the common unified exec path.

## Python progress

- Extended the stdlib Responses SSE parser to preserve streamed tool-call arguments:
  - `response.output_item.added` now seeds active `function_call` and `custom_tool_call` items.
  - `response.function_call_arguments.delta` appends to active `function_call.arguments`.
  - `response.custom_tool_call_input.delta` appends to active `custom_tool_call.input`.
  - `response.output_item.done` replaces the active streamed tool item when it matches by id or call id.
- Added CLI-level coverage proving the real `codex exec` local HTTP shell-tool loop can:
  - receive a streamed `exec_command` built from argument delta frames;
  - execute the command locally;
  - send the `function_call_output` back in the follow-up request;
  - render the final assistant answer.

## Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_accumulates_function_call_argument_deltas tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_streamed_exec_command_runs_tool_and_followup`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_smoke_outputs_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_streamed_exec_command_runs_tool_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_write_stdin_smoke_continues_session_and_followup tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_accumulates_function_call_argument_deltas tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_records_rust_style_sse_stream_events`
- `python -m py_compile pycodex\core\http_transport.py tests\test_core_http_transport.py tests\test_cli_parser.py`

## Follow-up debt

- Add a streamed custom `apply_patch` CLI smoke after the streamed function-call path remains stable.
- Keep websocket/app-server streaming out of the active implementation target unless the CLI/core runtime depends on it.
