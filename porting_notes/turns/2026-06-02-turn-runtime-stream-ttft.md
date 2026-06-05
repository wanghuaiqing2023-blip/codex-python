# 2026-06-02 turn runtime stream TTFT

## Scope

- Continued the graph-guided core path from `codex-rs/core/src/session/turn.rs`
  into `codex-rs/core/src/turn_timing.rs`.
- Confirmed Rust records time-to-first-token from response stream events such as
  assistant text deltas, reasoning deltas, and non-empty output items.

## Behavior

- Connected Python's existing `TurnTimingState` helper to
  `run_user_turn_sampling_from_session`.
- Stream events now update `turn_context.time_to_first_token_ms` when the
  turn context exposes `turn_timing_state`, so the emitted `task_complete`
  event can carry TTFT without callers manually pre-populating it.
- The mapper accepts both normalized Python stream event names and raw Responses
  SSE event names.

## Target files

- `pycodex/core/turn_runtime.py`
- `tests/test_core_turn_runtime.py`

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_ttft_from_stream_events`
- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_turn_timing`
- `python -m unittest tests.test_core_stream_events_utils`
- `python -m unittest tests.test_core_http_transport`
