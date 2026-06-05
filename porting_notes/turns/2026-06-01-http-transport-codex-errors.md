# HTTP Transport Codex Errors

## Scope

- Continued the graph-guided sampling path from request preparation into the stdlib HTTP transport boundary.
- Focused on making real HTTP transport failures participate in the Rust-shaped retry/error policy.

## Upstream Graph/Source Slice

- Graph nodes used:
  - `file:codex-rs/core/src/client.rs`
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
  - `file:codex-rs/core/src/responses_retry.rs`
  - `function:codex-rs/core/src/responses_retry.rs#handle_retryable_response_stream_error:22`
  - `class:codex-rs/protocol/src/error.rs#UnexpectedResponseError:305`
  - `class:codex-rs/protocol/src/error.rs#ConnectionFailedError:274`
  - `class:codex-rs/protocol/src/error.rs#ResponseStreamFailed:285`
- Rust source confirmed:
  - `UnexpectedStatus`, `ConnectionFailed`, and `ResponseStreamFailed` are retryable `CodexErr` variants.
  - The sampling loop delegates retry/fallback policy to `handle_retryable_response_stream_error`.
  - Non-retry terminal cases remain outside this generic transport retry path.

## Python Changes

- `pycodex/core/http_transport.py`
  - Mapped `HTTPError` to `CodexErr.unexpected_status(UnexpectedResponseError(...))`.
  - Mapped `URLError` to `CodexErr.connection_failed(ConnectionFailedError(...))`.
  - Mapped response read/decode failures to `CodexErr.response_stream_failed(ResponseStreamFailed(...))`.
  - Added optional retry support to `model_client_http_sampler()` using the existing `sample_with_model_client_session_retries()` adapter.
  - Added optional retry controls to `run_user_turn_http_sampling_from_session()` without changing the default single-attempt behavior.
- `tests/test_core_http_transport.py`
  - Added transport error mapping tests and a retrying HTTP sampler test.
- `tests/test_exec_local_runtime.py`
  - Updated the local HTTP error boundary to assert the new `CodexErr` surface while preserving the server error body in the message.

## Validation

- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_protocol_error`
  - 31 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_protocol_error tests.test_exec_local_runtime`
  - 116 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 698 tests passed, 1 skipped.

## Follow-up Debt

- Richer UI/event transport still needs broader parity beyond the in-memory token-count event record.

## 2026-06-01 Terminal API Error Payloads

### Scope

- Continued the same graph-guided HTTP sampling slice into terminal API error payloads.
- Focused on user-visible Rust parity for non-retryable errors before expanding session side effects.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `file:codex-rs/core/src/session/turn.rs`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `class:codex-rs/protocol/src/error.rs#UsageLimitReachedError:450`
  - `class:codex-rs/protocol/src/error.rs#UnexpectedResponseError:305`
- Rust source confirmed:
  - `codex-rs/codex-api/src/api_bridge.rs#map_api_error` maps transport HTTP 400 to `InvalidRequest`, 429 usage payloads to `UsageLimitReached`, non-usage 429 to `RetryLimit`, 500 to `InternalServerError`, and selected 503 bodies to `ServerOverloaded`.
  - `codex-rs/codex-api/src/rate_limits.rs` parses `x-codex-active-limit`, per-limit rate-limit headers, promo messages, credits, and `x-codex-rate-limit-reached-type`.
  - `codex-rs/codex-api/src/sse/responses.rs` maps `context_length_exceeded` response failures to `ApiError::ContextWindowExceeded`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Added Rust-shaped HTTP status/body mapping for invalid requests, internal server errors, overloaded server bodies, usage-limit 429s, usage-not-included 429s, and retry-limit 429s.
  - Added standard-library parsing for the Codex rate-limit header family into `RateLimitSnapshot`.
  - Added 200-response payload failure mapping for `context_length_exceeded`, quota, usage-not-included, cyber-policy, invalid-prompt, and overloaded errors.
- `tests/test_core_http_transport.py`
  - Added coverage for retry-limit 429s, usage-limit 429s with header metadata, context-window response failures, and 400 invalid requests.
- `tests/test_exec_local_runtime.py`
  - Updated local HTTP runtime expectations so HTTP 400 now surfaces as `CodexErr.invalid_request`, matching Rust `map_api_error`.

### Validation

- `python -m unittest tests.test_core_http_transport tests.test_exec_local_runtime`
  - 99 tests passed.

## 2026-06-01 Terminal Error Session Side Effects

### Scope

- Continued from HTTP terminal error mapping into the session-level effects that Rust applies when those errors escape sampling.
- Kept the slice on the common user-turn runtime path, not on TUI/app-server rendering.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/mod.rs#update_rate_limits:2988`
  - `function:codex-rs/core/src/session/mod.rs#set_total_tokens_full:3031`
  - `function:codex-rs/core/src/state/session.rs#set_token_usage_full:167`
  - `function:codex-rs/core/src/state/session.rs#token_info_and_rate_limits:161`
- Rust source confirmed:
  - `ContextWindowExceeded` calls `sess.set_total_tokens_full(&turn_context).await`, then returns the same error.
  - `UsageLimitReached(e)` clones `e.rate_limits`, updates the session's stored rate limits when present, emits token-count, then returns the same error.
  - `set_total_tokens_full` fills token usage to `turn_context.model_context_window()` and emits a `TokenCountEvent`.
  - `set_rate_limits` preserves prior credits and plan type when a new snapshot omits them, and defaults missing `limit_id` to `codex`.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Catches terminal `CodexErr` from initial and follow-up sampler calls.
  - Calls `session.set_total_tokens_full(turn_context)` for `context_window_exceeded`.
  - Calls `session.update_rate_limits(turn_context, rate_limits)` for `usage_limit_reached` when the error carries a snapshot.
  - Re-raises the original `CodexErr` so user-facing error behavior is unchanged.
- `pycodex/core/session_runtime.py`
  - Added in-memory `token_usage_info`, `latest_rate_limits`, and `emitted_events`.
  - Implemented `send_token_count_event`, `set_total_tokens_full`, `record_rate_limits_info`, and `update_rate_limits`.
  - Added Rust-shaped rate-limit field merging and effective context-window calculation.
- Tests:
  - `tests/test_core_turn_runtime.py` covers turn-runtime terminal error side effects.
  - `tests/test_core_session_runtime.py` covers in-memory token-count emission and rate-limit merging.

### Validation

- `python -m unittest tests.test_core_session_runtime tests.test_core_turn_runtime`
  - 90 tests passed.
- `python -m unittest tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime tests.test_core_responses_retry tests.test_core_turn_sampler`
  - 202 tests passed.

## 2026-06-01 Local Exec Token Usage Event Bridge

### Scope

- Continued the session token-count work into the `codex exec`-style local HTTP output path.
- Focused on the common non-interactive exec surface, not app-server or TUI rendering.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `class:codex-rs/protocol/src/protocol.rs#TokenCountEvent:1996`
  - `function:codex-rs/core/src/session/mod.rs#send_token_count_event:3022`
  - `function:codex-rs/exec/src/event_processor_with_jsonl_output.rs#usage_from_last_total:117`
- Rust source confirmed:
  - Exec processors cache `ThreadTokenUsageUpdated` notifications.
  - JSON turn completion emits usage from the latest cached total token usage.
  - Human output prints the cached blended total at shutdown.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added `session_events` to `UserTurnSamplingResult`.
  - Extracts Responses `usage` / `token_usage` / `tokenUsage` payloads after sampler success.
  - Records token usage into the session and asks the session to emit token-count events.
- `pycodex/core/session_runtime.py`
  - Added `record_token_usage_info()` using `TokenUsageInfo.new_or_append()`.
- `pycodex/exec/local_runtime.py`
  - Replays local in-memory `token_count` events through the existing exec processors.
  - Falls back to session token-count usage when raw Responses payload usage is absent.
  - Preserves session events when merging shell-tool follow-up results.
- Tests:
  - `tests/test_exec_local_runtime.py` verifies both real local HTTP usage recording and the event fallback path.

### Validation

- `python -m unittest tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_exec_local_runtime`
  - 176 tests passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_maps_usage tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_uses_session_token_count_event_when_raw_usage_missing`
  - 2 tests passed.

## 2026-06-01 Local Exec Terminal Error Event Bridge

### Scope

- Continued the local HTTP exec surface from successful token usage into failed terminal errors.
- Focused on preserving session token-count events attached to `CodexErr` before rendering the exec failure event.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `class:codex-rs/exec/src/exec_events.rs#TurnFailedEvent:55`
  - `file:codex-rs/exec/src/event_processor_with_jsonl_output.rs`
  - `file:codex-rs/exec/src/event_processor_with_human_output.rs`
- Rust source confirmed:
  - JSON exec processing records `ThreadTokenUsageUpdated` notifications before turn completion/failure.
  - Failed turns clear final-message state and emit `turn.failed` with the turn error, falling back to the last critical error or `turn failed`.
  - Human output prints `ERROR: ...` for failed turns and does not render a final assistant message.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Attaches in-memory session events to `CodexErr` raised by local HTTP user-turn and tool-output sampling.
  - Lets `emit_local_http_exec_error()` accept an exception object, replay attached session events, and emit the normal failed turn event.
  - Preserves existing string-error rendering.
- `tests/test_exec_local_runtime.py`
  - Added coverage for replaying attached session token-count events through the JSON error renderer.
  - Added coverage that context-window terminal errors carry session token-count events from the local HTTP runtime.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_error_replays_attached_session_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_context_window_error_attaches_session_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_runtime_uses_env_provider_and_model`
  - 3 tests passed.

## 2026-06-01 Tool Fatal Error Boundary

### Scope

- Continued the graph-selected `run_sampling_request -> try_run_sampling_request -> tool dispatch` slice.
- Focused on the user-visible tool failure boundary in the common agent loop, where fatal tool errors should fail the turn as `CodexErr::Fatal` instead of leaking a Python runtime exception.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
  - `file:codex-rs/core/src/tools/parallel.rs`
- Rust source confirmed:
  - `try_run_sampling_request` handles completed model output items, queues tool calls, drains in-flight tool futures, and records tool responses for follow-up sampling.
  - `ToolCallRuntime::handle_tool_call` maps `FunctionCallError::Fatal(message)` to `CodexErr::Fatal(message)`.
  - Recoverable tool errors are converted into model-visible failure tool outputs and still request follow-up sampling.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Maps fatal tool-dispatch failures escaping the Python `ToolCallRuntime` shim into `CodexErr.fatal(...)` at the user-turn runtime boundary.
  - Preserves existing recoverable tool-output behavior and follow-up request construction.
- `tests/test_core_turn_runtime.py`
  - Added coverage that a fatal tool handler error during `run_user_turn_sampling_from_session()` raises `CodexErr` with kind `fatal` after recording the original function call.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_maps_fatal_tool_error_to_codex_err tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_and_records_tool_outputs`
  - 2 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_exec_local_runtime`
  - 236 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 770 tests passed, 1 skipped.

### Follow-up Debt

- `pycodex/core/tool_parallel.py` still exposes fatal tool errors as `RuntimeError` internally. The turn runtime now preserves the user-facing Rust error boundary, but the lower-level helper can be tightened in a later core-path pass once its existing internal tests are updated deliberately.

## 2026-06-01 Model-Visible Tool Parse Errors

### Scope

- Continued the same graph-selected model-output-item handling slice.
- Focused on recoverable tool-call construction errors, especially malformed client `tool_search` arguments, so the agent loop can ask the model to recover instead of ending the turn.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
  - `function:codex-rs/core/src/tools/router.rs#build_tool_call:96`
- Rust source confirmed:
  - `ToolRouter::build_tool_call` returns `FunctionCallError::RespondToModel(...)` when client `tool_search` arguments fail to parse.
  - `handle_output_item_done` records the original response item, appends a `FunctionCallOutput` with empty `call_id`, marks the turn as needing follow-up, and lets the next sampling request carry the model-visible error.
  - Fatal tool-call construction errors still become `CodexErr::Fatal`.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Catches `FunctionCallError` raised while building tool calls from response items.
  - Converts model-visible errors into an empty-`call_id` `function_call_output` and preserves follow-up sampling behavior.
  - Converts fatal build errors into `CodexErr.fatal(...)`.
- `pycodex/core/compact_remote.py`
  - Preserves empty-`call_id` function outputs during prompt history normalization so model-visible tool parse errors are not removed as orphan outputs.
- Tests:
  - `tests/test_core_turn_runtime.py` covers malformed client `tool_search` arguments recovering through a follow-up request.
  - `tests/test_core_compact_remote.py` covers preserving the empty-`call_id` error output.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_responds_to_bad_tool_search_arguments tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_maps_fatal_tool_error_to_codex_err tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_and_records_tool_outputs tests.test_core_compact_remote.CompactRemoteTests.test_remove_orphan_outputs_keeps_empty_function_output_for_model_visible_tool_error`
  - 4 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_compact_remote tests.test_core_stream_events_utils`
  - 153 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 772 tests passed, 1 skipped.

## 2026-06-01 Unbounded Tool Follow-up Loop

### Scope

- Continued from model-visible tool outputs into the sampling follow-up loop.
- Focused on preserving Rust's user-visible behavior for multi-step tool chains: keep sampling after tool outputs until the model stops requesting follow-up and returns a final answer.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
- Rust source confirmed:
  - `try_run_sampling_request` returns `SamplingRequestResult { needs_follow_up, last_agent_message }`.
  - The outer turn loop continues while `needs_follow_up` is true, including tool-call follow-ups.
  - There is no fixed default count of tool follow-up requests in the Rust loop; it stops when the model no longer emits follow-up work or when an error/compaction path intervenes.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Changed the default `max_tool_followups` for `run_user_turn_sampling_from_session()` and `run_user_input_op_sampling_from_session()` from `8` to `None`.
  - Preserved explicit caps for tests/debugging and callers that intentionally pass `max_tool_followups=0` or another integer.
- `tests/test_core_turn_runtime.py`
  - Added coverage for a 10-tool chain that would have been cut off by the old default and now continues through the final assistant answer.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_can_limit_tool_followups tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_and_records_tool_outputs tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_responds_to_bad_tool_search_arguments`
  - 4 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_exec_local_runtime`
  - 147 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 773 tests passed, 1 skipped.

## 2026-06-01 HTTP Sampling Follow-up Default

### Scope

- Closed the previous follow-up-loop parity slice through the stdlib HTTP sampling wrapper used by local exec.
- Focused on ensuring the `codex exec` HTTP path inherits the Rust-like unbounded default rather than reintroducing the old 8-follow-up cap.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `file:codex-rs/core/src/client.rs`
- Rust source confirmed:
  - Sampling retry is transport-level; tool follow-up continuation is controlled by the turn loop's `needs_follow_up`, not by a fixed transport wrapper count.
  - The model client/HTTP transport layer does not impose a default 8-tool-follow-up cutoff.

### Python Changes

- `pycodex/core/http_transport.py`
  - Changed `run_user_turn_http_sampling_from_session(..., max_tool_followups=...)` default from `8` to `None`, matching `pycodex.core.turn_runtime`.
- `tests/test_core_http_transport.py`
  - Added coverage for the full HTTP wrapper path where 10 consecutive function-call responses continue through a final assistant message.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_run_user_turn_http_sampling_from_session_default_followups_continue_until_final_answer tests.test_core_http_transport.HttpTransportTests.test_run_user_turn_http_sampling_from_session_wraps_full_http_path tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
  - 3 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 133 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 774 tests passed, 1 skipped.

## 2026-06-01 Local HTTP Tool Search Rollout Interleaving

### Scope

- Tightened the local `codex exec` HTTP rollout/session-history path for multi-call client `tool_search`.
- Focused on preserving the prompt-visible ordering needed for resume/debug history: model calls first, then the matching tool outputs before the next model response.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
  - `file:codex-rs/core/src/tools/parallel.rs`
  - `function:codex-rs/core/src/tools/parallel.rs#handle_tool_call:63`
- Rust source confirmed:
  - Client `tool_search_call` items with `call_id` receive `tool_search_output` response input items.
  - Prompt/history normalization treats `tool_search_call` with a call id as a call that should have a matching output, like function and custom tool calls.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Counted client `tool_search_call` items with `call_id` when interleaving `tool_response_items` between raw HTTP response payloads for rollout persistence.
  - Kept server-side/no-call-id tool search behavior out of the local tool-output count.
- `tests/test_exec_local_runtime.py`
  - Added coverage for one raw response containing two client `tool_search_call` items followed by two matching outputs and a final assistant message.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_interleaves_multiple_client_tool_search_outputs`
  - 1 test passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 89 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 134 tests passed.

## 2026-06-01 HTTP Responses SSE Parsing

### Scope

- Advanced the real `codex exec` HTTP path from JSON-only response handling toward Rust's streamed Responses API behavior.
- Focused on the minimal stdlib transport slice needed when requests include `"stream": true`: parse SSE output-item and completion events into the same `PreparedSamplingResult` shape used by the existing agent loop.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
  - `function:codex-rs/core/src/client.rs#map_response_stream:1755`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
- Rust source confirmed:
  - The Responses API path streams `ResponseEvent::OutputItemDone(item)` and forwards completed items into the turn loop.
  - `ResponseEvent::Completed` is the provider terminal event.
  - If the stream ends before `response.completed`, Rust records/reports `stream closed before response.completed`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Added a standard-library SSE fallback when the HTTP body is not a single JSON payload.
  - Parses `response.output_item.done` events into `ResponseItem` instances.
  - Parses `response.completed` into a raw response payload while preserving usage and response id metadata for existing exec usage extraction.
  - Maps pre-completion stream closure to `CodexErr.response_stream_failed("stream closed before response.completed")`.
- `tests/test_core_http_transport.py`
  - Added coverage for streamed output-item/completed events.
  - Added coverage for stream closure before `response.completed`.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_parses_responses_sse_stream tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_errors_when_sse_closes_before_completed`
  - 2 tests passed.
- `python -m unittest tests.test_core_http_transport`
  - 17 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 141 tests passed.

## 2026-06-01 HTTP Responses SSE Event Name Fallback

### Scope

- Hardened the stdlib SSE parser added for real `codex exec` HTTP streaming.
- Focused on standard SSE framing parity: event kind can be carried by the `event:` field even when the JSON data payload does not repeat a `type` field.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
  - `function:codex-rs/core/src/client.rs#map_response_stream:1755`
- Rust source confirmed:
  - Rust receives already-classified `ResponseEvent` values from the API layer, so downstream mapping does not depend on the JSON data object repeating its event type.

### Python Changes

- `pycodex/core/http_transport.py`
  - Tracks `event:` names while parsing SSE blocks.
  - Injects the event name as `type` only when the data object lacks a `type`, preserving explicit payload types when present.
- `tests/test_core_http_transport.py`
  - Added coverage for `response.output_item.done` and `response.completed` events where data JSON omits `type`.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 18 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 142 tests passed.

## 2026-06-01 HTTP Identity Error Header Diagnostics

### Scope

- Continued the HTTP transport error mapping slice for the common `codex exec` runtime path.
- Focused on preserving Rust's user-visible diagnostics for unexpected identity/auth HTTP failures: request id, cf-ray, authorization error, and nested error code headers.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/api_bridge.rs#map_api_error:18`
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
- Rust source/tests confirmed:
  - Unknown HTTP statuses become `CodexErr::UnexpectedStatus`.
  - `x-request-id`/`x-oai-request-id`, `cf-ray`, `x-openai-authorization-error`, and base64 `x-error-json` details are preserved in the unexpected-status payload.
  - Header matching is case-insensitive through Rust's `HeaderMap`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Made `_header_value()` perform a case-insensitive scan for mapping-like headers after direct getter lookups.
  - This preserves identity/auth diagnostics for ordinary dict headers used by stdlib/fake transports, not only `email.message.Message`-style headers.
- `tests/test_core_http_transport.py`
  - Added a 401 unexpected-status regression with mixed-case dict headers and base64 `X-Error-Json`.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_preserves_identity_error_headers_case_insensitively tests.test_core_http_transport`
  - 20 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 151 tests passed.

## 2026-06-01 HTTP Timeout Error Mapping

### Scope

- Continued the Rust `map_api_error` parity slice for stdlib HTTP sampling.
- Focused on preserving user-visible timeout classification in the common `codex exec` HTTP path.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/api_bridge.rs#map_api_error:18`
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
- Rust source confirmed:
  - `TransportError::Timeout` maps to `CodexErr::RequestTimeout`.
  - Network/build errors map to stream/connection-style failures, so timeout is intentionally distinct from a generic connection failure.

### Python Changes

- `pycodex/core/http_transport.py`
  - Maps direct `TimeoutError` from `urlopen` to `CodexErr.simple("request_timeout")`.
  - Maps `URLError` values whose `reason` is `TimeoutError` to the same request-timeout kind.
  - Keeps non-timeout `URLError` values on the existing `connection_failed` path.
- `tests/test_core_http_transport.py`
  - Added coverage for both direct and `URLError`-wrapped timeout failures.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_timeouts_to_request_timeout tests.test_core_http_transport`
  - 21 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 152 tests passed.

## 2026-06-01 SSE Rate Limit Retry Mapping

### Scope

- Continued the real Responses SSE transport slice for `codex exec`.
- Focused on preserving Rust's retryable handling for `response.failed` events carrying `rate_limit_exceeded`.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
  - `function:codex-rs/core/src/client.rs#map_response_stream:1755`
  - `function:codex-rs/codex-api/src/api_bridge.rs#map_api_error:18`
