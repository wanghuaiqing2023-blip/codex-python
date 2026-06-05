# Raw response.completed end_turn follow-up parity

## Upstream slice

- Graph-selected path: `codex-rs/core/src/session/turn.rs#try_run_sampling_request` consumes `ResponseEvent::Completed` from the Responses stream.
- Rust source confirmed in `codex-rs/codex-api/src/sse/responses.rs`: raw SSE `"response.completed"` is parsed from `event.response` into `ResponseEvent::Completed { response_id, token_usage, end_turn }`.
- In the turn loop, `end_turn == Some(false)` means the model expects another sampling request, even when no tool output is pending.

## Python work

- Updated `pycodex/core/turn_runtime.py` so `_stream_completed_end_turn_needs_followup` uses the same completed-event helpers as the stream dispatch planner.
- The runtime now treats both normalized `{"type": "completed", ...}` and raw `{"type": "response.completed", "response": {...}}` events as completed events for `end_turn` follow-up decisions.
- Added a regression test proving raw `response.completed` with `end_turn: false` triggers a second model request and preserves the raw response id in the completed event apply plan.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_follows_raw_response_completed_end_turn_false tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_follows_stream_completed_end_turn_false tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_applies_raw_response_completed_usage_to_session`
  - Result: 3 tests OK.
- `python -m unittest tests.test_core_turn_runtime tests.test_core_http_transport tests.test_exec_local_runtime`
  - Result: 292 tests OK.

## Deferred

- Full live transport coverage remains broader than this slice. This turn only closes the runtime semantic gap once raw Responses stream events reach the Python core.
