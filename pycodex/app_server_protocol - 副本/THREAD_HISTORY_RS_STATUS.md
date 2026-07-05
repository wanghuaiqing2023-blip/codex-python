# protocol/thread_history.rs status

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/thread_history.rs`

Python module: `pycodex/app_server_protocol/thread_history.py`

Status: implemented, pending full crate validation.

Covered contract:

- `build_turns_from_rollout_items` and `ThreadHistoryBuilder` public reducer surface.
- Active-turn snapshot/position helpers, explicit turn tracking, active turn start index, reset, finish, and rollout replay entrypoints.
- Core persisted `EventMsg` replay into v2 `Turn` values for user/agent/reasoning items, tool items, dynamic/collab projections, exec/patch/guardian builder-backed items, turn lifecycle events, compaction markers, errors, aborts, rollbacks, and selected response-item hook prompts.
- Upsert-by-item-id behavior for turn items and late turn-scoped command/file items.

Rust test anchors used for light smoke:

- multiple explicit turns with in-progress active turn,
- thread rollback truncation,
- collab resume-end reconstruction,
- late command completion routed back to its original turn.

Notes:

- The module reuses already-ported `item_builders` and `event_mapping` helpers to avoid duplicate exec/patch/collab projection logic.
- Full crate tests remain deferred until `protocol/common.rs` is complete and the crate can be validated as a whole.
