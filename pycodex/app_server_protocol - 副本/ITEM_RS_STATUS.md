# protocol/v2/item.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/item.rs`

Python module: `pycodex/app_server_protocol/item.py`

Status: complete for the module-scoped app-server protocol contract, with
neighbor-owned runtime payloads intentionally represented as JSON-compatible
mappings.

## Covered

- Command and file-change approval decisions.
- Command actions and memory citation payloads.
- `ThreadItem` tagged protocol payloads and `id()` access.
- Hook prompt fragments.
- Guardian approval review status, risk, authorization, command source, review
  payloads, and tagged review actions.
- Web-search action tagged payloads.
- Command execution, patch apply, MCP tool-call, dynamic tool-call, collab
  tool-call, and collab agent status enums.
- File update changes and patch change tagged payloads.
- Item started/completed, raw response item completed, guardian review
  started/completed, text delta, reasoning delta, terminal interaction, command
  output, file output, and patch-updated notifications.
- Command/file approval request and response payloads.
- Dynamic tool-call params/responses and output content items.
- Request-user-input question/option/answer/response payloads.

## Intentional Adaptations

- Rust conversions from `codex_protocol` and RMCP/core types are not expanded
  into runtime behavior here. The Python module stays at the app-server
  protocol layer and accepts neighbor-owned payloads as JSON mappings.
- Rust tagged enums are represented by `TaggedPayload` subclasses to preserve
  `type` discriminators and camelCase wire fields without creating a Python
  subclass per variant.
- `CommandExecutionRequestApprovalParams.strip_experimental_fields()` mirrors
  the Rust method by clearing `additional_permissions`.

## Validation

- `python -m py_compile pycodex/app_server_protocol/item.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered command actions, thread item ids, lifecycle
  notifications, guardian review notifications, command approval decisions,
  command approval params, patch update notifications, dynamic tool responses,
  request-user-input payloads, and package exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
