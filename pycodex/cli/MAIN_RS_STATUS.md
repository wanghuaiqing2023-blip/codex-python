# codex-cli src/main.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/main.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/main.rs` |
| Python parser/dispatch module | `pycodex/cli/parser.py` |
| Python command surface spec | `pycodex/cli/spec.py` |
| Python feature helpers | `pycodex/cli/features.py` |
| Python app-exit helpers | `pycodex/cli/app_exit.py` |
| Python tests | `tests/test_cli_parser.py`, `tests/test_cli_app_exit.py` |
| Status | `complete_candidate` |

`src/main.rs` owns the top-level Codex CLI parser and dispatch shell:
`MultitoolCli`, `Subcommand`, completion dispatch, app-exit formatting,
root feature toggles, root `--strict-config` support rules, root remote-mode
guards, and the feature-management command surface.

Subcommand internals remain separate module or crate boundaries. In particular,
`exec`, `review`, TUI, app-server, exec-server, MCP, plugin, marketplace,
remote-control, login, doctor, desktop-app, sandbox backends, cloud tasks,
responses proxy, and stdio-to-UDS runtime behavior are not promoted through
this file unless they are only top-level parser/guard behavior owned by
`main.rs`.

## Completed Behavior Areas

- Top-level command names, aliases, hidden commands, and visible command help
  inventory are represented by `pycodex/cli/spec.py`.
- Top-level parser dispatch, root option parsing, root feature-toggle folding,
  and command help surfaces are represented by `pycodex/cli/parser.py`.
- Root `--strict-config` support/rejection mirrors the Rust command allowlist
  and app-server subcommand rejection behavior.
- Root `--remote` and `--remote-auth-token-env` rejection rules for
  non-interactive subcommands mirror the Rust guard shape.
- Completion command shell selection is represented by the Python completion
  shim.
- Feature command parsing, feature validation, root feature-toggle override
  generation, stage labels, list formatting, and config edit shims are
  represented by `pycodex/cli/features.py`.
- App-exit token usage, resume hint, fatal error, update-action forwarding, and
  update-action command output are represented by `pycodex/cli/app_exit.py`.

## Rust Test Inventory

The Rust module contains local tests for:

- exec-server remote auth host validation and config loading support
- profile-v2 parsing and subcommand allow/reject rules
- exec resume output flag placement and dangerous-bypass conflicts
- debug prompt input and debug models parsing
- plugin, marketplace, update, sandbox, and removed top-level command parsing
- app-exit formatting and resume/fork flag merging
- app-server analytics, transport, daemon/proxy parsing, and websocket auth flags
- root `--strict-config` allow/reject rules
- root remote-mode and remote-auth-token-env allow/reject rules
- remote auth token env var reading
- feature command parsing and feature toggle validation

These are represented by existing Python coverage in:

- `tests/test_cli_parser.py` for parser, dispatch, strict-config, remote-mode,
  completion, feature toggles, feature command, exec-server surface, app-server
  parser surface, resume/fork flag merging, sandbox/update/plugin/marketplace
  command surfaces, and removed command guards.
- `tests/test_cli_app_exit.py` for app-exit formatting and update-action
  forwarding.

## Remaining Gaps

- No known `src/main.rs`-owned top-level parser/helper gap remains.
- Deep runtime behavior for subcommands continues to be tracked by their owning
  crates/modules rather than this top-level CLI entry module.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
