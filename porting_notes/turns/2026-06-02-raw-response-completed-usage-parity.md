# Raw response.completed usage parity

## Upstream slice

- Graph-selected path: `codex-rs/core/src/session/turn.rs#try_run_sampling_request` consumes streaming `ResponseEvent::Completed` to drive usage recording, follow-up decisions, response processed notifications, and turn completion.
- Rust source confirmed in `codex-rs/codex-api/src/sse/responses.rs`: raw SSE event `"response.completed"` parses `event.response` into `ResponseCompleted`, then emits `ResponseEvent::Completed { response_id: resp.id, token_usage: resp.usage.map(Into::into), end_turn: resp.end_turn }`.

## Python work

- Updated `pycodex/core/turn_runtime.py` so sampling stream handling accepts both existing normalized completed events and raw Responses API style events:
  - top-level `{"type": "completed", "response_id": ..., "token_usage": ..., "end_turn": ...}`
  - raw `{"type": "response.completed", "response": {"id": ..., "usage": ..., "end_turn": ...}}`
- Added a regression test in `tests/test_core_turn_runtime.py` proving raw `response.completed` records token usage, sends `response_processed`, emits token count, and preserves the completed response id in runtime summary.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_raw_response_completed_usage_to_session tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_stream_completed_usage_to_session`
  - Result: 2 tests OK.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_exec_local_runtime`
  - Result: 321 tests OK.

## Deferred

- This only covers the core turn runtime's already-injected stream event shape. Full HTTP/SSE transport parity remains a separate core-path slice.
