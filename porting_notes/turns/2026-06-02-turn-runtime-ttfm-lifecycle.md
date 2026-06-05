# 2026-06-02 turn runtime TTFM lifecycle

## Upstream slice

- Checked Rust `codex-rs/core/src/session/mod.rs`.
- Rust records TTFM from `Session::emit_turn_item_completed` before sending `ItemCompleted`.
- The telemetry metric name is `codex.turn.ttfm.duration_ms`.

## Python changes

- Added runtime TTFM recording for completed `TurnItem` events in `pycodex.core.turn_runtime`.
- Added a response-item fallback so non-streamed assistant messages can still record TTFM once.
- Kept telemetry optional and dependency-free; sessions without `record_duration` continue normally.

## Validation

- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_turn_timing`

