# app-server-protocol `protocol/v2/collaboration_mode.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/collaboration_mode.rs`

Python target: `pycodex/app_server_protocol/collaboration_mode.py`

Status: implemented module contract.

## Covered Rust items

- `CollaborationModeListParams`
- `CollaborationModeMask`
- `From<CoreCollaborationModeMask> for CollaborationModeMask` via
  `CollaborationModeMask.from_core_mask()`
- `CollaborationModeListResponse`

## Notes

- The Rust serde shape keeps `reasoning_effort` as snake_case despite the
  enclosing struct's camelCase default; Python mirrors this in
  `to_mapping()` and `to_camel_mapping()`.
- Python bridges the core protocol `CollaborationModeMask` sentinel used for
  an absent `reasoning_effort` field into the app-server
  `UNSET_REASONING_EFFORT` sentinel, preserving the Rust
  `Option<Option<ReasoningEffort>>` intent.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/collaboration_mode.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: constructed params/mask/response values, parsed `ModeKind` and
  `ReasoningEffort`, and round-tripped a core collaboration mode mask.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
