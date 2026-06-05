# 2026-06-01 Stream Reasoning Item Constructors

## Graph-selected slice

- Upstream graph nodes used as navigation:
  - `codex-rs/protocol/src/models.rs#ResponseItem`
  - `codex-rs/protocol/src/items.rs#ReasoningItem`
  - `codex-rs/core/src/stream_events_utils.rs`
  - `codex-rs/core/src/event_mapping.rs`
- The slice advances `model stream item -> reasoning/assistant turn item -> event mapping -> final recording` behavior.

## Rust source checked

- `codex/codex-rs/protocol/src/models.rs`
- `codex/codex-rs/protocol/src/items.rs`

## Python changes

- Added `ResponseItem.reasoning(...)` as a standard-library-only convenience constructor over the existing Python reasoning fields.
- Extended `TurnItem.reasoning(...)` to accept either an existing `ReasoningItem` or Rust-shaped `(id, summary_text, raw_content)` arguments.
- Removed a test dependency on `MessagePhase.POST_COMPACT`, which is not present in Rust `codex_protocol::models::MessagePhase`; the tested path uses finalized facts and does not depend on that phase value.

## Validation

- `python -m unittest tests.test_core_stream_events_utils`
  - Passed: 106 tests.
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_core_turn_runtime`
  - Passed: 198 tests.

## Follow-up debt

- Broader unittest discovery still has failures outside this slice, especially in multi-agent v1/v2 assertion drift and other non-core/peripheral areas.
- `PORTING_STATUS.md` is currently deleted in the worktree; this turn intentionally did not recreate it.