- Rust source/tests confirmed:
  - `codex-api/src/sse/responses.rs` maps `response.failed` errors with known fatal codes to fatal API errors.
  - Unknown/retryable failures, including `rate_limit_exceeded`, become `ApiError::Retryable { message, delay }`.
  - `map_api_error` converts retryable API errors into `CodexErr::Stream(message, delay)`.
  - The retry delay is parsed from messages like `Please try again in 11.054s` and supports `s`, `seconds`, and `ms`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Maps `rate_limit_exceeded` errors in Responses payload/SSE events to `CodexErr.stream(...)`.
  - Parses retry-after seconds from the error message using the same standard-library-only pattern shape as Rust's regex.
- `tests/test_core_http_transport.py`
  - Added coverage for `response.failed` SSE rate-limit events preserving message, retry-after payload, and retryability.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_sse_rate_limit_failed_to_stream_retry tests.test_core_http_transport`
  - 22 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 153 tests passed.

## 2026-06-01 SSE Incomplete Response Mapping

### Scope

- Continued the real Responses SSE transport slice for `codex exec`.
- Focused on preserving Rust's user-visible `response.incomplete` reason instead of falling back to a generic event-name error.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
  - `function:codex-rs/core/src/client.rs#map_response_stream:1755`
- Rust source confirmed:
  - `codex-api/src/sse/responses.rs` handles `response.incomplete` separately from `response.failed`.
  - It reads `response.incomplete_details.reason`, defaults to `unknown`, and emits `ApiError::Stream("Incomplete response returned, reason: {reason}")`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Handles `response.incomplete` before generic SSE error handling.
  - Raises `CodexErr.stream("Incomplete response returned, reason: ...")`, preserving the reason and retryable stream classification.
- `tests/test_core_http_transport.py`
  - Added coverage for `response.incomplete` SSE events carrying `incomplete_details.reason`.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_sse_incomplete_reason_to_stream tests.test_core_http_transport`
  - 23 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 154 tests passed.

## 2026-06-01 SSE Failed Fallback Mapping

### Scope

- Continued the real Responses SSE transport slice for `codex exec`.
- Focused on preserving Rust's retryable stream classification for `response.failed` events when the error is unknown, unrecognized, or missing.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
  - `function:codex-rs/core/src/client.rs#map_response_stream:1755`
  - `function:codex-rs/codex-api/src/api_bridge.rs#map_api_error:18`
- Rust source confirmed:
  - `codex-api/src/sse/responses.rs` initializes `response.failed` as `ApiError::Stream("response.failed event received")`.
  - Recognized fatal codes override that default.
  - Unrecognized parsed errors become retryable stream errors using the provider error message.

### Python Changes

- `pycodex/core/http_transport.py`
  - Handles `response.failed` separately from generic SSE error events.
  - Preserves unknown provider error messages as `CodexErr.stream(message)`.
  - Uses `CodexErr.stream("response.failed event received")` when the event has no usable response/error payload.
- `tests/test_core_http_transport.py`
  - Added coverage for unknown `response.failed` provider errors.
  - Added coverage for `response.failed` without a response payload.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_unknown_sse_failed_to_stream tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_sse_failed_without_response_to_stream tests.test_core_http_transport`
  - 26 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 156 tests passed.

## 2026-06-01 SSE Completed Response Validation

### Scope

- Continued the Responses SSE terminal-event slice for `codex exec`.
- Focused on preserving Rust's distinction between a valid `response.completed` terminal event and malformed/non-terminal completed-looking events.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/client.rs#stream_responses_api:1241`
  - `function:codex-rs/core/src/client.rs#map_response_stream:1755`
- Rust source confirmed:
  - `codex-api/src/sse/responses.rs` parses `response.completed` into `ResponseCompleted { id, usage, end_turn }`.
  - Missing `response` does not emit a terminal completed event.
  - Malformed `response` maps to `ApiError::Stream("failed to parse ResponseCompleted: ...")`.
  - If no valid completed event arrives before stream close, Rust reports `stream closed before response.completed`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Treats `response.completed` as terminal only when `response` is a mapping with a string `id`.
  - Validates required usage counters when usage is present.
  - Maps malformed completed payloads to `CodexErr.stream("failed to parse ResponseCompleted: ...")`.
  - Leaves completed events without a response payload non-terminal, so they fall through to the existing closed-before-completed error.
- `tests/test_core_http_transport.py`
  - Added malformed completed payload coverage.
  - Added completed-without-response coverage.
  - Updated streamed success fixtures to include Rust-required `total_tokens` when usage is present.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 26 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime`
  - 158 tests passed.

## 2026-06-01 SSE Rate Limit Millisecond Retry Coverage

### Scope

- Continued the Responses SSE transport slice for `codex exec`.
- Focused on Rust's millisecond retry-delay parsing for retryable `response.failed` rate-limit events.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#spawn_response_stream:29`
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
  - `function:codex-rs/codex-api/src/sse/responses.rs#try_parse_retry_after:487`
- Rust source confirmed:
  - `process_responses_event` maps unrecognized `response.failed` API errors to retryable errors with an optional parsed delay.
  - `try_parse_retry_after` accepts `s`, `seconds`, and `ms` units.
  - Rust coverage includes a `Please try again in 28ms` message and expects `Duration::from_millis(28)`.

### Python Changes

- `tests/test_core_http_transport.py`
  - Added SSE `response.failed` rate-limit coverage for a `28ms` retry message.
  - Asserted the Python `CodexErr.stream(...)` payload is `0.028` seconds and remains retryable.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 27 tests passed.

## 2026-06-01 HTTP Success Rate-Limit Header Recording

### Scope

- Continued the `exec -> model stream/http result -> session token count` slice.
- Focused on Rust's response-header metadata path for successful Responses API calls, without expanding into model verification, MCP, plugin, or marketplace behavior.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#spawn_response_stream:29`
  - `function:codex-rs/codex-api/src/rate_limits.rs#parse_all_rate_limits:28`
  - `function:codex-rs/core/src/session/turn.rs#run:...` metadata match arm around `ResponseEvent::RateLimits`
- Rust source confirmed:
  - `spawn_response_stream` parses all known rate-limit header families before processing SSE body events.
  - `parse_all_rate_limits` emits the default `codex` snapshot plus additional header families discovered from `*-primary-used-percent`.
  - The turn loop records `ResponseEvent::RateLimits` into session state and defers token-count emission until usage is available.

### Python Changes

- `pycodex/core/http_transport.py`
  - Captures successful HTTP response headers before reading the body.
  - Parses the default Codex rate-limit header family and additional discovered families.
  - Attaches parsed snapshots to the standard-library `PreparedSamplingResult`.
- `pycodex/core/turn_sampler.py`
  - Carries transport-provided rate-limit snapshots across the model-session sampler wrapper.
- `pycodex/core/turn_runtime.py`
  - Records sampler rate-limit snapshots into the session before recording token usage, so the emitted token-count event can include the latest limits.
- `tests/test_core_http_transport.py`
  - Added end-to-end local HTTP coverage for successful response headers being recorded into session token-count events.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 28 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_exec_local_runtime`
  - 223 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 788 tests passed, 1 skipped.

## 2026-06-01 HTTP Response Header Metadata Recording

### Scope

- Continued the response metadata path used by the common `codex exec` runtime.
- Focused on the user-visible `ServerModel` behavior and small state updates carried by successful Responses API headers.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#spawn_response_stream:29`
  - `function:codex-rs/core/src/session/turn.rs#...` match arms for `ResponseEvent::ServerModel`, `ServerReasoningIncluded`, `RateLimits`, and `ModelsEtag`
  - `function:codex-rs/core/src/session/mod.rs#maybe_warn_on_server_model_mismatch:2495`
  - `function:codex-rs/core/src/session/mod.rs#set_server_reasoning_included:3017`
- Rust source confirmed:
  - `spawn_response_stream` emits `ServerModel` from `openai-model`, `ServerReasoningIncluded(true)` when `x-reasoning-included` is present, and `ModelsEtag` from `X-Models-Etag`.
  - The turn loop calls `maybe_warn_on_server_model_mismatch` for `ServerModel` and only emits the warning once per turn context.
  - `maybe_warn_on_server_model_mismatch` emits both `model_reroute` and `warning` events when the backend reports a different model.

### Python Changes

- `pycodex/core/http_transport.py`
  - Captures `openai-model`, `x-reasoning-included`, and `x-models-etag` from successful HTTP/SSE responses.
- `pycodex/core/turn_sampler.py`
  - Carries response header metadata through the model-session sampler wrapper.
- `pycodex/core/turn_runtime.py`
  - Applies response metadata before token usage recording, including one-per-turn server-model mismatch warnings.
- `pycodex/core/session_runtime.py`
  - Added lightweight `maybe_warn_on_server_model_mismatch`, `set_server_reasoning_included`, and `refresh_models_etag` support.
- `tests/test_core_http_transport.py`
  - Added end-to-end local HTTP coverage for reroute warning events, reasoning-included state, models etag recording, and the final token-count event.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 29 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 292 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 789 tests passed, 1 skipped.

## 2026-06-01 SSE Model Verification Metadata

### Scope

- Continued the Responses SSE metadata path on the common `codex exec` runtime.
- Focused on user-visible account verification recommendations emitted by the backend, while avoiding deeper account, marketplace, plugin, or MCP behavior.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#model_verifications_from_json_value:210`
  - `function:codex-rs/codex-api/src/sse/responses.rs#response_model:170`
  - `function:codex-rs/core/src/session/mod.rs#emit_model_verification:2534`
- Rust source confirmed:
  - Only `response.metadata` events are considered for `openai_verification_recommendation`.
  - `trusted_access_for_cyber` maps to `ModelVerification::TrustedAccessForCyber`.
  - Duplicate and unknown verification strings are ignored.
  - The turn loop emits `model_verification` only once per turn context.

### Python Changes

- `pycodex/core/http_transport.py`
  - Parses SSE `response.metadata` verification recommendations into protocol `ModelVerification` values.
  - Parses OpenAI model headers from SSE event `response.headers` or top-level `headers`, matching Rust's stream-event path.
- `pycodex/core/turn_sampler.py`
  - Carries model-verification metadata and server-model sequences through the model-session sampler wrapper.
- `pycodex/core/turn_runtime.py`
  - Applies model-verification metadata once per turn and de-duplicates nested sampler/transport metadata.
  - De-duplicates nested rate-limit snapshots while traversing wrapped sampler results.
- `pycodex/core/session_runtime.py`
  - Added lightweight `emit_model_verification` support for in-memory sessions.
- `tests/test_core_http_transport.py`
  - Added SSE metadata coverage for trusted-access verification, duplicate suppression, unknown-value filtering, SSE model header reroute handling, and token-count continuation.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 30 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_core_stream_events_utils`
  - 399 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 790 tests passed, 1 skipped.

## 2026-06-01 Local HTTP Exec Metadata Event Replay

### Scope

- Continued the `Responses metadata -> session event -> exec output` path.
- Focused on making already-ported session metadata events visible through the local HTTP `codex exec` processors.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/mod.rs#emit_model_verification:2534`
  - `function:codex-rs/core/src/session/mod.rs#maybe_warn_on_server_model_mismatch:2495`
  - `function:codex-rs/core/src/session/mod.rs#send_event:1595`
- Rust source confirmed:
  - `Warning`, `ModelReroute`, `ModelVerification`, and `TokenCount` are ordinary session events emitted through the same event path.
  - `emit_model_verification` sends `EventMsg::ModelVerification`.
  - server-model mismatch sends both `EventMsg::ModelReroute` and `EventMsg::Warning`.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Replays local HTTP session `warning`, `model_reroute`, and `model_verification` events as processor notifications.
  - Keeps `model_verification` silent in CLI processors, matching the existing processor behavior, while still preserving the notification method.
- `pycodex/exec/event_processor.py`
  - Treats direct `warning` notifications like existing config/deprecation warnings for both JSON and human processors.
- `tests/test_exec_local_runtime.py`
  - Added coverage that local HTTP exec results replay metadata events before the final turn result and preserve user-visible warning/reroute output.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_replays_metadata_session_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_error_replays_attached_session_events tests.test_exec_event_processor.ExecEventProcessorTests.test_json_processor_model_reroute_reason_matches_upstream_debug_name`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_turn_sampler`
  - 294 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 791 tests passed, 1 skipped.

## 2026-06-01 Local HTTP Exec Error Metadata Ordering Coverage

### Scope

- Continued hardening local HTTP `codex exec --json` event ordering.
- Focused on terminal-error paths where session metadata events are attached to the raised `CodexErr`.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/turn.rs#...` context-window error branch around `set_total_tokens_full`
  - `function:codex-rs/core/src/session/mod.rs#send_event:1595`
- Rust source confirmed:
  - Terminal sampling errors can emit session events before returning the final error.
  - Those events still belong to the active turn event stream bounded by `TurnStarted` and terminal completion/failure.

### Python Changes

- `tests/test_exec_local_runtime.py`
  - Added coverage that attached metadata events on a local HTTP `CodexErr` are replayed after `turn.started` and before `turn.failed`.
  - Confirmed silent `model_verification` metadata does not produce a CLI item, while reroute and warning do.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_error_replays_metadata_session_events_inside_turn tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_error_replays_attached_session_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_replays_metadata_session_events`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_session`
  - 298 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 792 tests passed, 1 skipped.

## 2026-06-01 SSE Assistant Text Delta Accumulation

### Scope

- Returned to the core `Responses SSE -> final answer` path after metadata replay work.
- Focused on assistant text streams that provide `response.output_item.added` and `response.output_text.delta` events before `response.completed`, rather than a single `response.output_item.done` item.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
  - `class:codex-rs/codex-api/src/sse/responses.rs#ResponseCompleted:100`
- Rust source confirmed:
  - `process_responses_event` maps `response.output_item.added` to `ResponseEvent::OutputItemAdded`.
  - `process_responses_event` maps `response.output_text.delta` to `ResponseEvent::OutputTextDelta`.
  - The Rust turn loop keeps an active assistant item and applies text deltas to that streamed item.

### Python Changes

- `pycodex/core/http_transport.py`
  - Added a minimal standard-library SSE accumulator for assistant message text deltas.
  - Seeds an assistant message from `response.output_item.added`, appends `response.output_text.delta` chunks, and exposes the accumulated text through both `response_items` and raw `output`.
  - Leaves tool-call input deltas and reasoning deltas deferred to later slices.
- `tests/test_core_http_transport.py`
  - Added coverage for a delta-only assistant message stream producing the final text and raw output payload.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 31 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 233 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 793 tests passed, 1 skipped.

## 2026-06-01 SSE Streamed Item Done Replacement

### Scope

- Tightened the assistant text delta accumulator so common SSE streams with both streamed deltas and a final `output_item.done` do not duplicate the same assistant message.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
  - `function:codex-rs/core/src/session/turn.rs#...` `ResponseEvent::OutputItemDone` and `OutputItemAdded` arms
- Rust source confirmed:
  - `OutputItemAdded` establishes an active streamed item.
  - `OutputItemDone` receives the previously streamed item and completes that item rather than creating a duplicate user-visible assistant message.

### Python Changes

- `pycodex/core/http_transport.py`
  - When `response.output_item.done` has the same id as the active delta-seeded assistant message, it replaces the seeded item.
  - Non-matching done items continue to append normally.
- `tests/test_core_http_transport.py`
  - Added coverage for `output_item.added` + `output_text.delta` + matching `output_item.done`, asserting exactly one final assistant item and raw output entry.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 32 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 234 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 794 tests passed, 1 skipped.

## 2026-06-01 Local HTTP Exec JSON Metadata Ordering

### Scope

- Tightened the local HTTP `codex exec --json` event order after metadata event replay was added.
- Focused on keeping metadata notifications inside the turn lifecycle instead of emitting them before `turn.started`.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/session/mod.rs#send_event:1595`
  - `function:codex-rs/core/src/session/mod.rs#emit_model_verification:2534`
- Rust source confirmed:
  - Metadata events such as `Warning`, `ModelReroute`, and `ModelVerification` flow through the normal session event stream.
  - Suite tests commonly observe `TurnStarted` as the boundary before turn-scoped events.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Emits `turn.started` before replaying local HTTP metadata session events in JSON mode.
  - Keeps token-usage replay before `turn.completed`, so fallback usage from session events still feeds final usage output.
- `tests/test_exec_local_runtime.py`
  - Updated metadata replay coverage to assert the JSON event stream starts with `turn.started`, followed by reroute/warning metadata, then final turn completion.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_replays_metadata_session_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_uses_session_token_count_event_when_raw_usage_missing`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_session`
  - 297 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 791 tests passed, 1 skipped.

## 2026-06-01 SSE Streamed Message Done Without Id

### Scope

- Closed a small Responses SSE parity gap on the core stream-handling path.
- Targeted streams where `response.output_item.added` seeds an assistant message, `response.output_text.delta` supplies text, and the final `response.output_item.done` completes the same active item without an explicit item id.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
- Rust source confirmed:
  - `response.custom_tool_call_input.delta` is parsed into `ResponseEvent::ToolCallInputDelta` and routed to a tool argument diff consumer for streaming display.
  - Final tool dispatch still comes from `ResponseEvent::OutputItemDone(ResponseItem)` through `handle_output_item_done`.
  - `OutputItemDone` completes the previously active streamed item by sequence, not only by a matching item id.

### Python Changes

- `pycodex/core/http_transport.py`
  - Added `_sse_done_replaces_active_delta`.
  - Keeps strict id matching when `output_item.added` includes an id.
  - Allows the next id-less assistant `output_item.done` to replace the active id-less streamed message, preventing duplicate final messages while preserving append behavior for unrelated done items.
- `tests/test_core_http_transport.py`
  - Added coverage for id-less `output_item.added` + text delta + id-less `output_item.done`, asserting one final assistant item and one raw output entry.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 33 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 795 tests passed, 1 skipped.

### Deferred

- Superseded follow-up: Python now preserves Rust-style normalized SSE stream events on HTTP sampling results, including `ToolCallInputDelta`. Runtime consumption of those events is still a follow-up; current local HTTP tool dispatch remains driven by completed `ResponseItem`s.

## 2026-06-01 SSE Completed Empty Output Backfill

### Scope

- Preserved model output visibility for local HTTP exec when a Responses SSE stream provides completed items as events but the final `response.completed` payload includes an empty `output` array.
- This protects tool-call timeline reconstruction and rollout payload generation, both of which consume the raw Responses payload in addition to typed `response_items`.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
- Rust source confirmed:
  - Each `response.output_item.done` is parsed into `ResponseEvent::OutputItemDone(ResponseItem)`.
  - The session turn loop handles these completed items directly for message finalization and tool dispatch.
  - Tool dispatch does not depend on the final `response.completed.response.output` array containing the same items.

### Python Changes

- `pycodex/core/http_transport.py`
  - Added `_responses_output_is_empty`.
  - Backfills `raw_result["output"]` from parsed SSE `response_items` when completed output is missing or contains no object items.
  - Leaves non-empty completed `output` untouched.
- `tests/test_core_http_transport.py`
  - Added coverage for an SSE `function_call` delivered via `response.output_item.done` followed by `response.completed` with `output: []`, asserting both typed `response_items` and raw output contain the tool call.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 34 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 201 tests passed.

## 2026-06-01 Responses Completed End Turn Follow-Up

### Scope

- Ported the `response.completed.response.end_turn == false` continuation behavior into the local HTTP runtime path.
- This covers model-driven continuations that do not produce a tool call in the current response but still require another sampling request before the turn is complete.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `class:codex-rs/codex-api/src/sse/responses.rs#ResponseCompleted:100`
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
- Rust source confirmed:
  - `ResponseCompleted` includes optional `end_turn`.
  - `process_responses_event` maps it onto `ResponseEvent::Completed`.
  - The session turn loop sets `needs_follow_up = true` when `end_turn` is explicitly `false`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Carries JSON and SSE completed `end_turn` into `PreparedSamplingResult`.
- `pycodex/core/turn_sampler.py`
  - Added `end_turn` to `PreparedSamplingResult` and propagated it through the model-client sampling adapter.
- `pycodex/core/turn_runtime.py`
  - Added `_sampling_result_needs_followup`.
  - The local sampling loop now continues when the latest result has `end_turn is False`, even if there are no tool response items to send back.
- `tests/test_core_http_transport.py`
  - Added an end-to-end local HTTP sampling test where a first response returns an assistant message with `end_turn: false` and no tools, followed by a second final response.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_run_user_turn_http_sampling_follows_completed_end_turn_false_without_tools tests.test_core_http_transport`
  - 36 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 237 tests passed.

## 2026-06-01 SSE Malformed Output Item Tolerance

### Scope

- Matched Rust's tolerant handling for malformed `response.output_item.added` and `response.output_item.done` events.
- This keeps a single malformed or forward-compatible output item from aborting an otherwise valid Responses SSE stream.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
- Rust source confirmed:
  - `response.output_item.done` attempts to parse `ResponseItem`, returns `OutputItemDone` on success, and only logs `failed to parse ResponseItem from output_item.done` on failure.
  - `response.output_item.added` follows the same tolerant parse-and-skip behavior.
  - `response.completed` parsing remains strict because it closes the stream and carries the response id/usage/end-turn state.

### Python Changes

- `pycodex/core/http_transport.py`
  - Added `_sse_response_item_or_none`.
  - `response.output_item.done` now skips malformed item payloads instead of raising.
  - `response.output_item.added` validates the item before seeding streamed assistant text, and skips malformed payloads.
  - Completed response validation is unchanged and remains strict.
- `tests/test_core_http_transport.py`
  - Added coverage for malformed added/done events followed by a valid done event and completed response, asserting the valid final message is preserved in both typed items and raw output.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 36 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 233 tests passed.

## 2026-06-01 SSE Malformed Data Event Tolerance

### Scope

- Matched Rust's tolerant handling for individual malformed SSE data frames on the Responses stream.
- A bad JSON frame or non-object frame no longer aborts an otherwise valid stream; the stream still fails if it closes without a valid `response.completed`.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_sse:399`
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
- Rust source confirmed:
  - `process_sse` attempts to deserialize each SSE data payload as `ResponsesStreamEvent`.
  - Deserialization failures are debug-logged and skipped with `continue`.
  - Closing before a valid `response.completed` still raises `stream closed before response.completed`.

