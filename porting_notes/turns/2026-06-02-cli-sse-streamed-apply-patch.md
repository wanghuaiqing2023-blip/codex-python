# 2026-06-02 - CLI SSE streamed apply_patch execution

## Upstream slice

- Used the graph-guided core custom-tool path:
  - `codex-rs/core/tests/common/responses.rs`
  - `codex-rs/core/tests/suite/shell_serialization.rs`
  - `codex-rs/core/tests/suite/tool_harness.rs`
- Confirmed Rust represents direct `apply_patch` as a Responses `custom_tool_call` with raw patch text in `input`, and returns a `custom_tool_call_output` in the follow-up request.

## Python progress

- Added transport coverage for streamed custom tool input:
  - `response.output_item.added` seeds a `custom_tool_call`;
  - `response.custom_tool_call_input.delta` frames append to `input`;
  - when `response.completed` has no output array, the accumulated item is used as the response output.
- Added a CLI-level local HTTP shell-tools smoke proving streamed `apply_patch` works end to end:
  - first model response is SSE and streams the patch through `custom_tool_call_input.delta`;
  - local helper applies the patch in the requested working directory;
  - follow-up request includes a successful `custom_tool_call_output`;
  - final assistant response is rendered to stdout.

## Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_accumulates_custom_tool_input_deltas tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_streamed_apply_patch_runs_tool_and_followup`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_streamed_exec_command_runs_tool_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_streamed_apply_patch_runs_tool_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_apply_patch_smoke_writes_file_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_exec_command_apply_patch_heredoc_smoke tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_accumulates_function_call_argument_deltas tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_accumulates_custom_tool_input_deltas tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_records_rust_style_sse_stream_events`
- `python -m py_compile tests\test_core_http_transport.py tests\test_cli_parser.py`

## Follow-up debt

- Add streamed `apply_patch` approval-denial coverage if approval behavior changes on the shell-tool loop.
- Continue prioritizing CLI/core runtime slices before deeper app-server or plugin parity.
