# app-server-protocol `protocol/common.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/common.rs`

Python target: `pycodex/app_server_protocol/common.py`

## Alignment

- Ported the common protocol envelope layer for client requests, client notifications, server requests, and server notifications.
- Added Rust method registries for `ClientRequest`, `ServerRequest`, `ServerNotification`, and `ClientNotification`, including legacy camelCase methods such as `getConversationSummary`, `gitDiffToRemote`, `getAuthStatus`, `fuzzyFileSearch`, `applyPatchApproval`, and `execCommandApproval`.
- Added `ClientRequestSerializationScope` and `ClientRequest.serialization_scope()` for the Rust keyed request families: thread id/path, command exec process, process handle, fuzzy file search session, fs watch id, MCP OAuth server, global, and global shared-read scopes.
- Added JSON-RPC conversion helpers for request/notification wrappers.
- Added fuzzy file search params, result, response, session params/responses, and session notification payloads.
- Reused the existing `AuthMode` and `ServerNotification` facade to avoid duplicating neighboring module behavior.

## Intentional adaptations

- Python treats neighboring v1/v2 request and response payloads as JSON-compatible mappings at this boundary. Their typed payload behavior remains owned by the already ported module files.
- `ServerNotification` remains the small facade used by `item_builders` and `event_mapping`; its method lookup now delegates to the full `SERVER_NOTIFICATION_METHODS` registry from `common.py`.

## Validation

- Checked Python compilation for `common.py`, `item_builders.py`, and package `__init__.py`.
- Focused Rust-derived pytest passed on 2026-06-17:
  `python -m pytest tests/test_app_server_protocol_common.py -q`
  (`5 passed`).
- Package compile closeout passed on 2026-06-17:
  `python -m compileall -q pycodex/app_server_protocol`.

## Remaining

- No known module-scoped functional gaps remain for this module.