### Python Changes

- `pycodex/core/http_transport.py`
  - `_append_sse_event` now ignores malformed JSON data frames and JSON values that are not objects.
  - The parser still requires at least one valid JSON event and a valid completed response to return a result.
- `tests/test_core_http_transport.py`
  - Added coverage for malformed JSON and non-object SSE data frames followed by valid `output_item.done` and `response.completed` events.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 37 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 234 tests passed.

## 2026-06-01 SSE No Valid Events Closed-Before-Completed Error

### Scope

- Tightened the terminal error for SSE streams where every data frame is malformed or non-object.
- This preserves Rust's user-facing behavior: after skipping bad frames, closing without a valid completed response reports `stream closed before response.completed`.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_sse:399`
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
- Rust source confirmed:
  - `process_sse` skips parse failures with `continue`.
  - When the stream then ends and no completed response was processed, it sends `ApiError::Stream("stream closed before response.completed")`.

### Python Changes

- `pycodex/core/http_transport.py`
  - `_parse_responses_sse_stream` now maps an empty valid-event list to `ResponseStreamFailed("stream closed before response.completed")`.
  - This replaces the Python-only `"response stream did not contain JSON events"` message on the Responses stream path.
- `tests/test_core_http_transport.py`
  - Added coverage for a stream containing only malformed/non-object SSE data frames, asserting the Rust-shaped closed-before-completed error.

### Validation

- `python -m unittest tests.test_core_http_transport`
  - 38 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_exec_local_runtime tests.test_exec_event_processor`
  - 235 tests passed.

## 2026-06-01 Local HTTP Reasoning Raw Content Visibility

### Scope

- Tightened local HTTP exec reasoning output so raw `reasoning_text` content is not surfaced by default.
- This preserves the common user-facing behavior where reasoning summaries are shown, while raw reasoning is gated behind explicit raw-reasoning display paths.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_non_tool_response_item:455`
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `class:codex-rs/protocol/src/protocol.rs#ReasoningContentDeltaEvent:1743`
- Rust source confirmed:
  - Reasoning summary deltas are emitted separately from raw reasoning content deltas.
  - The event processor has a `show_raw_agent_reasoning` gate for raw reasoning display.
  - Protocol serialization suppresses hidden `reasoning_text` content by default.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_text_from_value` now ignores mapping entries whose `type` is `reasoning_text`.
  - Public `text` entries and `summary` entries continue to contribute to local HTTP reasoning events.
- `tests/test_exec_local_runtime.py`
  - Added coverage that a local HTTP reasoning payload with summary, public `text`, and raw `reasoning_text` emits only the public note plus summary by default.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_reasoning_texts_skip_raw_reasoning_content_by_default tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_maps_reasoning_json_event`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_core_http_transport`
  - 206 tests passed.

## 2026-06-01 Local HTTP Reasoning Summary Text Alias

### Scope

- Aligned local HTTP exec reasoning extraction with the core/app-server reasoning item shape.
- `summary_text`/`summaryText` aliases are accepted as summary fields, while `raw_content` stays hidden on the default exec output path.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/core/src/event_mapping.rs#parse_turn_item:136`
  - `class:codex-rs/protocol/src/items.rs#ReasoningItem:120`
  - `class:codex-rs/exec/src/exec_events.rs#ReasoningItem:141`
  - `class:codex-rs/app-server-protocol/src/protocol/v2/item.rs#RawResponseItemCompletedNotification:1147`
- Rust source confirmed:
  - `parse_turn_item` maps Responses reasoning summaries into `ReasoningItem.summary_text` and raw reasoning/content into `ReasoningItem.raw_content`.
  - Human output uses `raw_content` only when `show_raw_agent_reasoning` is enabled.
  - JSON/JSONL exec output emits the joined summary text, not raw content.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_reasoning_text_from_item` now accepts `summary_text` and `summaryText` aliases.
  - Default reasoning extraction no longer reads `raw_content`/`rawContent`.
  - `_text_from_value` can unwrap nested `summary_text`/`summaryText` mappings and still suppresses `reasoning_text` entries.
- `tests/test_exec_local_runtime.py`
  - Updated app-server-style reasoning coverage so default local HTTP exec output emits the summary and hides raw content.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_reasoning_texts_skip_raw_reasoning_content_by_default tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_reasoning_texts_accept_app_server_style_fields`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_core_http_transport`
  - 207 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 802 tests passed, 1 skipped.

## 2026-06-01 Local HTTP Human Reasoning Raw Toggle

### Scope

- Tightened local HTTP exec reasoning rendering to match Rust's default exec behavior more closely.
- Default JSON and human exec output now use reasoning summaries only; raw reasoning/content is rendered only on the human path when `show_raw_agent_reasoning` is enabled.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#reasoning_text:467`
  - `class:codex-rs/exec/src/event_processor_with_human_output.rs#EventProcessorWithHumanOutput:23`
  - `class:codex-rs/exec/src/event_processor_with_jsonl_output.rs#EventProcessorWithJsonOutput:58`
  - `function:codex-rs/core/src/event_mapping.rs#parse_turn_item:136`
- Rust source confirmed:
  - `parse_turn_item` stores Responses reasoning `summary` as `summary_text` and `content` as `raw_content`.
  - Human output chooses `raw_content` only when `show_raw_agent_reasoning` is true and raw content is non-empty; otherwise it uses summary text.
  - JSON/JSONL exec output joins and emits summary text only.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added local HTTP reasoning `TurnItem` extraction preserving both summary text and raw content.
  - `reasoning_texts_from_local_http_exec_result` now returns summary text only, matching JSON exec behavior.
  - Human local HTTP rendering now feeds reasoning `TurnItem`s through the existing `HumanEventProcessor`, so `show_raw_agent_reasoning` controls raw content display consistently.
- `tests/test_exec_local_runtime.py`
  - Updated default reasoning expectations to hide all content/raw content.
  - Added coverage for human output using raw reasoning content only when the raw toggle is enabled.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_maps_reasoning_json_event tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_reasoning_texts_skip_raw_reasoning_content_by_default tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_reasoning_texts_accept_app_server_style_fields tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_human_reasoning_uses_raw_content_when_enabled`
  - 4 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_core_http_transport`
  - 208 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 803 tests passed, 1 skipped.

## 2026-06-01 Exec Raw Reasoning Config Propagation

### Scope

- Connected the exec configuration slice that enables raw reasoning display to the Python human-output processor path.
- This advances the Rust mainline behavior where `codex exec --oss` enables `show_raw_agent_reasoning` through config, and human output uses that config when rendering reasoning items.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/exec/src/lib.rs#run_main:232`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#create_with_ansi:42`
  - `class:codex-rs/exec/src/event_processor_with_human_output.rs#EventProcessorWithHumanOutput:23`
- Rust source confirmed:
  - `run_main` sets `ConfigOverrides.show_raw_agent_reasoning` to `Some(true)` when `oss` is enabled.
  - `run_exec_session` constructs `EventProcessorWithHumanOutput::create_with_ansi` with the resolved config.
  - `create_with_ansi` applies `show_agent_reasoning: !config.hide_agent_reasoning` and `show_raw_agent_reasoning: config.show_raw_agent_reasoning`.

### Python Changes

- `pycodex/exec/session.py`
  - `ExecSessionConfig` now carries `hide_agent_reasoning` and `show_raw_agent_reasoning` display flags.
- `pycodex/exec/config_plan.py`
  - `exec_session_config_from_bootstrap_plan` projects the existing OSS `showRawAgentReasoning` harness override into `ExecSessionConfig`.
- `pycodex/exec/event_processor.py`
  - `HumanEventProcessor.configure_from_config` applies `hide_agent_reasoning` / `show_raw_agent_reasoning` from mapping or object configs.
- `pycodex/exec/local_runtime.py`
  - `emit_local_http_exec_result` accepts an optional config and applies it to human processors before replaying local HTTP reasoning items.
- Tests:
  - Added coverage that OSS bootstrap config projects raw reasoning visibility.
  - Added coverage that human processors apply visibility flags from exec config.
  - Extended local HTTP human reasoning coverage to verify config-driven raw rendering.

### Validation

- `python -m unittest tests.test_exec_config_plan.ExecConfigPlanTests.test_exec_session_config_from_bootstrap_plan_projects_runtime_config tests.test_exec_config_plan.ExecConfigPlanTests.test_exec_session_config_projects_oss_raw_reasoning_override tests.test_exec_event_processor.ExecEventProcessorTests.test_human_processor_configures_reasoning_visibility_from_exec_config tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_human_reasoning_uses_raw_content_when_enabled`
  - 4 tests passed.
- `python -m unittest tests.test_exec_config_plan tests.test_exec_event_processor tests.test_exec_local_runtime`
  - 239 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 872 tests passed, 1 skipped.

### Follow-up Mapping Tightening

- `pycodex/exec/session.py`
  - `exec_session_config_mapping` now includes `hideAgentReasoning` and `showRawAgentReasoning`, so object and mapping config paths carry the same visibility flags.
- `pycodex/exec/config_plan.py`
  - `_exec_session_config_to_mapping` now includes the same reasoning visibility flags for startup-plan serialization.
- `tests/test_exec_session.py`
  - Added coverage for `ExecSessionConfig` mapping of both reasoning visibility flags.

### Additional Validation

- `python -m unittest tests.test_exec_session.ExecSessionRequestBuilderTests.test_session_config_mapping_carries_reasoning_visibility tests.test_exec_config_plan.ExecConfigPlanTests.test_exec_session_config_projects_oss_raw_reasoning_override tests.test_exec_event_processor.ExecEventProcessorTests.test_human_processor_configures_reasoning_visibility_from_exec_config tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_human_reasoning_uses_raw_content_when_enabled`
  - 4 tests passed.
- `python -m unittest tests.test_exec_session tests.test_exec_config_plan tests.test_exec_event_processor tests.test_exec_local_runtime`
  - 357 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 873 tests passed, 1 skipped.

## 2026-06-01 Exec Review Target Validation

### Scope

- Tightened Python `review/start` request construction to match Rust app-server review target normalization.
- This keeps CLI `review` request creation aligned with Rust while ensuring the app-server request boundary rejects or normalizes the same user-facing target values Rust does.

### Upstream Graph/Source Slice

- Graph nodes used:
  - `function:codex-rs/exec/src/lib.rs#build_review_request:1846`
  - `function:codex-rs/app-server/src/request_processors/turn_processor.rs#review_start:213`
  - `function:codex-rs/app-server/src/request_processors/turn_processor.rs#review_start_inner:1161`
- Rust source confirmed:
  - Exec CLI `build_review_request` constructs the selected review target.
  - App-server `review_request_from_target` trims base branch, commit sha/title, and custom instructions.
  - Empty trimmed base branch, commit sha, or custom instructions are rejected with `branch must not be empty`, `sha must not be empty`, and `instructions must not be empty`.

### Python Changes

- `pycodex/exec/session.py`
  - `ReviewStartParams` now normalizes review targets in `__post_init__`.
  - Base branches, commit SHAs, commit titles, and custom instructions are trimmed.
  - Empty base branch, commit SHA, or custom instructions raise `ValueError` with Rust-shaped messages.
- `tests/test_exec_session.py`
  - Added coverage for cleaned base branch, commit title removal, custom instruction trimming, and the three empty-target errors.

### Validation

- `python -m unittest tests.test_exec_session.ExecSessionRequestBuilderTests.test_review_start_params_and_client_request_match_app_server_wire_shape tests.test_exec_session.ExecSessionRequestBuilderTests.test_review_start_params_clean_and_validate_target_like_app_server`
  - 2 tests passed.
- `python -m unittest tests.test_exec_session tests.test_exec_run tests.test_exec_config_plan`
  - 210 tests passed.
- `python -m unittest tests.test_core_turn_sampler tests.test_core_responses_retry tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_config_plan tests.test_exec_run tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 897 tests passed, 1 skipped.

## 2026-06-01 Responses Stream Event Name Parity

### Scope

- Continued the graph-selected `exec -> model request -> stream handling -> tool dispatch` path.
- Tightened Python stream-dispatch helpers so they accept the same raw Responses SSE event names Rust maps in `process_responses_event`.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
  - `codex-rs/codex-api/src/sse/responses.rs#process_responses_event`
  - `codex-rs/core/src/session/turn.rs` `ResponseEvent::ToolCallInputDelta` branch
- Rust source confirmed:
  - `response.custom_tool_call_input.delta` maps to `ResponseEvent::ToolCallInputDelta`.
  - When the stream delta omits `call_id`, Rust keeps the active tool argument diff consumer's call id.
  - Reasoning summary/content deltas read `summary_index` and `content_index` from the SSE payload.

### Python Changes

- `pycodex/core/stream_events_utils.py`
  - Added Response API event-name aliases for the sampling stream dispatch helper.
  - Reads `call_id`, `summary_index`, and `content_index` from payloads when callers pass raw SSE-shaped events.
  - Preserves the existing simplified event names already used by tests and local runtime helpers.
- `tests/test_core_stream_events_utils.py`
  - Added coverage for `response.custom_tool_call_input.delta`, omitted `call_id` fallback to the active tool consumer, and `response.reasoning_text.delta` payload indexes.

### Validation

- `python -m unittest tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_stream_event_dispatch_plan_routes_deltas_and_metadata`
  - 1 test passed.
- `python -m unittest tests.test_core_stream_events_utils`
  - 106 tests passed.

## 2026-06-01 HTTP SSE ResponseEvent Preservation

### Scope

- Continued the same stream-handling slice from raw Responses SSE event parsing into the Python sampling boundary.
- Preserved Rust-style normalized `ResponseEvent` records on HTTP sampling results so later runtime code can consume streaming deltas without reparsing raw SSE text.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_sse:399`
  - `class:codex-rs/codex-api/src/common.rs#ResponseEvent:72`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
- Rust source confirmed:
  - `process_responses_event` maps raw SSE event names into `ResponseEvent` variants for created, output item added/done, output text delta, custom tool input delta, reasoning deltas, reasoning summary part added, and completed.
  - `ToolCallInputDelta` requires a delta plus either `item_id` or `call_id`; `call_id` remains optional on the event.
  - `Completed` carries response id, optional token usage, and optional `end_turn`.

### Python Changes

- `pycodex/core/http_transport.py`
  - `_parse_responses_sse_stream` now collects normalized `stream_events` alongside completed response items and metadata.
  - Added `_response_event_from_sse_event` to map raw SSE events into Rust-shaped internal event dictionaries.
  - SSE `PreparedSamplingResult` now exposes `stream_events`.
- `pycodex/core/turn_sampler.py`
  - `PreparedSamplingResult` now carries `stream_events`.
  - `sample_with_model_client_session` propagates transport-provided stream events.
- `tests/test_core_http_transport.py`
  - Added coverage for preserved output text, custom tool input, reasoning, and completed stream events.
- `tests/test_core_turn_sampler.py`
  - Added coverage that sampling preparation keeps transport stream events.

### Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_accumulates_sse_output_text_delta tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_records_rust_style_sse_stream_events tests.test_core_turn_sampler.TurnSamplerTests.test_sample_with_model_client_session_propagates_transport_stream_events`
  - 3 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_stream_events_utils`
  - 151 tests passed.

## 2026-06-01 Runtime StreamEvent Dispatch Projection

### Scope

- Continued from HTTP/SSE `ResponseEvent` preservation into the Python turn runtime boundary.
- Added a non-side-effecting dispatch projection so sampler-provided stream events are interpreted through the same state helpers used by the websocket/runtime planning path.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `class:codex-rs/codex-api/src/common.rs#ResponseEvent:72`
  - `function:codex-rs/codex-api/src/sse/responses.rs#process_responses_event:263`
- Rust source confirmed:
  - `try_run_sampling_request` maintains active streamed item state plus an active tool argument diff consumer.
  - `ResponseEvent::OutputItemAdded` starts a custom-tool diff consumer and updates the active item.
  - `ResponseEvent::ToolCallInputDelta` calls `consumer.consume_diff(turn_context, call_id, delta)` only for the active call id.
  - `ResponseEvent::OutputItemDone` clears active item/diff-consumer state before completed item handling.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - `UserTurnSamplingResult` now includes `stream_events` and `stream_event_dispatch_plans`.
  - `run_user_turn_sampling_from_session` collects sampler stream events for the initial turn and follow-ups.
  - Added a projection helper that turns normalized stream event dictionaries into `SamplingStreamEventDispatchPlan` values while maintaining active item and active tool diff-consumer state.
- `pycodex/core/stream_events_utils.py`
  - `sampling_stream_event_dispatch_plan` now forwards `turn_context` to `sampling_tool_call_input_delta_plan`, matching Rust's diff-consumer call shape.
- `tests/test_core_turn_runtime.py`
  - Added coverage for custom-tool stream events flowing through runtime dispatch projection and into a diff consumer with the current turn context.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events`
  - 1 test passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler`
  - 182 tests passed.

## 2026-06-01 Runtime StreamEvent Apply Projection

### Scope

- Continued from runtime stream-event dispatch projection into the existing apply-plan/state layer.
- The Python turn runtime now produces both dispatch plans and apply plans for sampler stream events, plus a runtime state summary that mirrors the already-ported websocket/runtime planning state.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
  - `class:codex-rs/codex-api/src/common.rs#ResponseEvent:72`
- Rust source confirmed:
  - `OutputItemDone` for tool-call items contributes to `needs_follow_up` via completed item handling.
  - `Completed` returns the accumulated `needs_follow_up` state and response id.
  - Tool input deltas are applied through the active diff consumer and can emit stream events before final tool execution.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - `UserTurnSamplingResult` now includes `stream_event_apply_plans` and `stream_runtime_state_summary`.
  - Added an apply projection that converts dispatch plans into `SamplingStreamEventApplyPlan` values and applies them through `SamplingRequestRuntimeHookAdapter`.
  - Tool-call `OutputItemDone` stream events now mark projected stream state as needing follow-up, matching Rust's accumulated turn state.
- `tests/test_core_turn_runtime.py`
  - Expanded stream-event runtime coverage to assert apply plans, completed response id, projected `needs_follow_up`, and emitted tool-input delta state.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events`
  - 1 test passed.
- Attempted `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_client tests.test_core_http_transport tests.test_core_turn_sampler`
  - Blocked for `tests.test_core_client` because `pytest` is not installed in this environment; the other unittest modules loaded and ran before the import error.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler`
  - 182 tests passed.

## 2026-06-01 Exec JSON Stream Delta Boundary

### Scope

- Checked whether the newly preserved runtime `stream_events` should be replayed through local `exec --json` output.
- Kept local exec output aligned with Rust's exec JSONL surface: completed thread items and turn status are emitted, while low-level stream delta events remain an internal runtime/app-server concern.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/exec/src/event_processor_with_jsonl_output.rs#EventProcessorWithJsonOutput:58`
  - `class:codex-rs/exec/src/event_processor_with_human_output.rs#EventProcessorWithHumanOutput:23`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `class:codex-rs/protocol/src/protocol.rs#ReasoningContentDeltaEvent:1743`
  - `class:codex-rs/protocol/src/protocol.rs#AgentReasoningSectionBreakEvent:2202`
- Rust source confirmed:
  - `try_run_sampling_request` emits streaming deltas as protocol `EventMsg` values while consuming the model stream.
  - Rust exec JSONL maps `ServerNotification::ItemStarted`, `ItemCompleted`, plan updates, metadata, token usage, and final turn status into `exec_events::ThreadEvent`.
  - Rust exec JSONL does not expose `AgentMessageContentDelta`, `ReasoningContentDelta`, `ReasoningRawContentDelta`, or `AgentReasoningSectionBreak` as JSONL `ThreadEvent` records.
  - Rust human exec output renders completed reasoning and final messages, not raw stream deltas.

### Python Changes

- `tests/test_exec_local_runtime.py`
  - Added coverage that `emit_local_http_exec_result(JsonEventProcessor(), ...)` ignores internal `UserTurnSamplingResult.stream_events` and emits only `turn.started`, completed items, and `turn.completed`.

### Deferred

- App-server/websocket event replay can consume the already-preserved runtime stream event application state later.
- Local exec JSON output should not grow delta event records unless Rust's `exec_events::ThreadEvent` surface changes upstream.

## 2026-06-01 Runtime Reasoning Delta Protocol IDs

### Scope

- Continued the stream-event runtime slice by making projected reasoning stream events protocol-shaped, not just summary-shaped.
- Focused on the Rust `try_run_sampling_request` branches that send reasoning summary/raw deltas as `EventMsg` values while preserving the local exec JSON boundary documented above.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `class:codex-rs/protocol/src/protocol.rs#ReasoningContentDeltaEvent:1743`
  - `class:codex-rs/protocol/src/protocol.rs#ReasoningRawContentDeltaEvent:1760`
  - `class:codex-rs/protocol/src/protocol.rs#AgentReasoningSectionBreakEvent:2202`
- Rust source confirmed:
  - `ResponseEvent::ReasoningSummaryDelta` sends `EventMsg::ReasoningContentDelta` with `thread_id`, `turn_id`, `item_id`, `delta`, and `summary_index`.
  - `ResponseEvent::ReasoningContentDelta` sends `EventMsg::ReasoningRawContentDelta` with `thread_id`, `turn_id`, `item_id`, `delta`, and `content_index`.
  - `ResponseEvent::ReasoningSummaryPartAdded` sends `EventMsg::AgentReasoningSectionBreak` with `item_id` and `summary_index`.

### Python Changes

