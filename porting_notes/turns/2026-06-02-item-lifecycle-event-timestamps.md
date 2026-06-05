# 2026-06-02 item lifecycle event timestamps

## Upstream slice

- Used the upstream graph to follow the core stream/session path through:
  - `codex-rs/core/src/session/mod.rs#emit_turn_item_started`
  - `codex-rs/core/src/session/mod.rs#emit_turn_item_completed`
- Confirmed from Rust source that both lifecycle events stamp `now_unix_timestamp_ms()`.
- `emit_turn_item_completed` also records TTFM before sending the event; that timing hook was already ported in the prior slice.

## Python changes

- Updated `pycodex.core.client._item_lifecycle_event` to stamp real millisecond timestamps.
- `item_started` now sets `started_at_ms`; `item_completed` now sets `completed_at_ms`.
- Kept the unused opposite timestamp field at `0` for compatibility with existing Python event dictionaries.

## Validation

- `python -m unittest tests.test_core_turn_runtime`
- Direct client assertion:
  - fixed `pycodex.core.client.time.time`
  - verified started/completed lifecycle events map to `1234567` ms in the matching field only

## Notes

- `python -m pytest tests/test_core_client.py` could not run in the current bare Python environment because `pytest` is not installed.

