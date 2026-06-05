# 2026-06-02 - CLI SSE response smoke coverage

## Upstream slice

- Used the graph-guided streaming/request path:
  - `codex-rs/core/tests/common/streaming_sse.rs`
  - `codex-rs/core/tests/suite/cli_stream.rs`
  - the core Responses streaming path that expects `response.output_item.*` and `response.completed` events.
- Confirmed from the Rust test helper that core tests exercise streaming SSE delivery through `/v1/responses`, not only JSON response bodies.

## Python progress

- Added a CLI-level local HTTP smoke test for SSE Responses output.
- The test drives the real `main(["exec", ...])` path with:
  - `PYCODEX_EXEC_LOCAL_HTTP=1`;
  - shell tools disabled so this isolates the base model response path;
  - a fake `urlopen` response returning `response.output_item.done`, `response.completed`, and `[DONE]` SSE frames.
- The smoke verifies:
  - the CLI posts to `/v1/responses`;
  - the prepared request contains `stream: true`;
  - the CLI renders the final assistant output from the SSE stream.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_smoke_outputs_final_message`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_posts_expected_request tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_sse_smoke_outputs_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_parses_responses_sse_stream tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_accumulates_sse_output_text_delta tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_records_rust_style_sse_stream_events`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up debt

- Extend CLI-level SSE coverage to a tool-call stream once the current shell-tool smoke tests are stabilized around streamed `function_call`/custom tool deltas.
- Keep app-server/websocket streaming out of scope until the common CLI/core runtime requires it.
