# 2026-06-02 turn runtime timing lifecycle

## Scope

- Continued the core runtime path from Rust `codex-rs/core/src/turn_timing.rs`
  into Python `run_user_turn_sampling_from_session`.
- Focused on common user-facing lifecycle metadata emitted through
  `task_started` and `task_complete` events.

## Behavior

- Python runtime now calls `turn_timing_state.mark_turn_started()` when emitting
  turn-start lifecycle events.
- Python runtime now calls `turn_timing_state.completed_at_and_duration_ms()`
  before emitting turn-complete lifecycle events.
- The generated values are copied onto the turn context so existing
  `TurnStartedEvent` and `TurnCompleteEvent` construction includes
  `started_at`, `completed_at`, `duration_ms`, and previously wired
  `time_to_first_token_ms`.
- Sessions without a timing state continue to work with the existing optional
  context fields.

## Target files

- `pycodex/core/turn_runtime.py`
- `tests/test_core_turn_runtime.py`

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_ttft_from_stream_events`
- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_turn_timing`
- `python -m unittest tests.test_core_session_runtime`
- `python -m unittest tests.test_local_http_core_smoke_suite`
