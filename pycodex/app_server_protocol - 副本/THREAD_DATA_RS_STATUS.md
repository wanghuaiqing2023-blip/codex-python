# protocol/v2/thread_data.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/thread_data.rs`

Python module: `pycodex/app_server_protocol/thread_data.py`

Status: complete for the module-scoped app-server protocol data contract.

## Covered

- `SessionSource` variants and Rust wire mapping, including `appServer` as the
  app-server view of core MCP source and custom/sub-agent payload variants.
- `ThreadSource` snake_case values.
- `GitInfo` with camelCase `originUrl`.
- `Thread` protocol payload fields, path/cwd serialization, optional fork,
  sub-agent metadata, git metadata, title, and nested turns.
- `Turn` protocol payload fields, default `TurnItemsView.full`, nested
  `ThreadItem` values, timestamps, duration, and optional errors.
- `TurnItemsView` wire values.
- `TurnError` payload and string display behavior.

## Intentional Adaptations

- `Thread.status` and `Turn.status` stay JSON-compatible because their owning
  Rust definitions are in `protocol/v2/thread.rs` and `protocol/v2/turn.rs`.
- `CodexErrorInfo` stays JSON-compatible inside `TurnError`; the concrete type
  is owned by `protocol/v2/shared.rs` and can be passed as a mapping.
- `ThreadItem` uses the already-ported `pycodex.app_server_protocol.item`
  protocol type.

## Validation

- `python -m py_compile pycodex/app_server_protocol/thread_data.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered session-source parsing, git info camelCase,
  thread/turn parsing and serialization, nested `ThreadItem`, default
  `TurnItemsView.full`, `TurnError`, and package exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
