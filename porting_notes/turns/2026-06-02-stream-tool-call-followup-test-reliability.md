# Stream tool-call follow-up test reliability

## Source slice

- Graph entrypoint: `function:codex-rs/core/src/session/turn.rs#run_turn:133`.
- Graph-selected dependency: `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`.
- Rust source check: `codex-rs/core/src/stream_events_utils.rs::handle_output_item_done` sets `needs_follow_up = true` when a custom/function tool call is completed, and `codex-rs/core/src/session/turn.rs` carries that into the next sampling request.

## Python port

- `tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events` previously returned the same streamed custom tool call on every sampler invocation.
- Because Python now correctly follows up after streamed tool calls, that fixture could loop indefinitely instead of reaching a final assistant answer.
- The fixture now returns the streamed custom tool call on the first request and a final assistant message on the follow-up request, preserving the stream-event assertions while matching the Rust tool-call loop shape.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_retries_retryable_stream_error tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_falls_back_to_http_after_retry_limit tests.test_core_responses_retry`
- `python -m unittest tests.test_core_turn_runtime`