- `pycodex/core/stream_events_utils.py`
  - `SamplingReasoningDeltaPlan` now carries `thread_id` and `turn_id`.
  - Reasoning summary/raw delta apply plans now emit protocol-parseable event dictionaries including those ids.
  - `sampling_stream_event_dispatch_plan` accepts `thread_id` and `turn_id` and forwards them into reasoning delta plans.
- `pycodex/core/turn_runtime.py`
  - Runtime stream-event projection now passes the `ModelClient` thread id and turn context id into dispatch planning.
- `tests/test_core_stream_events_utils.py`
  - Updated reasoning delta expectations and added explicit id-bearing event coverage.
- `tests/test_core_turn_runtime.py`
  - Added end-to-end runtime projection coverage proving emitted reasoning events can round-trip through `EventMsg.from_mapping`.

### Validation

- `python -m unittest tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_reasoning_delta_apply_plan_emits_reasoning_events tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_stream_event_dispatch_plan_routes_core_stream_events`
  - 2 tests passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_reasoning_stream_events_with_protocol_ids tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events`
  - 2 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 278 tests passed.

## 2026-06-01 Runtime Stream Event Session Emission

### Scope

- Continued the runtime stream-event slice from protocol-shaped event projection into actual session event emission.
- This closes the gap where Python preserved emitted stream events only in `stream_runtime_state_summary`, while Rust sends them through `sess.send_event(...)` during stream handling.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/session/mod.rs#send_event:1595`
  - `class:codex-rs/protocol/src/protocol.rs#AgentMessageContentDeltaEvent:1721`
  - `class:codex-rs/protocol/src/protocol.rs#ReasoningContentDeltaEvent:1743`
  - `class:codex-rs/protocol/src/protocol.rs#AgentReasoningSectionBreakEvent:2202`
- Rust source confirmed:
  - Tool input delta events from diff consumers are immediately sent with `sess.send_event`.
  - Reasoning summary/raw deltas and reasoning section breaks are immediately sent with `sess.send_event`.
  - `Session::send_event` persists/sends the primary event and then optionally sends legacy events.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added `_emit_stream_runtime_events` to send newly projected stream events through `sess.send_event(...)` after each sampler result is applied.
  - Tracks an emission cursor so follow-up sampling sends only newly produced stream events.
  - `UserTurnSamplingResult.session_events` now includes those emitted stream events when the session records them.
- `tests/test_core_turn_runtime.py`
  - Test session now records `send_event` calls.
  - Stream projection tests assert custom tool deltas and reasoning delta events are emitted into the session event stream.
- `tests/test_exec_local_runtime.py`
  - Extended the local exec JSON boundary test to include stream delta events in `session_events`, confirming local JSON output still does not replay those internal stream deltas.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_reasoning_stream_events_with_protocol_ids tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_json_output_does_not_replay_stream_deltas`
  - 1 test passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 278 tests passed.

## 2026-06-01 Runtime Assistant Text Delta Session Emission

### Scope

- Continued the stream-event session emission slice for assistant message output deltas.
- Python already parsed assistant text deltas into `assistant_text_deltas`; this change turns visible assistant text deltas into protocol-shaped `agent_message_content_delta` events and sends them through the same session event path as reasoning/tool stream events.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#emit_streamed_assistant_text_delta:1451`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `class:codex-rs/core/src/session/turn.rs#AssistantMessageStreamParsers:1168`
  - `class:codex-rs/protocol/src/protocol.rs#AgentMessageContentDeltaEvent:1721`
- Rust source confirmed:
  - `emit_streamed_assistant_text_delta` drops empty parsed deltas.
  - Citation extraction remains local and is not surfaced in protocol events.
  - Outside plan mode, non-empty `visible_text` becomes `EventMsg::AgentMessageContentDelta` with `thread_id`, `turn_id`, `item_id`, and `delta`.
  - Output text deltas for non-agent active items still use the raw `AgentMessageContentDelta` branch already modeled separately.

### Python Changes

- `pycodex/core/stream_events_utils.py`
  - `SamplingOutputTextDeltaPlan` and `SamplingStreamedAssistantTextDeltaPlan` now carry `thread_id` and `turn_id`.
  - `sampling_stream_event_dispatch_plan` forwards protocol ids into assistant text delta planning.
- `pycodex/core/client.py`
  - `_streamed_assistant_text_delta_record` now creates an `agent_message_content_delta` `event_to_emit` for non-empty visible assistant text.
  - Applying streamed assistant text delta plans appends that event to `emitted_stream_events`, so runtime session emission sends it.
- `tests/test_core_turn_runtime.py`
  - Added runtime coverage that assistant output text deltas are emitted as session `agent_message_content_delta` events with protocol ids.
- `tests/test_exec_local_runtime.py`
  - Extended the local exec JSON boundary test to include assistant text stream events in `session_events`, confirming local JSON output still does not replay stream deltas.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_assistant_text_stream_deltas tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_reasoning_stream_events_with_protocol_ids`
  - 2 tests passed.
- `python -m unittest tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_output_text_delta_apply_plan_streams_agent_message_delta tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_stream_event_dispatch_plan_routes_core_stream_events tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_stream_event_apply_plan_routes_done_and_completed`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_json_output_does_not_replay_stream_deltas`
  - 1 test passed.
- Attempted `python -m unittest tests.test_core_client tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - Blocked for `tests.test_core_client` because `pytest` is not installed in this environment; the remaining unittest modules ran.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 279 tests passed.

## 2026-06-01 Runtime Non-Agent Output Text Delta Emission

### Scope

- Closed the remaining `ResponseEvent::OutputTextDelta` parity gap for active items that are not assistant-message turn items.
- Python already recorded these deltas as raw content; this change mirrors Rust by emitting the raw delta as an `agent_message_content_delta` session event.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_non_tool_response_item:455`
  - `class:codex-rs/protocol/src/protocol.rs#AgentMessageContentDeltaEvent:1721`
- Rust source confirmed:
  - When `OutputTextDelta` arrives for a streamed active item:
    - `TurnItem::AgentMessage` uses `emit_streamed_assistant_text_delta`.
    - Any other active item sends `EventMsg::AgentMessageContentDelta` directly with the raw delta.
  - Non-streaming active items skip the delta entirely.

### Python Changes

- `pycodex/core/stream_events_utils.py`
  - `SamplingOutputTextDeltaApplyPlan` now carries `thread_id` and `turn_id`, preserving ids for raw non-agent delta application.
- `pycodex/core/client.py`
  - Raw `output_text_delta` application now records an `agent_message_content_delta` `event_to_emit` and appends it to `emitted_stream_events`.
- `tests/test_core_turn_runtime.py`
  - Added runtime coverage proving a reasoning active item receiving `output_text_delta` emits a session `agent_message_content_delta` with the raw delta.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_non_agent_output_text_deltas tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_assistant_text_stream_deltas`
  - 2 tests passed.
- `python -m unittest tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_output_text_delta_apply_plan_emits_raw_non_agent_delta tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_output_text_delta_apply_plan_streams_agent_message_delta`
  - 2 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 280 tests passed.

## 2026-06-01 Runtime Assistant Text Flush Emission

### Scope

- Continued the assistant text stream parity slice into the Rust flush paths:
  - `OutputItemDone` flushes buffered parser text for the completed active assistant item.
  - `response.completed` flushes all remaining buffered assistant parsers.
- Python already modeled these flush plans, but applying them did not emit session events. This change turns flushed visible text into `agent_message_content_delta` events in `emitted_stream_events`.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/session/turn.rs#AssistantMessageStreamParsers:1168`
  - `function:codex-rs/core/src/session/turn.rs#flush_assistant_text_segments_for_item:1486`
  - `function:codex-rs/core/src/session/turn.rs#flush_assistant_text_segments_all:1498`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
- Rust source confirmed:
  - `finish_item(item_id)` removes the parser and emits its final parsed visible text, if any.
  - `drain_finished()` flushes remaining parsers after the stream loop exits.
  - Both paths call `emit_streamed_assistant_text_delta`, which emits `AgentMessageContentDeltaEvent` outside plan mode for non-empty visible text.

### Python Changes

- `pycodex/core/stream_events_utils.py`
  - `SamplingOutputItemDoneTransitionPlan`, `SamplingCompletedEventPlan`, and `SamplingCompletedEventApplyPlan` now carry `thread_id` and `turn_id`.
  - Output-item-done and completed dispatch/apply planning now forwards those ids into assistant text flush plans.
- `pycodex/core/client.py`
  - Applying an `output_item_done` flush plan now records/emits an `agent_message_content_delta` event.
  - Applying a completed flush-all plan now records/emits `agent_message_content_delta` events for non-empty flushed assistant text.
- `tests/test_core_stream_events_utils.py`
  - Added apply-state coverage for both output-item-done flush and completed drain-all flush.

### Validation

- `python -m unittest tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_event_state_emits_output_done_flush_delta tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_event_state_emits_completed_flush_all_deltas tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_sampling_completed_event_apply_plan_flushes_and_returns_result`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_assistant_text_stream_deltas tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_non_agent_output_text_deltas`
  - 2 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 282 tests passed.

## 2026-06-01 Runtime Assistant Text Stream Parser

### Scope

- Replaced the Python runtime's no-op assistant stream parser shim with a lightweight stateful parser for the core streamed assistant text path.
- The parser now preserves the Rust behavior that matters for normal streaming:
  - citation tags can span `output_item.added` and `output_text_delta` boundaries;
  - citation payloads are extracted while hidden markup is omitted from visible deltas;
  - plan-mode `<proposed_plan>` blocks are split into normal/plan-start/plan-delta/plan-end segments.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/session/turn.rs#AssistantMessageStreamParsers:1168`
  - `function:codex-rs/core/src/session/turn.rs#seed_item_text:1190`
  - `function:codex-rs/core/src/session/turn.rs#parse_delta:1197`
  - `function:codex-rs/core/src/session/turn.rs#finish_item:1201`
  - `class:codex-rs/utils/stream-parser/src/assistant_text.rs#AssistantTextStreamParser:24`
  - `function:codex-rs/utils/stream-parser/src/citation.rs#strip_citations:69`
- Rust source confirmed:
  - `AssistantMessageStreamParsers` keeps one `AssistantTextStreamParser` per item id.
  - `seed_item_text`, `parse_delta`, `finish_item`, and `drain_finished` all share parser state.
  - `AssistantTextStreamParser` first strips/extracts citations, then applies proposed-plan parsing in plan mode.
  - Unterminated citation tags auto-close at finish; incomplete open-tag prefixes that are not full tags are flushed as visible text at finish.

### Python Changes

- `pycodex/core/stream_events_utils.py`
  - Added `AssistantMessageStreamParsers` with per-item state and stdlib-only citation/plan stream parsing.
  - `sampling_output_item_added_plan` and `sampling_output_text_delta_plan` can now seed/parse through the shared parser, while retaining stateless fallback behavior for isolated plan calls.
  - Apply plans also accept the parser so `output_item_done` and `completed` flushes operate on the same event sequence.
- `pycodex/core/turn_runtime.py`
  - Runtime stream dispatch/apply now use `AssistantMessageStreamParsers(plan_mode=False)` instead of the local no-op shim.
- `tests/test_core_stream_events_utils.py`
  - Added parser coverage for citation boundaries, partial-tag finish flushing, and plan block boundaries.
- `tests/test_core_turn_runtime.py`
  - Added runtime coverage proving citation tags split across `output_item_added` and delta do not leak hidden markup into emitted session deltas.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_parses_streamed_citations_across_boundaries tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_assistant_text_stream_deltas tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_assistant_message_stream_parsers_parse_citations_across_boundaries tests.test_core_stream_events_utils.CoreStreamEventsUtilsTests.test_assistant_message_stream_parsers_parse_plan_across_boundaries`
  - 4 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 286 tests passed.

## 2026-06-01 Runtime Plan-Mode Stream Event Projection

### Scope

- Connected the existing Python plan-mode stream planning helpers to the runtime stream projection path.
- This advances the Rust `ResponseEvent` stream parity for common plan-mode output:
  - assistant messages are deferred while the stream contains only `<proposed_plan>` content;
  - streamed proposed-plan segments emit `item_started` for the synthetic plan item and `plan_delta` updates;
  - finalized assistant output completes the synthetic plan item with extracted plan text.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/session/turn.rs#PlanModeStreamState:1145`
  - `function:codex-rs/core/src/session/turn.rs#handle_plan_segments:1388`
  - `function:codex-rs/core/src/session/turn.rs#maybe_complete_plan_item_from_message:1517`
  - `function:codex-rs/core/src/session/turn.rs#emit_agent_message_in_plan_mode:1546`
  - `function:codex-rs/core/src/session/turn.rs#handle_assistant_item_done_in_plan_mode:1610`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
- Rust source confirmed:
  - `PlanModeStreamState` is ephemeral per streamed response and tracks pending assistant messages, started assistant item ids, leading whitespace, and one synthetic `{turn_id}-plan` item.
  - Normal assistant text in plan mode starts the deferred assistant item only when non-plan text appears.
  - Proposed-plan stream content starts the plan item and emits plan deltas; final assistant output completes the plan item after extracting and citation-stripping the plan block.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Runtime stream dispatch/apply now detects plan mode from `turn_context.collaboration_mode`.
  - Runtime stream application passes current plan state into `sampling_stream_event_apply_plan`, including pending assistant items, started item ids, leading whitespace, and `{turn_id}-plan`.
- `pycodex/core/client.py`
  - `SamplingRuntimeEventApplicationState` now carries plan-mode ephemeral stream state.
  - Applying streamed assistant text plans now projects plan segment actions into protocol event dictionaries (`item_started`, `plan_delta`, `item_completed`) and keeps state in sync.
  - Applying plan-mode assistant completion plans now emits final plan item completion and handles deferred/fallback assistant message lifecycle actions.
- `tests/test_core_turn_runtime.py`
  - Added runtime coverage for a plan-mode assistant response whose streamed `<proposed_plan>` block emits plan lifecycle events and completes with extracted final plan text.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_routes_plan_mode_segments_to_plan_events tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_parses_streamed_citations_across_boundaries tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_emits_assistant_text_stream_deltas tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_reasoning_stream_events_with_protocol_ids`
  - 4 tests passed.
- `python -m py_compile pycodex/core/client.py pycodex/core/turn_runtime.py pycodex/core/stream_events_utils.py`
  - Passed.
- `python -m unittest tests.test_core_client tests.test_core_turn_runtime tests.test_core_stream_events_utils`
  - `tests.test_core_client` import is blocked by missing `pytest`; the other 148 unittest tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 287 tests passed.

## 2026-06-01 Runtime Plan-Mode Final Completion IDs

### Scope

- Tightened the plan-mode runtime projection for responses that do not stream any plan deltas and only expose the `<proposed_plan>` block in the final assistant item.
- This preserves Rust's behavior that `maybe_complete_plan_item_from_message` can start and complete the synthetic plan item during `OutputItemDone`, with protocol ids coming from the active session/turn rather than from prior emitted stream events.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/session/turn.rs#ProposedPlanItemState:1137`
  - `function:codex-rs/core/src/session/turn.rs#maybe_complete_plan_item_from_message:1517`
  - `function:codex-rs/core/src/session/turn.rs#handle_assistant_item_done_in_plan_mode:1610`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
- Rust source confirmed:
  - `maybe_complete_plan_item_from_message` extracts proposed-plan text from the finalized assistant item.
  - If the plan item has not started yet, it emits the start before completing it.
  - Both lifecycle events use the session conversation id and current turn id.

### Python Changes

- `pycodex/core/client.py`
  - Plan-mode assistant completion application now receives `thread_id` and `turn_id` from `SamplingOutputItemDoneTransitionPlan`.
  - Event-id fallback from previously emitted stream events remains only a fallback, not the primary source.
- `tests/test_core_turn_runtime.py`
  - Added coverage for final-only plan completion with no `output_text_delta` plan events, asserting valid thread/turn ids and final plan text.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_completes_plan_mode_item_without_plan_deltas tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_routes_plan_mode_segments_to_plan_events`
  - 2 tests passed.
- `python -m py_compile pycodex/core/client.py pycodex/core/turn_runtime.py pycodex/core/stream_events_utils.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 288 tests passed.

## 2026-06-01 Runtime Stream Metadata Session Side Effects

### Scope

- Applied streamed response metadata to the Python session runtime after stream-event projection.
- This advances the Rust `try_run_sampling_request` tail behavior for common stream events:
  - `ServerReasoningIncluded` updates the session flag;
  - `ModelsEtag` refreshes the session model etag;
  - `RateLimits` records rate-limit state and marks token counts for emission;
  - `Completed` token usage records usage and emits a token-count event.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `class:codex-rs/codex-api/src/common.rs#ResponseEvent:72`
- Rust source confirmed:
  - Stream metadata events mutate session state inside the sampling loop rather than only appearing in raw output.
  - `Completed { token_usage, end_turn }` records token usage, can trigger token-count emission, and controls follow-up turns when `end_turn` is false.
  - Rate-limit stream events also trigger token-count emission after the response is processed.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Runtime stream event payload extraction now passes metadata event payloads in the shape expected by the stream planner.
  - Added stream runtime session side-effect application for server reasoning inclusion, model etags, rate limits, and completed token usage.
  - Side effects skip duplication when equivalent raw-result metadata is already present.
- `tests/test_core_turn_runtime.py`
  - Extended the session test double with stream-side-effect sinks.
  - Added coverage for streamed `completed.token_usage` and metadata events updating the session runtime.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_stream_completed_usage_to_session tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_stream_metadata_to_session`
  - 2 tests passed.
- `python -m py_compile pycodex/core/turn_runtime.py pycodex/core/client.py pycodex/core/stream_events_utils.py`
  - Passed.

## 2026-06-01 Local HTTP Exec Streamed Final Message

### Scope

- Connected `UserTurnSamplingResult.last_agent_message` to local HTTP exec final-output rendering.
- This preserves Rust exec behavior where a completed turn with empty turn items keeps the already-streamed final message, while completed turn items still take precedence when present.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#final_message_from_turn_items:484`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#print_final_output:376`
  - `function:codex-rs/exec/src/event_processor.rs#handle_last_message:31`
- Rust source/tests confirmed:
  - `TurnCompleted` overwrites the cached final message only when `final_message_from_turn_items` finds one.
  - If completed turn items are empty, the previously streamed final message is preserved and emitted on shutdown.
  - Last-message file handling receives that preserved final message.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added `final_text_from_local_http_exec_result`, which prefers visible response-item text and falls back to `result.last_agent_message`.
  - Local HTTP human and JSON exec rendering now use this helper.
- `tests/test_exec_local_runtime.py`
  - Added coverage for stream-only final messages without response items.
  - Added coverage that response items still override a stale streamed final message.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_uses_streamed_last_agent_message_without_response_items tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_prefers_response_items_over_streamed_last_agent_message tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_prefers_env_key`
  - 3 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py pycodex/core/turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 97 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_exec_event_processor`
  - 118 tests passed.

## 2026-06-01 Local HTTP Exec Follow-Up Final Message Merge

### Scope

- Preserved `last_agent_message` when local HTTP exec merges shell-tool follow-up sampling results.
- This keeps stream-only final answers available after the shell-tool loop combines the initial tool-call response, local tool output, and follow-up response.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#print_final_output:376`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#final_message_from_turn_items:484`
- Rust source/tests confirmed:
  - `run_turn` carries the accumulated `last_agent_message` through model/tool follow-ups.
  - Exec rendering preserves a previously streamed final message when completed turn items are empty.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_merge_local_http_sampling_result` now carries `followup.last_agent_message`, falling back to the previous result when the follow-up lacks one.
- `tests/test_exec_local_runtime.py`
  - Added coverage for local HTTP shell-tool result merging preserving a streamed follow-up final answer.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_uses_streamed_last_agent_message_without_response_items tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_prefers_response_items_over_streamed_last_agent_message tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_merge_preserves_followup_streamed_last_agent_message`
  - 3 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py pycodex/core/turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 98 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_exec_event_processor`
  - 118 tests passed.

## 2026-06-01 Runtime Last Agent Message Result

### Scope

- Added `last_agent_message` to the Python sampling result so the runtime exposes the same core value Rust returns from `run_turn`.
- This prepares the common final-answer path for stop hooks, after-agent hooks, and exec final-output handling without requiring callers to rescan raw response state.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/session/turn.rs#handle_assistant_item_done_in_plan_mode:1610`
- Rust source confirmed:
  - `SamplingRequestResult` carries `last_agent_message`.
  - Non-empty finalized assistant messages update `last_agent_message`.
  - `ResponseEvent::Completed` returns the accumulated `last_agent_message`, and `run_turn` returns it when no follow-up remains.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - `UserTurnSamplingResult` now includes `last_agent_message`.
  - The result is derived first from stream runtime state, then stream apply plans, then streamed `output_item_done` items, and finally from recorded response items.
- `tests/test_core_turn_runtime.py`
  - Added coverage for ordinary response-item final messages.
  - Added coverage for stream-only finalized assistant messages with no `response_items` payload.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_sampler_response_items tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_returns_streamed_last_agent_message tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler`
  - 197 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 95 tests passed.
- `python -m py_compile pycodex/core/turn_runtime.py pycodex/core/client.py pycodex/core/stream_events_utils.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 290 tests passed.

## 2026-06-01 Request Permissions Session Grants for Patch Tools

### Scope

- Locked down that session-scoped `request_permissions` grants are reused by later user turns for `apply_patch`, not only shell calls.
- This preserves the Rust user-visible behavior where an approved session filesystem grant can preapprove a later patch write under the granted root.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/mod.rs#record_granted_request_permissions_for_turn:2374`
  - `function:codex-rs/core/src/session/mod.rs#run_exec_approval_request:2472`
  - `function:codex-rs/core/src/tools/handlers/request_permissions.rs#handle_request_permissions:48`
