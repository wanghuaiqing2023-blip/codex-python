# codex-cli src/marketplace_cmd.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/marketplace_cmd.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/marketplace_cmd.rs` |
| Python parser/runner module | `pycodex/cli/parser.py` |
| Python tests | `tests/test_cli_parser.py` |
| Status | `complete_candidate` |

`src/marketplace_cmd.rs` owns the CLI-facing `codex plugin marketplace`
subcommand shell: `add`, `list`, `upgrade`, and `remove` argument parsing plus
user-facing command messages. The deep marketplace implementation delegates to
`codex-core-plugins`, which is an extension area outside the current core
runtime priority.

Python intentionally keeps this module as a lightweight compatibility shim:
local marketplace config add/list/remove behavior is present, Git marketplace
upgrade is represented as a config timestamp shim, and deep Git snapshot
refresh/install behavior remains documented extension debt rather than expanded
inside `codex-cli`.

## Completed Behavior Areas

- `plugin marketplace add <SOURCE> [--ref REF] [--sparse PATH...]` parses with
  sparse paths before or after the source, including repeated sparse paths.
- `plugin marketplace upgrade [MARKETPLACE]` accepts zero or one marketplace
  name and rejects extras.
- `plugin marketplace remove <MARKETPLACE>` preserves the marketplace name.
- Python runner compatibility covers local marketplace config add/list/remove
  and a shallow Git-upgrade timestamp path.
- Help text exposes the same subcommand surface.

## Rust Test Inventory

The Rust module currently contains three local parser tests:

- `sparse_paths_parse_before_or_after_source`
- `upgrade_subcommand_parses_optional_marketplace_name`
- `remove_subcommand_parses_marketplace_name`

They are covered or represented by:

- `tests/test_cli_parser.py::CliParserTests::test_parse_plugin_marketplace_add_supports_sparse_and_ref`
- `tests/test_cli_parser.py::CliParserTests::test_parse_plugin_marketplace_upgrade_rejects_extra_arguments`
- `tests/test_cli_parser.py::CliParserTests::test_parse_plugin_marketplace_remove_matches_rust`

## Remaining Gaps

- No known module-owned parser-surface gaps remain.
- Full marketplace add/remove/upgrade side effects for Git snapshots and
  installed roots remain `codex-core-plugins` extension behavior and are not
  claimed by this `codex-cli` module.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
