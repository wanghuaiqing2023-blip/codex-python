# protocol/event_mapping.rs status

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/event_mapping.rs`

Python module: `pycodex/app_server_protocol/event_mapping.py`

Status: implemented, pending full crate validation.

Covered contract:

- `item_event_to_server_notification` for the Rust module's stateless one-to-one projections from selected core `EventMsg` variants into v2 `ServerNotification` payloads.
- Dynamic tool response, collaboration tool-call lifecycle events, streaming text/plan/reasoning deltas, item lifecycle events, patch updates, command execution lifecycle/output deltas, and terminal interaction notifications.
- Rust test anchors mirrored by smoke checks: `collab_resume_begin_maps_to_item_started_resume_agent`, `collab_resume_end_maps_to_item_completed_resume_agent`, and `exec_command_output_delta_maps_to_command_execution_output_delta`.

Notes:

- `protocol/common.rs::ServerNotification` is still an adjacent module boundary, so this module returns the existing Python compatibility facade from `item_builders.py`. Full JSON-RPC method serialization remains owned by `common.rs`.
- Neighboring core protocol payloads are accepted as typed Python events, mappings, or compatible duck-typed objects to keep this module independent of downstream runtime orchestration.
