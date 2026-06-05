# Sampling Retry Adapter

## Scope

- Continued the graph-guided core request path after prompt construction into sampling request execution.
- Focused on the retry/fallback policy around retryable response stream failures, keeping transport side effects injectable.

## Upstream Graph/Source Slice

- Graph nodes used:
  - `file:codex-rs/core/src/session/turn.rs`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `file:codex-rs/core/src/responses_retry.rs`
- Rust source confirmed:
  - `run_sampling_request` retries retryable stream errors up to the provider cap.
  - After the cap is reached, Rust can switch from WebSocket to HTTPS transport if fallback is available.
  - Retry handling reports a `RetryableResponseStreamDecision`-shaped policy: retry with delay, fallback transport, or fail.
  - Context-window and usage-limit errors remain special terminal paths outside the generic retry loop.

## Python Changes

- `pycodex/core/turn_sampler.py`
  - Added `sample_with_model_client_session_retries()` as a stdlib retry adapter around the existing one-shot sampler.
  - Kept existing `sample_with_model_client_session()` behavior unchanged.
  - Added injectable `sleep`, retry-decision callback, optional fallback transport, and WebSocket visibility flag so UI/transport side effects can be layered by callers.
- `tests/test_core_turn_sampler.py`
  - Added coverage for retryable `CodexErr` retries, fallback transport after capped retries, and non-retryable error propagation.

## Validation

- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_runtime`
  - 46 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 695 tests passed, 1 skipped.

## Follow-up Debt

- The stdlib HTTP transport still preserves its existing `RuntimeError` surface for HTTP/URL failures. A later slice can add explicit `CodexErr` mapping at the transport boundary so real HTTP failures participate in the retry adapter.
- Usage-limit and context-window terminal updates still need fuller session side effects when the Python sampler owns more of the response stream lifecycle.
