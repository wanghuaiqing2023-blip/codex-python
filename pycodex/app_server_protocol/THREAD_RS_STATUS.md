# protocol/v2/thread.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/thread.rs`

Python module: `pycodex/app_server_protocol/thread.py`

Status: complete for the module-scoped app-server protocol data contract.

## Covered

- Thread start, resume, fork, settings, archive, unsubscribe, elicitation,
  naming, unarchive, metadata, memory, compaction, shell command, guardian
  approval, background-terminal cleanup, and rollback params/responses.
- Thread goal payloads, goal status wire values, goal get/set/clear
  params/responses, and goal notifications.
- `ThreadStatus` tagged variants, active flags, thread source kinds, sort
  keys, sort direction, start source, memory mode, and unsubscribe status.
- Thread list/search/read payloads, loaded-thread listing, injected item
  payloads, turn list payloads, turn item list payloads, and cwd string-or-list
  filters.
- Dynamic tool specs, token usage breakdowns, token usage notifications, and
  thread lifecycle/name/status/archive/context notifications.

## Intentional Adaptations

- Runtime thread storage, session management, subscription state, command
  dispatch, goal orchestration, and background terminal cleanup remain outside
  the protocol module boundary.
- Neighboring `Thread`, `Turn`, `ThreadItem`, and `TurnEnvironmentParams`
  values use the already-ported app-server protocol modules.
- Runtime config/model/sandbox payloads remain JSON-compatible fields where
  their owning Rust modules are outside `protocol/v2/thread.rs`.

## Validation

- `python -m py_compile pycodex/app_server_protocol/thread.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered dynamic tool default/defer serialization,
  `ThreadStatus.active`, goal serialization, thread start/list params,
  `ThreadStartResponse`, token usage payloads, and package exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
