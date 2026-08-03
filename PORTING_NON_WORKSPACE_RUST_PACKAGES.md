# Cargo adjunct and non-member package inventory

This compatibility-named file records Rust packages that are not ordinary
top-level members of `codex/codex-rs/Cargo.toml`, plus repository tools outside
that Cargo workspace.

The parity Harness inventories both workspace members and local path
dependencies. Therefore the Rust packages under `codex/codex-rs` listed below
are now first-class active scopes in
`parity_harness/contracts/workspace.json`; they are no longer untracked
porting candidates.

## Scope rule

- `parity_harness/contracts/workspace.json` is authoritative for every
  Harness-managed Rust package and its Python owner.
- Test-support crates map to Python test support, not runtime packages.
- Repository developer tools outside the Rust workspace remain side inventory
  unless explicitly added to the porting scope.

## Inventory

| Rust package path | Harness scope | Python owner | Project status |
|---|---|---|---|
| `codex/codex-rs/app-server/tests/common` | `app_test_support` | `tests/support/app_test_support` | accepted |
| `codex/codex-rs/chatgpt` | `chatgpt` | `pycodex/chatgpt` | accepted |
| `codex/codex-rs/core/tests/common` | `core_test_support` | `tests/support/core_test_support` | accepted |
| `codex/codex-rs/mcp-server/tests/common` | `mcp_test_support` | `tests/support/mcp_test_support` | accepted |
| `codex/codex-rs/message-history` | `message-history` | `pycodex/message_history` | accepted |
| `codex/codex-rs/windows-sandbox-rs` | `windows-sandbox` | `pycodex/windows_sandbox` | accepted |
| `codex/tools/argument-comment-lint` | not Harness-managed | none | repository developer tool |

## Follow-up policy

For the Harness-managed entries, use their workspace scope, accepted
contracts, module documentation, and Rust-derived tests. Do not maintain a
second status here independently of `workspace.json`.

Before adding a repository developer tool to the porting scope, confirm its
runtime relevance, assign an explicit Rust/Python owner, add it to the
executable workspace contract, and provide Rust-derived tests.