- Rust source/tests confirmed:
  - `PermissionGrantScope::Session` records grants on session state instead of turn state.
  - Later permission checks merge existing grants before deciding whether a tool needs approval.
  - The Rust suite covers approved folder write permissions unblocking later `apply_patch`.

### Python Changes

- `tests/test_exec_local_runtime.py`
  - Added coverage for `request_permissions(scope=session)` in one user turn preapproving `apply_patch` in a later user turn.
  - The existing implementation path already passed this through the shared effective-grant merge, so this is a regression lock rather than a new runtime behavior change.

### Validation

- `python -m py_compile pycodex\exec\session.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_session_grant_applies_to_later_apply_patch`
  - 1 test passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 135 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 554 tests passed, 1 skipped.

## 2026-06-01 Request Permissions Grant Propagation

### Scope

- Extended the local HTTP shell-tool loop so a successful `request_permissions` response can authorize later `with_additional_permissions` shell calls in the same automatic tool loop.
- This keeps the model-visible `function_call_output` shape unchanged while preserving an internal parsed `RequestPermissionsResponse` for runtime policy checks.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/tools/handlers/request_permissions.rs#handle_request_permissions:17`
  - `function:codex-rs/core/src/session/mod.rs#request_permissions:2336`
  - `function:codex-rs/core/src/session/mod.rs#record_granted_request_permissions:2397`
- Rust source confirmed:
  - `request_permissions` returns serialized `RequestPermissionsResponse` to the model on success.
  - The session records granted request permissions so subsequent tool execution can compare requested additional permissions against the current grant set.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `shell_tool_outputs_from_local_http_exec_result` accepts a `granted_permissions` profile for local HTTP shell calls.
  - `request_permissions` tool outputs now retain an internal parsed `RequestPermissionsResponse`.
  - `run_exec_user_turn_with_shell_tools_http_sampling` merges granted permissions between tool rounds.
  - `with_additional_permissions` shell calls now reuse `permissions_are_preapproved` before falling back to the existing unsupported-permission error.
- `tests/test_exec_local_runtime.py`
  - Added direct helper coverage for granted additional permissions allowing shell execution.
  - Added end-to-end loop coverage for `request_permissions -> shell(with_additional_permissions) -> final answer`.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_runs_with_granted_additional_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_applies_granted_request_permissions`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 127 tests passed.

## 2026-06-01 Request Permissions Apply Patch Grants

### Scope

- Extended the local HTTP automatic tool loop so `request_permissions` file-system grants can authorize a later `apply_patch` custom tool call in the same turn.
- This follows the Rust core behavior where granted request permissions are recorded on turn/session state and can unblock subsequent shell-like and patch tools without a second approval prompt.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/mod.rs#record_granted_request_permissions_for_turn:2374`
  - `function:codex-rs/core/tests/suite/request_permissions_tool.rs#approved_folder_write_request_permissions_unblocks_later_apply_patch:333`
  - `function:codex-rs/core/tests/suite/request_permissions_tool.rs#apply_patch_after_request_permissions:343`
- Rust source confirmed:
  - A turn-scoped file-system permission grant can unblock a later `apply_patch` call.
  - Without a grant, `apply_patch` under `on-request` should still require approval.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added an apply-patch preapproval check that maps verified patch protocol changes to write targets and verifies them against granted file-system permissions.
  - The existing `approval_required` path is preserved when no grant covers all patch write targets.
- `tests/test_exec_local_runtime.py`
  - Added end-to-end local HTTP coverage for `request_permissions -> apply_patch -> final answer`.
  - Kept the existing approval-failure coverage paired with the new grant path.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_applies_granted_permissions_to_apply_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_apply_patch_approval_failure`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 128 tests passed.

## 2026-06-01 Request Permissions Approval Policy Edges

### Scope

- Matched two Rust approval-policy edges in the local HTTP request-permissions path:
  - `approval_policy = never` auto-denies `request_permissions` with an empty successful response instead of waiting for a client callback.
  - `approval_policy = on-request` can still execute a later shell call automatically when its explicit `additional_permissions` are already covered by a prior grant.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/mod.rs#request_permissions_for_cwd:2082`
  - `function:codex-rs/core/tests/suite/request_permissions.rs#with_additional_permissions_requires_approval_under_on_request:327`
  - `function:codex-rs/core/tests/suite/request_permissions.rs#request_permissions_preapprove_explicit_exec_permissions_outside_on_request:1161`
- Rust source confirmed:
  - `AskForApproval::Never` returns an empty `RequestPermissionsResponse` immediately.
  - Under `on-request`, explicit additional permissions normally require approval, but a previous matching request-permissions grant can preapprove execution.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added local request-permissions auto-denial for `never` and granular configs that disallow request-permissions.
  - Moved shell permission validation ahead of approval-required output so already-granted explicit additional permissions can run under `on-request`.
- `tests/test_exec_local_runtime.py`
  - Added coverage for `never` returning empty request-permissions success without invoking the callback.
  - Adjusted cancellation tests to use `on-request`, where Rust waits for a user/client response.
  - Restored unrelated shell-output tests to `never` so they continue exercising automatic execution.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_uses_rust_cancel_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_auto_denies_when_approval_never tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_serializes_grant_response tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_runs_with_granted_additional_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_failure tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_success tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_applies_granted_request_permissions`
  - 7 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 129 tests passed.

## 2026-06-01 Relative Additional Permissions Workdir

### Scope

- Matched Rust behavior where relative `additional_permissions` paths on shell-like tool calls resolve against the tool call's `workdir`, not the session cwd.
- This affects both approval-required output and preapproval checks against previously granted permissions.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/tests/suite/request_permissions.rs#relative_additional_permissions_resolve_against_tool_workdir:511`
  - `function:codex-rs/core/src/tools/handlers/shell.rs#run_exec_like:60`
  - `function:codex-rs/core/src/session/mod.rs#request_permissions_for_cwd:2082`
- Rust source confirmed:
  - A shell command with `workdir = "nested"` and `additional_permissions.file_system.write = ["."]` asks for write permission to the nested directory.
  - The same workdir-relative profile can be compared against granted permissions for preapproval.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Shell additional-permission preapproval now uses `invocation.workdir or config.cwd` as the permission resolution cwd.
  - Approval-required output materializes relative file-system permission paths against the shell workdir before serializing the permissions profile.
- `tests/test_exec_local_runtime.py`
  - Added coverage for approval output resolving relative additional permissions against workdir.
  - Added coverage for a granted absolute workdir permission preapproving a shell call whose requested profile uses `write: ["."]`.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_resolves_relative_additional_permissions_against_workdir tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_runs_with_granted_relative_workdir_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_runs_with_granted_additional_permissions`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 131 tests passed.

## 2026-06-01 Request Permissions Grant Lifetimes

### Scope

- Added local HTTP bridge parity for request-permissions grant lifetimes:
  - turn-scoped grants apply only inside the current automatic tool loop;
  - session-scoped grants are retained on `ExecSessionConfig` and can preapprove later local HTTP user turns that reuse the same config.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/mod.rs#record_granted_request_permissions_for_turn:2374`
  - `function:codex-rs/core/tests/suite/request_permissions.rs#request_permissions_grants_do_not_carry_across_turns:1680`
  - `function:codex-rs/core/tests/suite/request_permissions.rs#request_permissions_session_grants_carry_across_turns:1796`
- Rust source confirmed:
  - `PermissionGrantScope::Turn` records permissions on turn state only.
  - `PermissionGrantScope::Session` records permissions on session state and survives later turns.

### Python Changes

- `pycodex/exec/session.py`
  - Added a lightweight `granted_session_permissions` field to `ExecSessionConfig` for local HTTP bridge session-scope grants.
- `pycodex/exec/local_runtime.py`
  - Split local HTTP grant accumulation into turn-scoped and session-scoped paths.
  - Merges stored session grants with current-turn grants when evaluating shell/apply-patch preapproval.
- `tests/test_exec_local_runtime.py`
  - Added coverage showing session grants carry across two local HTTP user turns using the same config.
  - Added coverage showing turn grants do not carry across user turns.

### Validation

- `python -m py_compile pycodex/exec/session.py pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_session_grant_carries_across_user_turns tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_turn_grant_does_not_carry_across_user_turns tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_applies_granted_request_permissions`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 133 tests passed.

## 2026-06-01 Partial Grants Approval Merge

### Scope

- Matched the Rust request-permissions edge where a partial grant does not preapprove a later broader permission request, but the resulting approval request carries the merged granted + newly requested permissions.
- This keeps local HTTP from widening execution silently while preserving enough permission context for the user-facing approval output.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/tests/suite/request_permissions.rs#partial_request_permissions_grants_do_not_preapprove_new_permissions:1513`
  - `function:codex-rs/core/src/session/mod.rs#record_granted_request_permissions_for_turn:2374`
- Rust source confirmed:
  - A grant for one directory does not preapprove a later command requesting a different directory.
  - The subsequent approval request includes the merged first granted directory and second requested directory.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Approval-required output for shell calls now merges any existing granted permissions with the pending `additional_permissions` profile before rendering.
  - Preapproval behavior is unchanged: only a grant that fully covers the requested profile allows execution.
- `tests/test_exec_local_runtime.py`
  - Added coverage that partial grants do not execute the command and that approval output includes both the previous grant and the new requested path.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_approval_merges_partial_grant_with_new_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_runs_with_granted_additional_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_rejects_additional_permissions_before_auto_execution`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 134 tests passed.

## 2026-06-01 Local Apply Patch Follow-Up Request Shape

### Scope

- Tightened the local HTTP `apply_patch` follow-up path on the common exec tool loop.
- The new coverage verifies the actual second Responses request body after Python executes a model-emitted `apply_patch` custom tool call.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`
  - `codex-rs/protocol/src/models.rs#ResponseInputItem::CustomToolCallOutput`
- Rust source confirmed:
  - `apply_patch` returns its summary text through `ApplyPatchToolOutput::from_text`.
  - `ResponseInputItem::CustomToolCallOutput.name` is optional and omitted when `None`.

### Python Changes

- `tests/test_exec_local_runtime.py`
  - Added a local HTTP follow-up request test for `apply_patch`.
  - The test runs the first model turn, applies the patch locally, sends tool output back through `run_exec_tool_output_http_sampling`, and captures the follow-up request JSON.
  - It asserts the `custom_tool_call_output` uses `call_id`, `success`, and summary `output`, and does not serialize a `name` field.

### Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_followup_request_omits_custom_output_name tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_tool_output_followup_request`
  - 3 tests passed.

## 2026-06-01 Local Apply Patch Structured Changes

### Scope

- Carried verified `apply_patch` file changes through the local HTTP tool-output path for event projection.
- This keeps the model-visible tool output unchanged while preserving Rust-like internal `FileChange` metadata for the exec timeline.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`
  - `codex-rs/core/src/apply_patch.rs#convert_apply_patch_to_protocol`
  - `codex-rs/protocol/src/items.rs#FileChangeItem`
  - `codex-rs/exec/src/event_processor_with_jsonl_output.rs`
- Rust source confirmed:
  - Verified patch actions are converted to protocol `FileChange` values before `ToolEmitter::apply_patch` begins.
  - The same structured changes feed both begin and finish file-change events.
  - Exec JSON ultimately projects file changes to path/kind/status, while richer protocol changes remain available before that projection.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added `raw_tool_output_items` to `UserTurnSamplingResult` so local exec can keep non-prompt-visible tool metadata next to prompt-visible `ResponseItem`s.
- `pycodex/exec/local_runtime.py`
  - Local `apply_patch` execution now converts verified actions with `convert_apply_patch_to_protocol`.
  - Structured changes are relativized to the exec cwd and stored under `internal_output["changes"]`.
  - Local HTTP result merging preserves raw tool outputs, and timeline projection prefers those structured changes for `file_change` begin/end items.
- `tests/test_exec_local_runtime.py`
  - Tightened apply-patch coverage to assert internal structured changes include update diffs and move targets while the model follow-up request remains standard Responses JSON.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_updates_deletes_and_moves_files tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_requires_approval_before_write tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_followup_request_omits_custom_output_name`
  - 4 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime`
  - 166 tests passed.

## 2026-06-01 Apply Patch Tool Loop Coverage

### Scope

- Added an end-to-end local HTTP shell-tools loop check for model-emitted `apply_patch`.
- This verifies the automatic `run_exec_user_turn_with_shell_tools_http_sampling` path, not only manually assembled tool-output results.

### Python Changes

- `tests/test_exec_local_runtime.py`
  - Added coverage where the first model response emits an `apply_patch` custom tool call, Python applies the file edit, and the second model request receives a standard `custom_tool_call_output`.
  - Asserted the merged result retains `raw_tool_output_items` with structured update diffs for exec timeline projection.
  - Asserted the emitted timeline contains `file_change` begin/end items with `in_progress` then `completed` statuses.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_apply_patch_followup_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_followup_request_omits_custom_output_name tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_updates_deletes_and_moves_files`
  - 4 tests passed.

## 2026-06-01 Apply Patch Tool Loop Approval Failure

### Scope

- Added local HTTP shell-tools loop coverage for approval-blocked `apply_patch` calls.
- This protects the core safety path where Python must not write files, but still returns a model-visible failed tool output so the turn can complete with a final answer.

### Python Changes

- `tests/test_exec_local_runtime.py`
  - Added coverage for `run_exec_user_turn_with_shell_tools_http_sampling` with `approval_policy=on-request`.
  - Asserted the target file is not created.
  - Asserted the second Responses request receives `custom_tool_call_output` with `success=false` and `approval_required`.
  - Asserted the merged result keeps structured patch changes and projects `file_change` timeline items as `in_progress` then `failed`.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_apply_patch_approval_failure tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_apply_patch_followup_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_requires_approval_before_write`
  - 3 tests passed.

## 2026-06-01 Request Permissions Local HTTP Cancel Shape

### Scope

- Replaced the Python-only local HTTP `request_permissions` unavailable output with the Rust handler's model-visible cancellation wording.
- This keeps the non-interactive exec bridge honest: without an approval callback it does not grant permissions, but it now parses and fails like the core handler boundary.
- Added a callback-backed success path so tests and embedders can exercise the Rust-shaped successful `RequestPermissionsResponse` tool output in the local HTTP exec loop.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/core/src/tools/handlers/request_permissions.rs`
  - `codex-rs/protocol/src/request_permissions.rs`
- Rust source confirmed:
  - The handler parses and normalizes `RequestPermissionsArgs`.
  - Empty permission requests are rejected before prompting.
  - If the approval response is absent/cancelled, the model-visible message is `request_permissions was cancelled before receiving a response`.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Local HTTP `request_permissions` now reuses `RequestPermissionsHandler` parsing/error behavior.
  - In local HTTP exec mode, the no-callback path returns the Rust cancellation message with `success=false`.
  - When `ExecSessionConfig.request_permissions_callback` is provided, the callback response is serialized as a successful `function_call_output`.
- `pycodex/exec/session.py`
  - Added `request_permissions_callback` to `ExecSessionConfig` for local/core runtime tests and non-interactive embedders.
- `pycodex/core/tool_router.py`
  - `ToolRouter.from_parts(registry)` now accepts registry-only construction and derives visible direct tool specs from the registry.
- `tests/test_exec_local_runtime.py`
  - Added helper-level coverage for the Rust cancellation message.
  - Added helper-level coverage for empty permission requests and malformed JSON arguments, preserving Rust's model-visible handler errors.
  - Added helper-level and automatic tool-loop coverage for successful callback-backed permission responses.
  - Added automatic shell-tools loop coverage that feeds the failed `request_permissions` output back to the model and preserves the standard `function_call_output` request shape.

### Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_uses_rust_cancel_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_failure tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_apply_patch_approval_failure`
  - 3 tests passed.
- `python -m py_compile pycodex\core\tool_router.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py tests\test_core_request_permissions_handler.py`
  - Passed.
- `python -m unittest tests.test_core_request_permissions_handler tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_uses_rust_cancel_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_failure`
  - 19 tests passed, 1 skipped.
- `python -m py_compile tests\test_exec_local_runtime.py pycodex\exec\local_runtime.py pycodex\core\tool_router.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_uses_rust_cancel_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_rejects_empty_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_rejects_bad_arguments tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_failure`
  - 4 tests passed.
- `python -m py_compile pycodex\exec\session.py pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_serializes_grant_response tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_success tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_uses_rust_cancel_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_request_permissions_failure tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_rejects_empty_permissions tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_request_permissions_tool_output_helper_rejects_bad_arguments`
  - 6 tests passed.

## 2026-06-01 Local Apply Patch Timeline Status

### Scope

- Locked down local HTTP `apply_patch` user-visible status and event-shape mapping on the core tool-dispatch path.
- This preserves the Rust behavior where patch execution success/failure is reflected as completed/failed patch status for the user-facing event stream.
- The Python local HTTP path now emits `file_change` timeline/JSONL items for `apply_patch` begin/end rather than generic `mcp_tool_call` items.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/core/src/tools/runtimes/apply_patch.rs`
  - `codex-rs/core/src/tools/events.rs`
- Rust source confirmed:
  - `ToolEventStage::Begin` for `ApplyPatch` emits a `TurnItem::FileChange(FileChangeItem { status: None, ... })`.
  - `ApplyPatchRuntime::run` maps patch application failure to exit code `1` and success to exit code `0`.
  - Tool events map `ApplyPatch` success/failure output to `PatchApplyStatus::Completed` when exit code is `0`, otherwise `PatchApplyStatus::Failed`.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `tool_timeline_items_from_local_http_exec_result` now projects `apply_patch` calls and outputs to `file_change` items.
  - Added a small parser-backed converter from Responses `apply_patch` tool input to protocol `FileChange` entries for the exec JSONL payload.
  - Local HTTP patch execution now reuses core `apply_patch_action_to_disk`, so model-visible success output uses the same `Success. Updated the following files:` summary as the core runtime path.
  - Local HTTP `apply_patch` custom tool outputs no longer set a `name`, matching Rust `ResponseInputItem::CustomToolCallOutput { name: None, ... }`.
- `tests/test_exec_local_runtime.py`
  - Added focused coverage that successful local HTTP `apply_patch` outputs appear as `file_change` timeline/JSONL events with `completed` status.
  - Added coverage that update/delete/move patches expose their file-change kinds in the `file_change` event payload.
  - Added focused coverage that approval-blocked local HTTP `apply_patch` outputs appear as `file_change` timeline/JSONL events with `failed` status and do not write files.
  - Updated the success-output assertion to cover the Rust-shaped patch summary instead of the previous Python-only `apply_patch succeeded` string.
  - Updated custom output assertions so `apply_patch` follow-up items carry `name=None`, while timeline rendering still derives the tool name from the original call.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_updates_deletes_and_moves_files tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_requires_approval_before_write`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_updates_deletes_and_moves_files tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_requires_approval_before_write tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer`
  - 4 tests passed.
- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 327 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 136 tests passed.

## 2026-06-01 Local Exec Direct Shell Output Formatting

### Scope

- Tightened the local HTTP `exec_command` direct runner path so model-visible command output uses the Rust unified exec text shape instead of a Python-only `exit_code/stdout/stderr` debug format.
- This keeps the common `exec -> tool call -> tool output -> follow-up request` path closer to upstream behavior before expanding deeper sandbox/runtime parity.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `file:codex-rs/core/src/tools/runtimes/shell.rs`
  - `function:codex-rs/core/src/tools/context.rs#response_text`
- Rust source confirmed:
  - Unified exec model responses include `Wall time`, optional `Process exited with code`, optional `Original token count`, and `Output`.
  - Shell runtime participates in the same tool-output-follow-up loop from `run_turn`.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_run_shell_tool_command_result()` now measures wall time and renders direct command output through the existing local unified-exec formatter.
  - Timeout output now reports the Rust-style timeout line inside the unified output body with exit code `124`.
  - Added a small coercion helper for timeout stdout/stderr values that may be bytes.
- `tests/test_exec_local_runtime.py`
  - Updated direct shell execution, failure, truncation, and follow-up request assertions to expect the unified exec output shape.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_execution_helper tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_execution_failure_marks_unsuccessful tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 129 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 320 tests passed.

## 2026-06-01 Local Exec Aggregated Shell Output Boundaries

### Scope

- Continued the local direct-shell output slice by tightening stdout/stderr aggregation before the unified-exec renderer sees it.
- This protects the model-visible tool output body from collapsing adjacent stdout and stderr fragments into one word, while keeping the stdlib-only local HTTP helper lightweight.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `file:codex-rs/core/src/tools/runtimes/shell.rs`
  - `function:codex-rs/core/src/tools/mod.rs#format_exec_output_for_model`
  - `function:codex-rs/core/src/exec.rs#process_raw_output`
- Rust source confirmed:
  - Shell execution returns an `ExecToolCallOutput` with separate stdout/stderr and an `aggregated_output` stream.
  - Model-visible formatting uses `aggregated_output` and prepends timeout text when the command timed out.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added `_combine_shell_output()` to coerce stdout/stderr values and insert a separator when both sides are present without line boundaries.
  - Timeout rendering now uses the same aggregation helper before passing content to the unified-exec output formatter.
- `tests/test_exec_local_runtime.py`
  - Added coverage for direct-runner stdout/stderr separation.
  - Added coverage for direct-runner timeout output using unified exec shape, exit code `124`, timeout text, and combined partial output.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_combines_stdout_and_stderr_with_separator tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_timeout_uses_unified_exec_shape tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_output_execution_helper`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 322 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 131 tests passed.

## 2026-06-01 Local Exec Truncation Marker Shape

### Scope

- Continued the model-visible local shell output parity work by aligning Python's direct-runner truncation marker with Rust's output-truncation text shape.
- This keeps long command output returned through the local HTTP `exec_command` helper closer to upstream user/model-facing behavior.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/tools/mod.rs#format_exec_output_for_model`
  - `function:codex-rs/utils/output-truncation/src/lib.rs#truncate_text`
  - `function:codex-rs/utils/string/src/truncate.rs#format_truncation_marker`
