# 2026-06-01 SSE Function Call Delta Boundary

## Graph-Guided Slice

- Continued the core `exec -> model stream -> tool dispatch -> final answer` path.
- Used the upstream graph to stay on high-fan-out `codex-rs/exec` and `codex-api` stream handling nodes, then confirmed behavior in:
  - `codex/codex-rs/codex-api/src/sse/responses.rs`
  - `codex/codex-rs/core/src/session/turn.rs`

## Upstream Behavior

- Rust emits `ResponseEvent::ToolCallInputDelta` for `response.custom_tool_call_input.delta`.
- Rust intentionally ignores `response.function_call_arguments.delta` in the SSE parser; the upstream test `parses_tool_call_input_deltas` confirms the ordinary function-call argument delta is not surfaced as a stream event.

## Python Work

- Added focused coverage in `tests/test_core_http_transport.py` proving the stdlib HTTP/SSE parser preserves the same boundary:
  - custom tool input deltas are emitted as `tool_call_input_delta`;
  - ordinary function-call argument deltas are ignored.

## Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_ignores_function_call_argument_deltas tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_records_rust_style_sse_stream_events`

## Deferred

- No deep MCP/plugin/marketplace work was added. The slice only protects the core streaming/tool-input event boundary.
