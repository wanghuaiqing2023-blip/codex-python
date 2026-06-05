# Non-workspace Rust package inventory

This file records Rust `Cargo.toml` packages found under `codex/` that are not listed as members of the primary upstream workspace at `codex/codex-rs/Cargo.toml`.

These packages are intentionally kept separate from `PORTING_CRATE_ALIGNMENT.md`, which tracks the 113 official workspace crates. This separation keeps the main crate alignment table strict while still making non-workspace Rust packages visible for later investigation.

## Scope rule

- `PORTING_CRATE_ALIGNMENT.md`: authoritative inventory for `codex/codex-rs` workspace members.
- This file: side inventory for Rust packages present in the repository but not part of that workspace.
- Entries here do not imply active implementation priority.
- Test-support crates should usually map to Python test support only, not runtime packages.

## Inventory

| Rust package path | Category | Suggested Python target | Status | Notes |
|---|---|---|---|---|
| `codex/codex-rs/app-server/tests/common` | test_support | `tests/support/app_server_common` | candidate | Test helper package for app-server tests; not a runtime crate alignment target. |
| `codex/codex-rs/chatgpt` | non_workspace_package | `pycodex/chatgpt` | candidate | Present under `codex-rs` but not listed in the primary workspace. Needs source-level confirmation before runtime alignment. |
| `codex/codex-rs/core/tests/common` | test_support | `tests/support/core_common` | candidate | Test helper package for core tests; should inform Python parity tests rather than runtime package structure. |
| `codex/codex-rs/mcp-server/tests/common` | test_support | `tests/support/mcp_server_common` | candidate | Test helper package for mcp-server tests; extension area is deferred unless needed by core compatibility. |
| `codex/codex-rs/message-history` | non_workspace_package | `pycodex/message_history` | candidate | Present under `codex-rs` but not listed in the primary workspace. Needs source-level confirmation before runtime alignment. |
| `codex/codex-rs/windows-sandbox-rs` | non_workspace_package | `pycodex/windows_sandbox_rs` | candidate | Present under `codex-rs` but not listed in the primary workspace. Likely platform-specific; confirm before implementation. |
| `codex/tools/argument-comment-lint` | developer_tool | `tools/argument_comment_lint` | candidate | Repository developer tool; not part of Codex runtime behavior parity. |

## Follow-up policy

Before moving any entry from this file into the active implementation plan:

1. Confirm why it is outside the primary workspace.
2. Read its `Cargo.toml` and relevant source files.
3. Decide whether it affects common user-facing Codex behavior.
4. If runtime-relevant, either add a dedicated Python package target or document why a compatibility shim is sufficient.
5. If test-only, map it to Python test support and cite the Rust test package in test provenance comments.