- Rust source confirmed:
  - Truncated output is prefixed with `Total output lines: N` when truncation changes line count.
  - The truncation marker uses the compact `…N chars truncated…` / `…N tokens truncated…` shape.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added `_local_http_truncation_marker()` and switched `_truncate_middle_shell_tool_output()` from the Python-only `... N chars truncated ...` marker to the Rust-shaped `…N chars truncated…` output.
- `tests/test_exec_local_runtime.py`
  - Added coverage that local shell truncation includes the Rust marker shape and no longer emits the spaced ASCII marker.

### Validation

- `python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tool_truncation_uses_utf8_byte_budget tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tool_truncation_marker_matches_rust_shape tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_truncates_output`
  - 3 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 323 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 132 tests passed.

## 2026-06-01 Local Exec Token Budget Truncation

### Scope

- Continued local HTTP `exec_command` output parity by separating token-budget truncation from byte-budget truncation.
- This keeps model-visible tool output aligned with Rust unified exec when `max_output_tokens` is omitted or explicitly supplied.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/tools/context.rs#ExecCommandToolOutput`
  - `function:codex-rs/core/src/tools/context.rs#model_output_max_tokens`
  - `function:codex-rs/core/src/tools/context.rs#truncated_output`
  - `function:codex-rs/utils/output-truncation/src/lib.rs#truncate_text`
  - `function:codex-rs/utils/string/src/truncate.rs#truncate_middle_with_token_budget`
- Rust source confirmed:
  - Unified exec response text resolves a model output token budget and calls `formatted_truncate_text(..., TruncationPolicy::Tokens(max_tokens))`.
  - Token-budget truncation uses a `tokens truncated` marker, while byte-budget truncation uses a `chars truncated` marker.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added `LocalHttpOutputBudget` to carry whether a local direct-shell output cap is token- or char-based.
  - Added `_effective_shell_output_budget()` and `_output_budget_max_bytes()` so direct runner output can use token markers while long-lived session/write_stdin paths still receive byte caps.
  - Added `_truncate_shell_tool_output_tokens()` for stdlib-only approximate token truncation with Rust-shaped `…N tokens truncated…` marker text.
- `tests/test_exec_local_runtime.py`
  - Updated the default direct shell output limit to expect `tokens truncated`.
  - Added explicit `max_output_tokens` coverage that asserts token markers are used and char markers are not.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_uses_default_output_token_limit tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_max_output_tokens_uses_token_marker tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_truncates_output tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tool_truncation_marker_matches_rust_shape`
  - 4 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 324 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 133 tests passed.

## 2026-06-01 Local Exec Session Nonzero Success Semantics

### Scope

- Extended the Rust unified exec success semantics from direct local shell execution into long-lived local exec sessions and `write_stdin`.
- A process that exits nonzero after a session start or stdin write is now returned as a successful tool observation with the exit code in the model-visible output.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/tools/context.rs#ExecCommandToolOutput`
  - `function:codex-rs/core/src/tools/context.rs#to_response_item`
  - `function:codex-rs/core/src/unified_exec/process_manager.rs#exec_command`
  - `function:codex-rs/core/src/unified_exec/process_manager.rs#write_stdin`
- Rust source confirmed:
  - `process_manager.exec_command(...)` and `process_manager.write_stdin(...)` both return `ExecCommandToolOutput` for alive and exited processes.
  - `ExecCommandToolOutput.to_response_item()` sends `success: Some(true)` independent of `exit_code`.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `LocalHttpExecSession.snapshot()` now returns `success=True` for normal completed/alive process observations, including nonzero exit codes.
  - Local session timeout remains `success=False` because the helper had to terminate the process.
- `tests/test_exec_local_runtime.py`
  - Added session-start coverage for a process exiting with code `7`.
  - Added `write_stdin` coverage for a process exiting with code `9`.
  - Kept timeout cleanup coverage asserting the timeout path remains unsuccessful.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_session_nonzero_exit_remains_successful_tool_result tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_nonzero_exit_remains_successful_tool_result tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_session_timeout_cleans_up_session`
  - 3 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 326 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 135 tests passed.

## 2026-06-01 Local Exec Nonzero Timeline Status

### Scope

- Separated model-visible tool success from user-visible tool/timeline status for local HTTP shell output.
- This preserves Rust behavior where a nonzero command exit is a successful tool observation to the model, while command/event rendering still marks the command as failed for the user.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/tools/context.rs#ExecCommandToolOutput`
  - `function:codex-rs/core/src/tools/context.rs#to_response_item`
  - `function:codex-rs/core/src/tools/events.rs#finish`
  - `function:codex-rs/core/src/tools/events.rs#emit_exec_stage`
- Rust source confirmed:
  - `ExecCommandToolOutput.to_response_item()` emits `success: Some(true)`.
  - Tool event handling derives command execution status from `ExecToolCallOutput.exit_code`, so nonzero exits render as failed events.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added `_tool_output_status_from_item()` and `_tool_output_exit_code_from_item()`.
  - Local HTTP tool timeline/output items now mark status `failed` when `success` is false or a `Process exited with code N` / structured `exit_code` is nonzero.
  - Model-facing `success=True` for nonzero command observations remains unchanged.
- `tests/test_exec_local_runtime.py`
  - Added coverage that a nonzero direct shell result remains a successful tool output for follow-up sampling, but renders as `failed` in tool output/timeline JSON events.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_nonzero_exit_marks_timeline_failed tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_nonzero_exit_remains_successful_tool_result tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer`
  - 3 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 327 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 136 tests passed.

## 2026-06-01 Local Exec Nonzero Exit Success Semantics

### Scope

- Aligned local HTTP direct-shell response-item success semantics with Rust unified exec.
- A command that runs and exits nonzero is now returned as a successful tool observation with the exit code/stderr in the output text, rather than as a failed tool call.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/core/src/tools/context.rs#ExecCommandToolOutput`
  - `function:codex-rs/core/src/tools/context.rs#to_response_item`
  - `function:codex-rs/core/src/tools/context.rs#success_for_logging`
  - `function:codex-rs/core/src/tools/events.rs#format_exec_output_for_model`
- Rust source confirmed:
  - `ExecCommandToolOutput.success_for_logging()` returns true.
  - `ExecCommandToolOutput.to_response_item()` calls `function_tool_response(..., Some(true))` independent of the contained process exit code.
  - The command failure remains visible to the model through `Process exited with code N` and output text.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_run_shell_tool_command_result()` now returns `success=True` when the runner completes, even for nonzero return codes.
  - Timeout exceptions still return `success=False` because no normal completed command result was produced.
- `tests/test_exec_local_runtime.py`
  - Renamed and updated the nonzero-exit coverage to assert a successful tool result with `Process exited with code 7`.

### Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_nonzero_exit_remains_successful_tool_result tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_combines_stdout_and_stderr_with_separator tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_timeout_uses_unified_exec_shape`
  - 3 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 324 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 133 tests passed.

## 2026-06-01 Local Exec Truncation Head/Tail Budget

### Scope

- Tightened the local HTTP direct shell output truncation algorithm to match Rust's byte-budget semantics more closely.
- This keeps long command outputs useful to the model by preserving the beginning and end of the original output, even when the truncation marker itself is longer than the requested byte budget.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/tools/mod.rs#format_exec_output_for_model`
  - `function:codex-rs/utils/output-truncation/src/lib.rs#formatted_truncate_text`
  - `function:codex-rs/utils/string/src/truncate.rs#truncate_with_byte_estimate`
  - `function:codex-rs/utils/string/src/truncate.rs#split_string`
- Rust source confirmed:
  - Byte truncation splits the requested byte budget between the original prefix and suffix.
  - The truncation marker is inserted between those retained regions rather than being counted against the retained-content budget.
  - Removed character count is based on the omitted middle segment.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_truncate_middle_shell_tool_output()` now splits the byte budget across original output head/tail and inserts the Rust-shaped marker between them.
  - Added `_split_shell_output_for_truncation()` and `_iter_shell_output_char_byte_indices()` to preserve UTF-8 character boundaries using only the standard library.
- `tests/test_exec_local_runtime.py`
  - Strengthened truncation-marker coverage to assert retained head/tail output, e.g. `abcdef…14 chars truncated…uvwxyz`.

### Validation

- `python -m unittest tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tool_truncation_marker_matches_rust_shape tests.test_exec_local_runtime.LocalHttpShellToolSpecTests.test_local_http_shell_tool_truncation_uses_utf8_byte_budget tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_truncates_output`
  - 3 tests passed.
- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router`
  - 323 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_http_transport tests.test_cli_parser -k local_http`
  - 132 tests passed.

## 2026-06-01 Local HTTP Auth Error Surface

### Scope

- Aligned the local HTTP exec missing-auth CLI tests with the Python runtime's OpenAI/Codex API key fallback behavior.
- Hardened the missing-key tests so an ambient `CODEX_API_KEY` in the developer environment cannot accidentally make the test take the authenticated path.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/protocol/src/error.rs#CodexErr:68`
  - `function:codex-rs/login/src/auth/manager.rs#read_openai_api_key_from_env:471`
  - `function:codex-rs/login/src/auth/manager.rs#read_codex_api_key_from_env:478`
  - `function:codex-rs/login/src/auth/manager.rs#load_auth:735`
- Rust source confirmed:
  - Auth env handling names both `OPENAI_API_KEY` and `CODEX_API_KEY`.
  - `CODEX_API_KEY` is honored when the Codex API key env mode is enabled.
  - Env auth values are trimmed and ignored when empty.

### Python Changes

- `tests/test_cli_parser.py`
  - Updated local HTTP missing-key human and JSON assertions to expect `OPENAI_API_KEY or CODEX_API_KEY`.
  - The tests now temporarily remove both `OPENAI_API_KEY` and `CODEX_API_KEY` before invoking the CLI and restore both afterward.

### Validation

- `python -m py_compile tests/test_cli_parser.py`
  - Passed.
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_missing_api_key_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_missing_api_key_prints_json_turn_failed tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_error_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_error_prints_json_turn_failed tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_runtime_requires_api_key tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_uses_codex_api_key_env_var tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_prefers_openai_env_over_codex_env_key`
  - 7 tests passed.

## 2026-06-01 Local HTTP Default Model Smoke Isolation

### Scope

- Hardened the local HTTP exec request smoke test so it verifies the no-config default model path instead of accidentally inheriting the developer environment.
- This protects the model precedence behavior on the common local HTTP `exec` path:
  - explicit session config model;
  - `PYCODEX_EXEC_MODEL`;
  - `OPENAI_MODEL`;
  - `config.toml` model;
  - built-in default.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/mod.rs#get_default_model:536`
  - `class:codex-rs/core/src/config/mod.rs#Config:695`
  - `function:codex-rs/exec/src/lib.rs#run_exec_session:577`
- Rust source confirmed:
  - The configured model participates in session startup before requests are sent.
  - When no model is configured, Codex falls back through the model/default-selection path.

### Python Changes

- `tests/test_cli_parser.py`
  - `test_main_exec_local_http_smoke_posts_expected_request` now runs with a temporary empty `CODEX_HOME`.
  - It explicitly clears `PYCODEX_EXEC_MODEL` and `OPENAI_MODEL` in the test environment before asserting the built-in local HTTP default model.

### Validation

- `python -m py_compile tests/test_cli_parser.py`
  - Passed.
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_posts_expected_request tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_model_precedence`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor tests.test_exec_config_plan tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_posts_expected_request tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_uses_openai_base_url tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_outputs_thread_and_turn_events tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_uses_config_provider_env_key tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop`
  - 259 tests passed.

## 2026-06-01 Local HTTP Auth Object Preservation

### Scope

- Preserved auth.json-derived auth objects through the local HTTP exec runtime instead of collapsing them to raw API-key strings before sampling.
- Environment variable auth still takes precedence, but stored auth now keeps its structured shape until the HTTP request layer extracts headers.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/login/src/auth/manager.rs#CodexAuth:51`
  - `function:codex-rs/login/src/auth/manager.rs#from_auth_dot_json:203`
  - `function:codex-rs/login/src/auth/manager.rs#load_auth:735`
  - `function:codex-rs/core/src/client.rs#create_model_provider:330`
- Rust source confirmed:
  - `AuthDotJson` is converted into a structured `CodexAuth`.
  - `CODEX_API_KEY` env auth can override stored auth when enabled.
  - The core client/model-provider layer owns converting structured auth into request credentials.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `default_local_http_exec_auth` now returns the auth object itself for auth.json-style objects when no env/provider key overrides it.
  - `OPENAI_API_KEY`, `CODEX_API_KEY`, and provider `env_key` values still return strings and keep priority over stored auth.
- `tests/test_exec_local_runtime.py`
  - Updated auth fallback coverage to assert object preservation in an empty-env case.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py tests/test_cli_parser.py`
  - Passed.
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_uses_auth_json_api_key tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_prefers_env_api_key_over_auth_json tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_uses_auth_openai_api_key_value tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_prefers_env_key tests.test_core_http_transport.HttpTransportTests.test_http_transport_config_from_provider_combines_endpoint_auth_and_client_headers`
  - 5 tests passed.
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_posts_expected_request tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_smoke_uses_openai_base_url tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_outputs_thread_and_turn_events tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_missing_api_key_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_missing_api_key_prints_json_turn_failed tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_error_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_provider_error_prints_json_turn_failed tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_writes_last_message_file tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_writes_last_message_file tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_uses_auth_json_api_key tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_reads_config_toml_for_local_http_session_config tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_prefers_env_api_key_over_auth_json tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_uses_config_provider_env_key tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_last_uses_resume_runner tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_named_session_uses_resume_runner tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_passes_tool_loop_options tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_uses_auth_openai_api_key_value tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_prefers_env_key tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_default_local_http_auth_uses_codex_api_key_env_var`
  - 20 tests passed.

## 2026-06-01 Resume Config Summary Thread Identity

### Scope

- Rechecked the local HTTP `exec resume` human config summary against upstream Rust before expanding the Python output surface.
- The selected slice protects the common resume path while keeping structured thread identity in JSON/thread events rather than human config summary lines.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/protocol/src/protocol.rs#SessionConfiguredEvent:3362`
  - `function:codex-rs/core/src/session/session.rs#new:500`
  - `function:codex-rs/core/src/session/tests.rs#resumed_root_session_uses_thread_id_as_session_id:4970`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#config_summary_entries:421`
  - `function:codex-rs/exec/src/lib.rs#session_configured_from_thread_resume_response:1087`
- Rust source confirmed:
  - `SessionConfiguredEvent` carries both `session_id` and `thread_id`.
  - Resumed root sessions use the resumed thread id as the session id, while sub-agent resumes can preserve an inherited session id.
  - Human config summary entries print `session id` but do not print a separate `thread_id` line.
  - JSON/thread-started event output uses the structured `thread_id`.

### Python Changes

- `tests/test_exec_event_processor.py`
  - Tightened the human config summary test to assert `thread_id` is not emitted as a human summary entry.
  - Existing JSON summary coverage continues to assert `thread.started` carries `thread_id`.
- `tests/test_cli_parser.py`
  - Aligned the local HTTP `exec resume --last` expectation with Rust human output by checking `session id: resumed-thread` instead of a non-upstream `thread_id:` summary line.

### Validation

- `python -m py_compile pycodex/exec/event_processor.py tests/test_exec_event_processor.py tests/test_cli_parser.py`
  - Passed.
- `python -m unittest tests.test_exec_event_processor.ExecEventProcessorTests.test_config_summary_entries_match_upstream_order_and_sandbox_summary tests.test_exec_event_processor.ExecEventProcessorTests.test_config_summary_lines_match_human_output_shape tests.test_exec_event_processor.ExecEventProcessorTests.test_human_and_json_processors_print_config_summary tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_last_uses_resume_runner`
  - 4 tests passed.
- `python -m unittest tests.test_exec_event_processor`
  - 77 tests passed.

## 2026-06-01 Exec Human Reasoning Visibility Wiring

### Scope

- Connected the exec CLI config projection to the human-output reasoning visibility behavior used by the core `exec` path.
- This makes local HTTP `codex exec --oss ...` honor the upstream behavior that OSS runs expose raw reasoning content in human output.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `class:codex-rs/exec/src/event_processor_with_human_output.rs#EventProcessorWithHumanOutput:23`
  - `function:codex-rs/config/src/config_toml.rs#default_hide_agent_reasoning:86`
  - `function:codex-rs/core/src/session/mod.rs#show_raw_agent_reasoning:3221`
  - `function:codex-rs/exec/src/lib.rs#run_exec_session:577`
- Rust source confirmed:
  - `EventProcessorWithHumanOutput::create_with_ansi` initializes `show_agent_reasoning` from `!config.hide_agent_reasoning`.
  - It initializes `show_raw_agent_reasoning` from `config.show_raw_agent_reasoning`.
  - The exec session creates the human event processor from the final config before processing server notifications.

### Python Changes

- `pycodex/cli/parser.py`
  - `_build_exec_session_config` now preserves `harness_overrides.show_raw_agent_reasoning`.
  - The noninteractive exec human processor is configured from the projected `ExecSessionConfig` for both local HTTP and remote app-server paths.
  - Local HTTP result rendering now receives the same `ExecSessionConfig`, so reasoning items replayed after sampling use the configured visibility.
- `tests/test_cli_parser.py`
  - Added CLI coverage that `exec --oss --local-provider lmstudio` emits raw reasoning content from the local HTTP result instead of the public summary.

### Validation

- `python -m py_compile pycodex/cli/parser.py tests/test_cli_parser.py`
  - Passed.
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_configures_human_reasoning_visibility tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_runtime_prints_summary_and_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_last_uses_resume_runner tests.test_exec_event_processor.ExecEventProcessorTests.test_human_processor_configures_reasoning_visibility_from_exec_config`
  - 4 tests passed.
- `python -m unittest tests.test_exec_config_plan tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_human_reasoning_uses_raw_content_when_enabled tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_reasoning_texts_skip_raw_reasoning_content_by_default tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_reasoning_texts_accept_app_server_style_fields`
  - 71 tests passed.

## 2026-06-01 Rollout Event Readback Helper

### Scope

- Added a filesystem rollout helper for reading persisted `event_msg` JSONL items back into protocol `EventMsg` values.
- This keeps interrupted-turn rollout persistence on the same helper path used by resume/local exec tests instead of requiring each caller to hand-parse JSONL lines.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/rollout/src/recorder.rs` and `codex-rs/rollout/src/list.rs` consumers of `RolloutItem::EventMsg`.
  - `codex-rs/core/src/session/turn.rs` interrupted-turn event emission path.
  - Python protocol `RolloutItem.event_msg` and `SavedRollout.get_event_msgs` as the local contract counterpart.
- Rust source confirmed:
  - Rollout history treats protocol events as first-class `EventMsg` items alongside response items.
  - Interrupted turns are represented as structured protocol events, not only prompt-visible marker text.

### Python Changes

- `pycodex/core/rollout.py`
  - Added `read_event_msgs_from_rollout(path, max_items=None)`.
  - The helper mirrors `read_response_items_from_rollout`: ignores malformed JSONL/non-event rows, parses payloads with `EventMsg.from_mapping`, preserves file order, and supports `max_items`.
- `pycodex/core/__init__.py`
  - Re-exported `read_event_msgs_from_rollout`.
- `tests/test_core_rollout.py`
  - Verified appended `turn_aborted` events can be read back as typed protocol events.
  - Added invalid-line and `max_items` coverage.
- `tests/test_exec_local_runtime.py`
  - Switched interrupted rollout assertions to the shared event reader.

### Validation

- `python -m py_compile pycodex/core/rollout.py pycodex/core/__init__.py pycodex/exec/local_runtime.py tests/test_core_rollout.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_rollout.CoreRolloutTests.test_append_event_msg_to_rollout_persists_turn_aborted_event tests.test_core_rollout.CoreRolloutTests.test_read_event_msgs_from_rollout_skips_invalid_lines_and_respects_max_items tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_rollout_persists_interrupted_turn_marker tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_persists_interrupted_turn_event`
  - 4 tests passed.
- `python -m unittest tests.test_core_rollout`
  - 32 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 106 tests passed.

## 2026-06-01 Resume Rollout History Reconstruction

### Scope

