# Sampling websocket-to-HTTP fallback

## Source slice

- Graph entrypoint: `function:codex-rs/core/src/session/turn.rs#run_turn:133`.
- Graph-selected dependency: `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`.
- Rust source check: `codex-rs/core/src/session/turn.rs::run_sampling_request` retries retryable stream errors and delegates retry/fallback behavior to `handle_retryable_response_stream_error`.
- Rust source check: `codex-rs/core/src/responses_retry.rs::handle_retryable_response_stream_error` switches from WebSockets to HTTPS transport after the retry limit when `client_session.try_switch_fallback_transport(...)` succeeds, emits a warning, resets the retry counter, and continues the sampling loop.

## Python port

- `pycodex.core.turn_runtime._sample_with_retry` now exposes the same fallback branch instead of always passing `fallback_transport_available=False`.
- The Python runtime checks `sess.services.model_client.responses_websocket_enabled()`, calls `force_http_fallback(session_telemetry, model_info)` when the fallback decision is selected, emits the Rust-shaped warning, resets retries, and continues sampling.
- Added focused coverage for a retryable stream error that retries once, falls back from WebSockets to HTTPS after the retry limit, and succeeds on the next sampling attempt.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_retries_retryable_stream_error tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_falls_back_to_http_after_retry_limit`
- `python -m unittest tests.test_core_responses_retry`
- `python -m unittest tests.test_core_turn_runtime`

## Follow-up

- The earlier full-suite hang was traced to `test_run_user_turn_sampling_projects_sampler_stream_events` returning the same streaming tool call on every sampler invocation. That test now returns a final assistant message on the follow-up request, matching Rust's `needs_follow_up` behavior after tool calls.
