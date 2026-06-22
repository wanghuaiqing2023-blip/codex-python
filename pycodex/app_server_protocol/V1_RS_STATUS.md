# protocol/v1.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v1.rs`

Python module: `pycodex/app_server_protocol/v1.py`

Status: complete candidate for the module-scoped v1 payload contract.

## Covered

- Initialize payloads: `InitializeParams`, `ClientInfo`,
  `InitializeCapabilities`, and `InitializeResponse`.
- Conversation summary payloads, including untagged rollout-path versus
  conversation-id params and snake-case `ConversationGitInfo`.
- Auth, git-diff, apply-patch approval, exec approval, one-off command,
  saved-config, tools, sandbox-settings, and interrupt response shapes.
- Package-root re-exports matching the Rust crate root's selected
  `protocol::v1` public types.

## Intentional Adaptations

- Python reuses existing core protocol/config classes for `ThreadId`,
  `GitSha`, `ReviewDecision`, `FileChange`, `ParsedCommand`, `SandboxPolicy`,
  `SessionSource`, `TurnAbortReason`, `AskForApproval`, `SandboxMode`,
  reasoning config enums, and forced-login/workspace types.
- Path fields are represented as `pathlib.Path` internally and serialized as
  strings in camelCase mappings.

## Validation

- Light validation only: `py_compile`, v1 mapping smoke, and package export
  smoke.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