- Moved local HTTP resume history loading closer to Rust's rollout replay semantics.
- Python resume no longer treats rollout history as a flat list of `response_item` rows only; it now reconstructs model-visible history from response items plus selected structural rollout events.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/rollout/src/recorder.rs::get_rollout_history`
  - `codex-rs/core/src/session/mod.rs::record_initial_history`
  - `codex-rs/core/src/session/rollout_reconstruction.rs::reconstruct_history_from_rollout`
  - `codex-rs/core/src/context_manager/history.rs::drop_last_n_user_turns`
- Rust source confirmed:
  - Resume loads full rollout items, not only `ResponseItem` entries.
  - `Compacted.replacement_history` replaces the reconstructed model history baseline.
  - `EventMsg::ThreadRolledBack` drops the newest user-turn segments from reconstructed history.
  - Non-model-visible rollout items such as `SessionMeta`, `TurnContext`, and most events do not become request input.

### Python Changes

- `pycodex/core/rollout.py`
  - Added `read_model_history_from_rollout(path)`.
  - The helper reads rollout JSONL in order, appends valid response items, applies compacted replacement history, and handles `thread_rolled_back` events by dropping the latest user turns.
- `pycodex/core/__init__.py`
  - Re-exported `read_model_history_from_rollout`.
- `pycodex/exec/local_runtime.py`
  - `run_exec_resume_user_turn_http_sampling` now preloads reconstructed model history instead of raw response-only history.
- `tests/test_core_rollout.py`
  - Added compacted replacement-history and rollback replay coverage.
- `tests/test_exec_local_runtime.py`
  - Added resume-runner coverage proving compacted/rolled-back text is not sent in the next model request while surviving history remains ordered.

### Validation

- `python -m py_compile pycodex/core/rollout.py pycodex/core/__init__.py pycodex/exec/local_runtime.py tests/test_core_rollout.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_rollout.CoreRolloutTests.test_read_model_history_from_rollout_applies_compacted_replacement_history tests.test_core_rollout.CoreRolloutTests.test_read_model_history_from_rollout_applies_thread_rollback_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_reconstructed_model_history`
  - 3 tests passed.
- `python -m unittest tests.test_core_rollout`
  - 34 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 107 tests passed.

## 2026-06-01 Resume Initial Messages In SessionConfigured

### Scope

- Added resume `initial_messages` propagation for the local HTTP exec summary path and remote thread response mapping.
- This preserves the Rust behavior where resumed sessions include persisted rollout `EventMsg` history in `SessionConfiguredEvent.initial_messages` so clients can render prior messages immediately.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/core/src/session/session.rs::Session::new`
  - `codex-rs/protocol/src/protocol.rs::SessionConfiguredEvent`
  - `codex-rs/core/tests/suite/resume.rs::resume_includes_initial_messages_from_rollout_events`
  - `codex-rs/core/tests/suite/resume.rs::resume_includes_initial_messages_from_reasoning_events`
- Rust source confirmed:
  - `SessionConfiguredEvent` is sent before other startup events.
  - On resume, `initial_messages` is populated by `initial_history.get_event_msgs()`.
  - The initial messages include persisted user, agent, reasoning, token-count, and turn lifecycle events from the rollout.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - Added `local_http_exec_initial_messages_from_rollout(path)`.
  - Extended `local_http_exec_config_summary` with optional `initial_messages` and `rollout_path`.
- `pycodex/cli/parser.py`
  - Local HTTP `exec resume` now passes rollout-derived initial messages into the config summary before sampling starts.
- `pycodex/exec/session.py`
  - Remote thread start/resume response mapping now preserves `initialMessages` / `initial_messages` as typed `EventMsg` values on `SessionConfiguredEvent`.
- `tests/test_exec_local_runtime.py`
  - Added coverage for local HTTP resume summary initial-message serialization.
- `tests/test_exec_session.py`
  - Added coverage for snake_case remote resume responses carrying initial messages.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py pycodex/cli/parser.py pycodex/exec/session.py tests/test_exec_local_runtime.py tests/test_exec_session.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_config_summary_includes_resume_initial_messages tests.test_exec_session.ExecSessionRequestBuilderTests.test_session_configured_from_thread_resume_response_accepts_snake_case_response`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 108 tests passed.
- `python -m unittest tests.test_exec_session`
  - 119 tests passed.
- `python -m unittest tests.test_cli_parser`
  - Failed with pre-existing broad CLI failures unrelated to this slice, including live HTTP 401s, cloud/doctor/help expectation drift, and local HTTP rollout serialization/auth expectation failures.

## 2026-06-01 Local HTTP Rollout Raw Response Persistence

### Scope

- Fixed local HTTP rollout persistence when the exec result contains display-layer response item objects that do not expose protocol `to_mapping()`.
- This advances the CLI local HTTP core path because mocked and app-server-shaped result items should not prevent a successful `exec` run from being persisted to rollout history.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `codex-rs/core/src/session/mod.rs::record_conversation_items`
  - `codex-rs/core/src/session/mod.rs::persist_rollout_items`
  - `codex-rs/protocol/src/models.rs::ResponseItem`
  - `codex-rs/protocol/src/protocol.rs::RolloutItem`
- Rust source confirmed:
  - Rollout persistence stores protocol `RolloutItem::ResponseItem` values.
  - The model-visible output item, not UI display wrapper shape, is the durable rollout payload.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_local_http_prompt_visible_rollout_items` now prefers canonical raw Responses `output` payloads when no tool-output interleaving is needed.
  - This keeps rollout persistence on protocol `ResponseItem` mappings even when `result.response_items` contains display-only objects from a test double or app-server-shaped adapter.
- `tests/test_exec_local_runtime.py`
  - Added coverage proving raw Responses output is used for persistence instead of a non-serializable display item.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py tests/test_cli_parser.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_prefers_raw_response_items_for_persistence tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_uses_config_provider_env_key`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 109 tests passed.
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_flag_uses_tool_loop tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_uses_config_provider_env_key tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_last_uses_resume_runner`
  - 2 serialization-related tests passed.
  - `test_main_exec_resume_local_http_last_uses_resume_runner` still fails on an existing human summary formatting expectation for `thread_id`, not on rollout serialization.

## 2026-06-01 Stream Tail Turn-Aborted Handling

### Scope

- Preserved Rust's post-drain cancellation boundary in the Python session-like turn runtime.
- When cancellation is detected after response completion, response-processed, drain, and token-count side effects now remain visible, but the Python runtime stops before turn diff/tool dispatch/follow-up work and returns the partial turn result instead of surfacing `turn_aborted` as a terminal sampling error.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `class:codex-rs/core/src/context/turn_aborted.rs#TurnAborted:4`
- Rust source confirmed:
  - `try_run_sampling_request` sends `response.processed`, drains in-flight work, and emits token counts before checking cancellation.
  - If the cancellation token is cancelled at that boundary, it returns `CodexErr::TurnAborted` before turn-diff emission.
  - `run_turn` handles `CodexErr::TurnAborted` by breaking the turn loop without emitting the generic terminal error path.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Catches `turn_aborted` from stream loop-tail execution and returns the accumulated `UserTurnSamplingResult`.
  - Shared the result construction path so normal completion and cancellation after tail expose the same result fields.
- `tests/test_core_turn_runtime.py`
  - Added coverage for cancellation after stream tail, including response-processed/drain/token-count ordering and absence of turn-diff/error emission.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_turn_aborted_after_stream_tail_returns_partial_result tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_stream_completed_usage_to_session tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_stream_metadata_to_session`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 47 tests passed.

## 2026-06-01 Local Exec Interrupted Turn Rendering

### Scope

- Carried the Rust interrupted-turn boundary from the session-like runtime result into local exec rendering.
- A turn aborted after the stream tail is now marked as `interrupted` instead of being rendered as a successful completed answer.
- Local exec output now follows the Rust exec processors: JSON output does not emit a synthetic success/failure event for interrupted turns, and human output prints `turn interrupted` without treating partial assistant text as the final answer.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/exec/src/event_processor_with_jsonl_output.rs#collect_thread_events:412`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#process_server_notification:227`
- Rust source confirmed:
  - `TurnStatus::Interrupted` clears the final message state.
  - JSON exec initiates shutdown without emitting `turn.completed` or `turn.failed`.
  - Human exec prints `turn interrupted` and does not print a final answer.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added `turn_status` to `UserTurnSamplingResult`.
  - Marks post-tail cancellation results as `interrupted`.
- `pycodex/exec/local_runtime.py`
  - Suppresses final-answer extraction for interrupted results.
  - Renders interrupted local HTTP exec results through the normal exec processor notification path.
- `tests/test_core_turn_runtime.py` and `tests/test_exec_local_runtime.py`
  - Added coverage for interrupted status propagation and local exec interrupted rendering.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py pycodex/exec/local_runtime.py tests/test_core_turn_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_turn_aborted_after_stream_tail_returns_partial_result tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_renders_interrupted_turn_without_final_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_replays_stream_error_session_event`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 47 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 103 tests passed.

## 2026-06-01 Local Exec Follow-Up Interrupted Status Merge

### Scope

- Preserved interrupted-turn status across local HTTP exec follow-up result merging.
- This keeps a later interrupted follow-up from being rendered as a completed turn when an earlier sampling result has partial streamed assistant text.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `class:codex-rs/app-server-protocol/src/protocol/v2/turn.rs#TurnStatus:28`
  - `function:codex-rs/exec/src/event_processor_with_jsonl_output.rs#collect_thread_events:412`
- Rust source confirmed:
  - The turn's final status comes from the terminal turn notification/result, not from earlier partial model output.
  - `TurnStatus::Interrupted` clears final-message state and does not emit a JSON success/failure terminal event.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_merge_local_http_sampling_result` now carries the follow-up result's `turn_status` into the merged result.
- `tests/test_exec_local_runtime.py`
  - Added coverage that a follow-up interrupted status survives merge and suppresses final text extraction.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_merge_preserves_followup_interrupted_status tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_merge_preserves_followup_streamed_last_agent_message tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_renders_interrupted_turn_without_final_answer`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 104 tests passed.

## 2026-06-01 Sampling Request Turn-Aborted Handling

### Scope

- Aligned sampler-level cancellation with Rust `run_turn` behavior.
- When the initial sampler or a follow-up sampler raises `turn_aborted` before producing a sampling result, the Python session-like runtime now returns an `interrupted` turn result instead of routing through terminal error handling.
- Follow-up cancellation preserves accumulated response items, request plans, raw results, stream artifacts, and session events from earlier successful sampling requests.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
- Rust source confirmed:
  - `try_run_sampling_request` maps cancellation while creating or reading the stream to `CodexErr::TurnAborted`.
  - `run_turn` handles `Err(CodexErr::TurnAborted)` by breaking the turn loop and skipping the generic terminal error path.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Initial sampler `turn_aborted` now returns an empty interrupted `UserTurnSamplingResult`.
  - Follow-up sampler `turn_aborted` now returns the accumulated interrupted result.
- `tests/test_core_turn_runtime.py`
  - Added coverage for initial sampler cancellation and follow-up sampler cancellation.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_turn_aborted_before_sampling_result_returns_interrupted tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_turn_aborted_during_followup_returns_accumulated_interrupted tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_turn_aborted_after_stream_tail_returns_partial_result`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 49 tests passed.
- `python -m unittest tests.test_core_session_runtime`
  - 72 tests passed.

## 2026-06-01 Local Exec Interrupted Rollout Marker

### Scope

- Preserved interrupted-turn context in local HTTP exec rollout persistence.
- Interrupted local exec results now append the model-visible `<turn_aborted>` marker to the persisted response items, so resume prompt assembly can tell the model the prior turn was intentionally interrupted instead of silently resuming from partial assistant output.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/thread_manager.rs#append_interrupted_boundary:1524`
  - `function:codex-rs/core/src/tasks/mod.rs#interrupted_turn_history_marker:87`
  - `class:codex-rs/core/src/context/turn_aborted.rs#TurnAborted:4`
- Rust source confirmed:
  - Interrupted snapshots append a contextual `<turn_aborted>` response item when the interrupt marker feature is enabled.
  - Rust also appends a `TurnAborted` event; Python local rollout resume currently consumes response items, so this slice ports the prompt-visible marker first.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_local_http_response_rollout_payloads` appends `TurnAborted.INTERRUPTED_GUIDANCE` as a user response item for interrupted results.
- `tests/test_exec_local_runtime.py`
  - Added coverage that persisted interrupted local exec rollouts read back a `<turn_aborted>` marker through `read_response_items_from_rollout`.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_rollout_persists_interrupted_turn_marker tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_renders_interrupted_turn_without_final_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_merge_preserves_followup_interrupted_status`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 105 tests passed.

## 2026-06-01 Resume Runner Interrupted Event Persistence

### Scope

- Completed interrupted-turn event persistence for the actual local HTTP resume runner path.
- `run_exec_resume_user_turn_http_sampling` previously appended response items directly to the resolved rollout and bypassed the interrupted event helper used by new-turn and resume-helper persistence. It now writes the same `turn_aborted` event after interrupted resumed turns.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/thread_manager.rs#append_interrupted_boundary:1524`
  - `class:codex-rs/protocol/src/protocol.rs#TurnAbortedEvent:3630`
  - `function:codex-rs/core/src/tasks/mod.rs#interrupted_turn_history_marker:87`
- Rust source confirmed:
  - Interrupted persisted history includes both the marker response item and the structured `TurnAborted` event at the interrupted boundary.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `run_exec_resume_user_turn_http_sampling` now reuses the interrupted event persistence helper after direct rollout append.
- `tests/test_exec_local_runtime.py`
  - Added coverage for interrupted results returned through the real resume runner append path.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_persists_interrupted_turn_event tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_rollout_persists_interrupted_turn_marker tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_pre_resolved_rollout_path`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 106 tests passed.

## 2026-06-01 Interrupted Rollout Event Persistence

### Scope

- Added a rollout-level event writer and used it to persist `turn_aborted` events for interrupted local HTTP exec turns.
- This complements the prompt-visible `<turn_aborted>` marker with the structured `event_msg` that Rust persists at the interrupted turn boundary.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/thread_manager.rs#append_interrupted_boundary:1524`
  - `class:codex-rs/protocol/src/protocol.rs#TurnAbortedEvent:3630`
  - `class:codex-rs/app-server-protocol/src/protocol/v2/turn.rs#TurnStatus:28`
- Rust source confirmed:
  - Interrupted boundaries append both a prompt-visible marker and `RolloutItem::EventMsg(EventMsg::TurnAborted(...))`.
  - The event reason is `TurnAbortReason::Interrupted`.

### Python Changes

- `pycodex/core/rollout.py`
  - Added `append_event_msg_to_rollout` for JSONL `event_msg` persistence.
- `pycodex/core/__init__.py`
  - Re-exported the event writer alongside the existing rollout append helpers.
- `pycodex/exec/local_runtime.py`
  - Interrupted local HTTP exec persistence now appends `EventMsg.turn_aborted` with `TurnAbortReason.INTERRUPTED`.
- `tests/test_core_rollout.py` and `tests/test_exec_local_runtime.py`
  - Added focused coverage for direct event persistence and local interrupted rollout persistence.

### Validation

- `python -m py_compile pycodex/core/rollout.py pycodex/core/__init__.py pycodex/exec/local_runtime.py tests/test_core_rollout.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_rollout.CoreRolloutTests.test_append_event_msg_to_rollout_persists_turn_aborted_event tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_rollout_persists_interrupted_turn_marker`
  - 2 tests passed.
- `python -m unittest tests.test_core_rollout`
  - 31 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 105 tests passed.

## 2026-06-01 Local Exec Terminal Error Replay

### Scope

- Replayed terminal `EventMsg.error` session events through the local HTTP exec processors.
- This closes the output boundary for terminal runtime errors that are now emitted by the core turn runtime, so JSON exec output can surface the Rust-shaped `error` event before the failed turn event.
- Human output suppresses a duplicate failed-turn error when the terminal error was already replayed, matching Rust's split between `ServerNotification::Error` and a later failed turn with no turn-local error.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/exec/src/event_processor_with_jsonl_output.rs#collect_thread_events:412`
  - `function:codex-rs/exec/src/event_processor_with_human_output.rs#process_server_notification:227`
- Rust source confirmed:
  - JSON exec maps `ServerNotification::Error` to `ThreadEvent::Error`, stores it as `last_critical_error`, and can reuse it when the turn later fails without its own error.
  - Human exec prints the terminal error notification immediately, and only prints the failed-turn error when the turn completion notification includes one.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_local_http_session_event_notification` now maps ordinary `error` session events into app-server-style `method: "error"` notifications with `codexErrorInfo`.
  - `emit_local_http_exec_error` now leaves the human failed-turn notification error empty when a terminal error event was already replayed.
- `tests/test_exec_local_runtime.py`
  - Added coverage for JSON replay order (`turn.started`, `error`, `turn.failed`) and human output de-duplication.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_error_replays_attached_terminal_error_event tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_error_replays_attached_session_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_replays_stream_error_session_event`
  - 3 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 102 tests passed.

## 2026-06-01 Pending Input Active Turn Shim

### Scope

- Tightened the pending-input compatibility shim so Python passes the active turn to input queues that accept it.
- This keeps the core user-turn loop aligned with Rust's turn-local pending-input behavior.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `file:codex-rs/core/src/session/input_queue.rs`
  - `function:codex-rs/core/src/session/input_queue.rs#get_pending_input:169`
- Rust source confirmed:
  - `run_turn` calls `sess.input_queue.get_pending_input(&sess.active_turn)`.
  - `get_pending_input` uses the active turn boundary when returning queued user input for the current loop.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - `_call_input_queue_method` now prefers calling positional-compatible pending-input methods with `session.active_turn`.
  - The shim still supports zero-argument test doubles and older compatibility objects.
- `tests/test_core_turn_runtime.py`
  - Extended the pending-input test double to capture active-turn arguments.
  - Added an assertion that each pending-input drain receives the current session active turn.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup`
  - 1 test passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 44 tests passed.

## 2026-06-01 Invalid Tool Image Recovery

### Scope

- Continued the graph-selected `run_turn -> run_sampling_request` error boundary.
- Focused on Rust's `InvalidImageRequest` recovery path: sanitize bad tool-output images and retry the model request instead of letting an invalid generated/viewed image poison the turn.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `file:codex-rs/core/src/context_manager/history.rs`
  - `function:codex-rs/core/src/context_manager/history.rs#replace_last_turn_images:194`
- Rust source confirmed:
  - `run_turn` catches `CodexErr::InvalidImageRequest`.
  - It calls `state.history.replace_last_turn_images("Invalid image")`.
  - If the last turn contains a function-call output image, that image is replaced with a text placeholder and the loop retries.
  - User image messages are not rewritten; Rust emits a bad-request error message for those instead.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added invalid-image recovery around initial and follow-up sampler calls.
  - Added a stdlib-only history sanitizer for the Rust-covered case: recent `function_call_output` content images become `input_text("Invalid image")`.
  - Rebuilds the request from sanitized history before retrying.
  - Emits the Rust-shaped bad-request error event when no tool-output image can be sanitized.
- `tests/test_core_turn_runtime.py`
  - Added coverage for retrying after replacing a bad tool-output image.
  - Added coverage that user image messages are left intact and surface a bad-request error event.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_replaces_invalid_tool_output_image_and_retries tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_invalid_user_image_still_surfaces_bad_request_error`
  - 2 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 46 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_exec_local_runtime`
  - 145 tests passed.
- `python -m unittest tests.test_core_stream_events_utils tests.test_core_turn_sampler`
  - 117 tests passed.

## 2026-06-01 In-Memory History Image Replacement

### Scope

- Moved the invalid tool-image recovery behavior into the in-memory session API used by local/core runtime flows.
- This keeps Python's session-shaped object closer to Rust's `ConversationHistory::replace_last_turn_images` instead of relying only on a turn-runtime fallback.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `file:codex-rs/core/src/context_manager/history.rs`
  - `function:codex-rs/core/src/context_manager/history.rs#replace_last_turn_images:194`
- Rust source confirmed:
  - `replace_last_turn_images` scans back to the latest function-call output or user turn boundary.
  - It replaces only `FunctionCallOutputContentItem::InputImage` entries with an `InputText` placeholder.
  - It returns false for user image messages and non-image function outputs.

### Python Changes

- `pycodex/core/session_runtime.py`
  - Added `InMemoryCodexSession.replace_last_turn_images()`.
  - Rewrites `function_call_output` content-item images to `input_text(placeholder)` while preserving other output content and success metadata.
  - Stops at user message boundaries without mutating user-provided images.
- `tests/test_core_session_runtime.py`
  - Added focused coverage for replacing tool-output images.
  - Added coverage that user image messages remain unchanged.

### Validation

- `python -m py_compile pycodex/core/session_runtime.py tests/test_core_session_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_replace_last_turn_images_rewrites_tool_output_images tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_replace_last_turn_images_does_not_touch_user_images`
  - 2 tests passed.
- `python -m unittest tests.test_core_session_runtime`
  - 65 tests passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_replaces_invalid_tool_output_image_and_retries tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_invalid_user_image_still_surfaces_bad_request_error`
  - 2 tests passed.
- `python -m unittest tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_http_transport`
  - 155 tests passed.

## 2026-06-01 In-Memory Pending Input Queue

### Scope

- Added a lightweight pending-input queue to the in-memory session runtime.
- This connects the already-ported Python turn loop pending-input drain to the common local/core session object used by HTTP sampling.
- The slice intentionally covers ordinary turn-local pending input only; mailbox delivery and sub-agent phases remain deferred extension behavior.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `file:codex-rs/core/src/session/input_queue.rs`
  - `function:codex-rs/core/src/session/input_queue.rs#get_pending_input:169`
  - `function:codex-rs/core/src/session/input_queue.rs#has_pending_input:207`
  - `function:codex-rs/core/src/session/mod.rs#steer_input:3153`
- Rust source confirmed:
  - `run_turn` drains `sess.input_queue.get_pending_input(&sess.active_turn)` before each follow-up request when draining is allowed.
  - `has_pending_input` is part of the follow-up decision after each sampling request.
  - Steering input extends the active turn's pending input so the current loop can pick it up.

### Python Changes

- `pycodex/core/session_runtime.py`
  - Added `InMemoryInputQueue`, `InMemoryActiveTurn`, and `InMemoryActiveTurnState`.
  - `InMemoryCodexSession` now owns default `input_queue` and `active_turn` objects.
  - Added `inject_if_running()` as a compatibility entrypoint that queues `UserInput` or `ResponseItem`-shaped pending input.
- `tests/test_core_session_runtime.py`
  - Added direct queue drain coverage.
  - Added local HTTP sampling coverage showing pending input causes a follow-up request and appears in the second request body.

### Validation

- `python -m py_compile pycodex/core/session_runtime.py tests/test_core_session_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_input_queue_drains_pending_items_for_active_turn tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_http_sampling_uses_pending_input_followup`
  - 2 tests passed.
- `python -m unittest tests.test_core_session_runtime`
  - 67 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 46 tests passed.
- `python -m unittest tests.test_core_session_runtime tests.test_core_http_transport tests.test_exec_local_runtime`
  - 212 tests passed.

