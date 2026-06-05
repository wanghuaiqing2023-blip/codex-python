# 2026-06-02 function-call arguments delta stream alias

## Scope

- Used the upstream dependency graph to continue along the core
  `session/turn.rs -> try_run_sampling_request -> stream event handling` path.
- Confirmed from `codex-rs/core/src/session/turn.rs` that Rust handles
  `ResponseEvent::ToolCallInputDelta` as part of the main sampling stream loop.

## Behavior

- Added a Python stream-event alias for
  `response.function_call_arguments.delta` so the generic sampling event planner
  recognizes function-call argument deltas.
- Preserved Rust's user-visible behavior for ordinary function calls: when there
  is no active custom-tool argument diff consumer, the delta is recognized but
  does not emit a client tool-input-delta event.

## Target files

- `pycodex/core/stream_events_utils.py`
- `tests/test_core_stream_events_utils.py`

## Validation

- `python -m unittest tests.test_core_stream_events_utils`
- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_http_transport`