### Follow-up Debt

- Mailbox delivery coordination and sub-agent delivery phases are still compatibility shims, not a full Rust port.

## 2026-06-01 In-Memory Stream Loop Tail Hooks

### Scope

- Added in-memory session support for the stream loop-tail side effects already driven by Python's turn runtime.
- This keeps local/core session behavior closer to Rust after `response.completed`: response-processed acknowledgement, in-flight drain, token-count emission, and turn-diff emission.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/session/turn.rs#drain_in_flight:1663`
  - `function:codex-rs/core/src/session/mod.rs#send_token_count_event:3022`
  - `function:codex-rs/core/src/client.rs#send_response_processed:967`
  - `class:codex-rs/core/src/turn_diff_tracker.rs#TurnDiffTracker:18`
- Rust source confirmed:
  - `try_run_sampling_request` records completed response metadata during streaming.
  - After stream completion, Rust sends response-processed when enabled, drains in-flight tool work, emits token counts, then emits turn diff.

### Python Changes

- `pycodex/core/session_runtime.py`
  - Added `send_response_processed`, `drain_in_flight`, and `get_unified_diff` methods.
  - Added in-memory tracking fields for response-processed ids, drain count, unified diff, and loop-tail call ordering.
  - Token-count and turn-diff event emission now records loop-tail order for tests.
- `tests/test_core_session_runtime.py`
  - Added an integration test using streamed `completed` metadata to assert in-memory loop-tail side effects and event emission.

### Validation

- `python -m py_compile pycodex/core/session_runtime.py tests/test_core_session_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_stream_loop_tail_side_effects`
  - 1 test passed.
- `python -m unittest tests.test_core_session_runtime`
  - 68 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport`
  - 90 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 101 tests passed.

## 2026-06-01 In-Memory Tool Dispatch Active-Turn Count

### Scope

- Verified the in-memory active-turn state against the real Python tool dispatch path.
- This protects the core `model tool call -> tool execution -> tool output follow-up -> final answer` path now that `InMemoryCodexSession` owns an active turn.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/stream_events_utils.rs#handle_output_item_done:343`
  - `file:codex-rs/core/src/state/turn.rs`
- Rust source confirmed:
  - Tool dispatch is part of `try_run_sampling_request` output-item handling.
  - Active turn state tracks per-turn tool activity during the common sampling loop.

### Python Changes

- `tests/test_core_session_runtime.py`
  - Added an integration test using `InMemoryCodexSession`, real `ToolRouter`, and a test handler.
  - The test asserts that dispatch increments `session.active_turn.turn_state.tool_calls`, records tool output, and continues to a final assistant answer.

### Validation

- `python -m py_compile tests/test_core_session_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_tool_dispatch_increments_active_turn_tool_calls`
  - 1 test passed.
- `python -m unittest tests.test_core_session_runtime`
  - 69 tests passed.
- `python -m unittest tests.test_core_tool_router tests.test_core_turn_runtime`
  - 98 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 101 tests passed.

## 2026-06-01 Terminal Error Lifecycle Side Effects

### Scope

- Added session-side lifecycle recording for terminal sampling errors while preserving Python's existing exception propagation to exec rendering.
- This moves the Python core loop closer to Rust `run_turn` behavior, where terminal errors emit turn-error lifecycle side effects before the turn ends.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `file:codex-rs/protocol/src/error.rs`
- Rust source confirmed:
  - Generic terminal errors call `e.to_codex_protocol_error()`, emit turn-error lifecycle, send an `ErrorEvent`, and end the turn.
  - `InvalidImageRequest` emits `CodexErrorInfo::BadRequest` when no tool-output image can be sanitized.
  - `ContextWindowExceeded` and `UsageLimitReached` still apply token/rate-limit side effects before the error reaches the outer turn boundary.

### Python Changes

- `pycodex/core/session_runtime.py`
  - Added `emit_turn_error_lifecycle()` and in-memory `turn_error_lifecycle` recording.
- `pycodex/core/turn_runtime.py`
  - Terminal sampling errors now call `emit_turn_error_lifecycle()` with `CodexErr.to_codex_protocol_error()`.
  - Invalid user-image failures record `bad_request` lifecycle before sending the user-facing bad-request error event.
- `tests/test_core_session_runtime.py`
  - Added lifecycle coverage for context-window, usage-limit, and invalid user-image terminal failures.

### Validation

- `python -m py_compile pycodex/core/session_runtime.py pycodex/core/turn_runtime.py tests/test_core_session_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_terminal_error_lifecycle tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_usage_limit_error_lifecycle tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_invalid_user_image_records_bad_request_lifecycle`
  - 3 tests passed.
- `python -m unittest tests.test_core_session_runtime`
  - 72 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport`
  - 90 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 101 tests passed.

### Follow-up Debt

- The Python non-interactive runtime still propagates terminal `CodexErr` for exec rendering instead of fully swallowing the error inside a Rust-shaped turn task.

## 2026-06-01 Terminal Error Event Emission

### Scope

- Extended terminal sampling error handling from lifecycle-only recording to Rust-shaped session error events.
- Kept local exec's user-facing failure rendering stable: ordinary session `error` events remain ignored by local replay, while `turn.failed` still comes from the caught `CodexErr`.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `file:codex-rs/protocol/src/error.rs`
  - `class:codex-rs/protocol/src/protocol.rs#ErrorEvent:1803`
- Rust source confirmed:
  - Terminal errors emit lifecycle side effects and then send `EventMsg::Error(e.to_error_event(None))`.
  - `InvalidImageRequest` that cannot be sanitized sends a bad-request `ErrorEvent` instead of a generic error.
  - Context-window and usage-limit sampling side effects happen before the outer turn emits the error event.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Terminal sampling errors now emit `EventMsg.error` using `CodexErr.to_error_event()`.
  - Context-window and usage-limit side effects run before lifecycle/error event emission.
  - Unsanitizable `invalid_image_request` raises after its bad-request error event instead of falling through to generic error handling.
- Tests:
  - `tests/test_core_session_runtime.py` now asserts `token_count` precedes `error` for context-window and usage-limit errors.
  - `tests/test_exec_local_runtime.py` now asserts attached context-window session events include `token_count` followed by `error`, while local exec rendering remains stable.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_session_runtime.py tests/test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_terminal_error_lifecycle tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_usage_limit_error_lifecycle tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_invalid_user_image_records_bad_request_lifecycle tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_context_window_error_attaches_session_events tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_error_replays_attached_session_events`
  - 5 tests passed.
- `python -m unittest tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_http_transport`
  - 162 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 101 tests passed.

## 2026-06-01 Local HTTP Follow-up Stream Artifact Merge

### Scope

- Preserved stream runtime artifacts when local HTTP exec performs tool-output follow-up sampling.
- This keeps the merged local exec result shaped like the Rust turn loop's whole-turn transcript: earlier stream events/plans are retained, while the final stream runtime state summary comes from the follow-up request when available.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `file:codex-rs/exec/src/event_processor_with_human_output_tests.rs`
- Rust source confirmed:
  - `run_turn` loops across follow-up sampling requests within a single user turn.
  - `try_run_sampling_request` updates streamed item state, `last_agent_message`, and `needs_follow_up` as events arrive.
  - exec human-output tests preserve an already streamed final message when a completed turn has no full turn items.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_merge_local_http_sampling_result` now concatenates `stream_events`, `stream_event_dispatch_plans`, and `stream_event_apply_plans` across the pre-tool and follow-up sampling results.
  - The merged result now carries the follow-up `stream_runtime_state_summary`, falling back to the previous summary when the follow-up has none.
- `tests/test_exec_local_runtime.py`
  - Added focused coverage for merged stream artifacts and fallback runtime state summary.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py pycodex/core/turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 100 tests passed.

## 2026-06-01 HTTP Sampling Retry Session Events

### Scope

- Connected Python HTTP sampling retries to session-visible stream retry events.
- This preserves the Rust user-facing behavior where retryable stream disconnects notify the frontend/exec processor instead of leaving the user with a silent wait.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/responses_retry.rs#handle_retryable_response_stream_error:22`
  - `function:codex-rs/core/src/session/mod.rs#notify_stream_error:3072`
  - `class:codex-rs/protocol/src/protocol.rs#StreamErrorEvent:3121`
- Rust source confirmed:
  - `run_sampling_request` loops retryable stream errors through `handle_retryable_response_stream_error`.
  - Retry reporting sends `StreamErrorEvent` with a `Reconnecting... {retry}/{max}` message and response-stream-disconnected error info.
  - Fallback transport decisions still send a warning event.

### Python Changes

- `pycodex/core/http_transport.py`
  - `model_client_http_sampler` now installs a default retry decision callback for retry-enabled sampling.
  - Retry decisions emit `stream_error` events through the session when `notify_message` is present, falling back to the session `notify_stream_error` method if an implementation provides it.
  - Fallback warning decisions emit session warning events.
  - User-provided `on_retry_decision` callbacks still run after the default session side effects.
- `pycodex/core/responses_retry.py`
  - Retry decisions now carry the original `CodexErr`, allowing HTTP sampling to populate stream-error details.
- `tests/test_core_http_transport.py`
  - Added coverage that a retryable disconnect emits a `stream_error` event before the retry succeeds.

### Validation

- `python -m py_compile pycodex/core/http_transport.py pycodex/core/responses_retry.py pycodex/core/turn_sampler.py`
  - Passed.
- `python -m unittest tests.test_core_responses_retry tests.test_core_turn_sampler tests.test_core_http_transport.HttpTransportTests.test_model_client_http_sampler_emits_stream_retry_event_by_default tests.test_core_http_transport.HttpTransportTests.test_model_client_http_sampler_can_retry_retryable_transport_errors`
  - 16 tests passed.
- `python -m unittest tests.test_core_http_transport`
  - 40 tests passed.

## 2026-06-01 Provider Stream Retry Defaults

### Scope

- Connected the default stream retry count to the common Python HTTP user-turn path.
- This moves retry behavior from an opt-in test/helper path into the same default path used by local exec HTTP sampling.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/responses_retry.rs#handle_retryable_response_stream_error:22`
  - `function:codex-rs/model-provider-info/src/lib.rs#stream_max_retries:298`
- Rust source confirmed:
  - `run_sampling_request` reads `turn_context.provider.info().stream_max_retries()` before entering the retry loop.
  - provider stream retries default to `5` and are capped at `100`.

### Python Changes

- `pycodex/core/http_transport.py`
  - Added `http_sampling_stream_max_retries` with Rust-shaped default (`5`) and cap (`100`).
  - `run_user_turn_http_sampling_from_session` now derives `sampling_max_retries` from the provider when the caller does not explicitly override it.
  - Provider info can come from mapping/object `info` or direct `stream_max_retries`, matching the lightweight provider shapes used in the Python port.
- `tests/test_core_http_transport.py`
  - Added coverage for default/capped provider retry counts.
  - Added coverage that `run_user_turn_http_sampling_from_session` retries by default from provider settings and emits the stream retry event added in the previous slice.

### Validation

- `python -m py_compile pycodex/core/http_transport.py`
  - Passed.
- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_http_sampling_stream_max_retries_uses_rust_defaults_and_cap tests.test_core_http_transport.HttpTransportTests.test_run_user_turn_http_sampling_uses_provider_stream_retry_default tests.test_core_http_transport.HttpTransportTests.test_model_client_http_sampler_emits_stream_retry_event_by_default`
  - 3 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_responses_retry`
  - 56 tests passed.

## 2026-06-01 Local Exec Stream Error Replay

### Scope

- Connected retry-time `stream_error` session events to local exec output replay.
- This completes the user-visible half of the HTTP retry work: reconnect notifications are no longer dropped between the in-memory session and the exec processors.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/mod.rs#notify_stream_error:3072`
  - `class:codex-rs/protocol/src/protocol.rs#StreamErrorEvent:3121`
  - `file:codex-rs/app-server/src/bespoke_event_handling.rs`
  - `file:codex-rs/exec/src/event_processor_with_human_output.rs`
  - `file:codex-rs/exec/src/event_processor_with_jsonl_output.rs`
- Rust source confirmed:
  - `notify_stream_error` creates `EventMsg::StreamError` with a reconnect message, response-stream-disconnected error info, and additional details.
  - app-server maps `EventMsg::StreamError` to `ServerNotification::Error` with `will_retry: true` without marking the turn failed.
  - exec human and JSONL processors render the intermediate error notification while continuing the turn.

### Python Changes

- `pycodex/exec/local_runtime.py`
  - `_local_http_session_event_notification` now maps `stream_error` events to local `error` notifications with `willRetry: true`.
  - Added a small `CodexErrorInfo` mapping helper so replayed notifications preserve error info when available.
- `tests/test_exec_local_runtime.py`
  - Added JSON and human-output coverage for replaying a retry-time stream error before final turn completion.

### Validation

- `python -m py_compile pycodex/exec/local_runtime.py`
  - Passed.
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_replays_stream_error_session_event tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_replays_metadata_session_events`
  - 2 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 101 tests passed.

## 2026-06-01 Terminal SSE Failure Coverage

### Scope

- Locked down Rust parity for terminal `response.failed` SSE errors on the common HTTP sampling path.
- This protects the retry loop from treating fatal model/provider failures as retryable stream disconnects.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/responses_retry.rs#handle_retryable_response_stream_error:22`
  - `file:codex-rs/codex-api/src/sse/responses.rs`
- Rust source confirmed:
  - SSE `response.failed` with `context_length_exceeded` maps to context-window exceeded.
  - `insufficient_quota`, `usage_not_included`, `cyber_policy`, `invalid_prompt`, `server_is_overloaded`, and `slow_down` are terminal errors rather than retryable stream failures.
  - empty cyber-policy messages use the standard cybersecurity fallback message.

### Python Changes

- `tests/test_core_http_transport.py`
  - Added reusable `_SseResponse` fixture for compact SSE transport tests.
  - Added coverage for terminal `response.failed` SSE codes and cyber-policy fallback messaging.
  - No production-code change was needed; the existing Python mapper already matched the Rust behavior.

### Validation

- `python -m py_compile tests/test_core_http_transport.py`
  - Passed.
- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_maps_terminal_sse_failed_errors tests.test_core_http_transport.HttpTransportTests.test_send_prepared_http_sampling_request_uses_cyber_policy_fallback_for_empty_sse_message`
  - 2 tests passed.
- `python -m unittest tests.test_core_http_transport tests.test_core_responses_retry tests.test_core_turn_sampler`
  - 58 tests passed.

## 2026-06-01 Pending Input Follow-up Loop

### Scope

- Connected turn-local pending input to the Python user-turn sampling loop.
- This advances the core Rust `run_turn` behavior where user input submitted while the model is running is drained into history and triggers another model request after the current sampling request completes.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `file:codex-rs/core/src/session/input_queue.rs`
  - `function:codex-rs/core/src/session/input_queue.rs#get_pending_input:169`
  - `function:codex-rs/core/src/session/input_queue.rs#has_pending_input:207`
- Rust source confirmed:
  - `run_turn` defers pending input at turn start so the original user input is sampled first.
  - After sampling completes, pending input is drained and recorded before building the next prompt.
  - Pending input makes the loop continue even when the model itself did not request a follow-up.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - `run_user_turn_sampling_from_session` now drains `sess.input_queue.get_pending_input(...)` before follow-up request construction.
  - Pending `UserInput`, `ResponseInputItem`, `ResponseItem`, and lightweight mapping/object shapes are converted to `ResponseItem` entries and recorded into session history.
  - Existing `max_tool_followups` behavior remains a hard cap on additional model requests.
- `tests/test_core_turn_runtime.py`
  - Added an in-memory `PendingInputQueue` test double.
  - Added coverage that pending input injected during the first sampling result is included in the follow-up request and causes a second sampler call.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_follows_stream_completed_end_turn_false`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 42 tests passed.

## 2026-06-01 Pending Input Limit Boundary

### Scope

- Tightened the pending-input follow-up loop so Python's tool follow-up safety limit does not suppress user pending input.
- This keeps the new pending input support aligned with Rust's `run_turn` semantics: pending input is a separate reason to continue the turn, not a tool-output retry.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/input_queue.rs#get_pending_input:169`
  - `function:codex-rs/core/src/session/input_queue.rs#has_pending_input:207`
- Rust source confirmed:
  - After sampling, `needs_follow_up = model_needs_follow_up || has_pending_input`.
  - Pending input is checked independently from tool output handling and keeps the turn loop alive.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Pending input is now drained and recorded before applying the Python-only `max_tool_followups` guard.
  - The guard still prevents additional tool/model follow-ups when no pending user input is waiting.
- `tests/test_core_turn_runtime.py`
  - Added coverage that pending input still triggers a follow-up request even with `max_tool_followups=0`.
  - Rechecked the existing tool follow-up limit behavior.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_drains_pending_input_before_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_can_limit_tool_followups`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 43 tests passed.

## 2026-06-01 Model Follow-up Limit Boundary

### Scope

- Tightened the Python user-turn follow-up loop so `max_tool_followups` only limits tool-output-driven continuations.
- This keeps Rust model continuation semantics intact for streamed `completed.end_turn == false` and pending input follow-ups.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/session/input_queue.rs#has_pending_input:207`
- Rust source confirmed:
  - `run_turn` computes `needs_follow_up = model_needs_follow_up || has_pending_input`.
  - `model_needs_follow_up` comes from the sampling result, including streamed `completed.end_turn == false`.
  - There is no Rust tool-follow-up cap in this path; Python's cap is a local guard and should not block independent Rust continuation reasons.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Replaced the generic follow-up counter with `tool_followups`, incremented only when a follow-up request is made with tool response items.
  - `max_tool_followups` now stops only pure tool-output continuations; model-requested and pending-input continuations still proceed.
- `tests/test_core_turn_runtime.py`
  - Added coverage that streamed `completed.end_turn=false` still follows up when `max_tool_followups=0`.
  - Re-ran pending-input and pure tool-limit tests around the same boundary.

### Validation

- `python -m py_compile pycodex/core/turn_runtime.py tests/test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_can_limit_tool_followups tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_pending_input_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_model_followup_bypasses_tool_followup_limit tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_follows_stream_completed_end_turn_false`
  - 4 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 44 tests passed.

## 2026-06-01 Runtime Stream Completed Follow-Up

### Scope

- Connected streamed `Completed.end_turn == false` to the Python turn follow-up loop.
- This preserves the Rust behavior where a completed response can request another model sampling request even when no tool output is pending.
- The implementation intentionally uses the explicit `Completed.end_turn` stream signal rather than every stream output-state `needs_follow_up` bit, because injected Python sampler tests can project tool-call stream events separately from their final `response_items`.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/session/turn.rs#run_sampling_request:926`
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `class:codex-rs/codex-api/src/common.rs#ResponseEvent:72`
- Rust source confirmed:
  - `ResponseEvent::Completed { end_turn, .. }` sets `needs_follow_up = true` when `end_turn` is `Some(false)`.
  - `run_turn` then continues the model loop when `model_needs_follow_up` is true, independent of pending user input.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - `run_user_turn_sampling_from_session` now treats streamed `completed` events with `end_turn: False` as model follow-up requests.
  - Added a focused stream-event helper so this behavior does not accidentally turn stream-only tool projection tests into unbounded follow-up loops.
- `tests/test_core_turn_runtime.py`
  - Added coverage for streamed `completed.end_turn=false` causing a second sampler call and final assistant response collection.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_follows_stream_completed_end_turn_false tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_projects_sampler_stream_events tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer`
  - 3 tests passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler`
  - 196 tests passed.
- `python -m unittest tests.test_exec_local_runtime`
  - 95 tests passed.
- `python -m py_compile pycodex/core/turn_runtime.py pycodex/core/client.py pycodex/core/stream_events_utils.py`
  - Passed.

## 2026-06-01 Runtime Stream Loop Tail Execution

### Scope

- Connected the streamed sampling runtime to the Rust loop-tail ordering after response completion.
- This advances the common runtime path after `ResponseEvent::Completed` and metadata events:
  - sends websocket `response.processed` when the feature is enabled and a response id completed successfully;
  - drains pending in-flight work before token-count emission;
  - emits token-count updates after streamed token usage or rate-limit metadata;
  - emits turn diff after the post-drain token-count/cancellation boundary.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request:1697`
  - `function:codex-rs/core/src/session/turn.rs#drain_in_flight:1663`
  - `function:codex-rs/core/src/session/mod.rs#send_token_count_event:3022`
  - `function:codex-rs/core/src/client.rs#send_response_processed:967`
  - `class:codex-rs/core/src/turn_diff_tracker.rs#TurnDiffTracker:18`
- Rust source confirmed:
  - `try_run_sampling_request` sends `response.processed` only after a successful completed response and only when the websocket response-processed feature is enabled.
  - In-flight work is drained before token counts are sent.
  - Token counts are emitted before returning turn cancellation.
  - Turn diffs are read and emitted after the cancellation boundary.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added stream loop-tail execution for response-processed, drain, token-count, cancellation, and turn-diff actions.
  - Streamed token usage recording now defers token-count emission to the loop tail instead of sending it during usage recording.
  - Tail flags are derived from the current stream apply plans so follow-up sampling requests do not reuse stale completed-response metadata.
- `tests/test_core_turn_runtime.py`
  - Extended the session test double with response-processed, drain, and turn-diff hooks.
  - Tightened streamed completed-usage and metadata tests to assert Rust tail ordering.

### Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_stream_completed_usage_to_session tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_stream_metadata_to_session`
  - 2 tests passed.
- `python -m py_compile pycodex/core/turn_runtime.py pycodex/core/client.py pycodex/core/stream_events_utils.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_http_transport tests.test_core_turn_sampler tests.test_exec_local_runtime`
  - 290 tests passed.
