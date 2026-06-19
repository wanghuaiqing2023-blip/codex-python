# codex-cli src/plugin_cmd.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/plugin_cmd.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/plugin_cmd.rs` |
| Python parser/runner module | `pycodex/cli/parser.py` |
| Python tests | `tests/test_cli_parser.py` |
| Status | `complete_candidate` |

`src/plugin_cmd.rs` owns the CLI-facing `codex plugin` command shell:
`add`, `list`, `marketplace`, and `remove`, including selector parsing,
user-facing add/list/remove messages, and snapshot-load issue formatting.
Deep plugin installation, marketplace discovery, Git snapshot refresh, and
plugin cache behavior delegate to `codex-core-plugins`, which is an extension
area outside the active core runtime priority.

Python keeps this module as a compatibility shim: local marketplace plugin
add/list/remove flows are represented, and extension-heavy marketplace/cache
behavior remains documented debt rather than expanded in `codex-cli`.

## Completed Behavior Areas

- `plugin add <PLUGIN>@<MARKETPLACE>` and `plugin remove
  <PLUGIN>@<MARKETPLACE>` selector parsing is represented.
- `--marketplace` / `-m` is supported for explicit marketplace selection.
- Rust selector errors are mirrored: a bare plugin name requires
  `--marketplace`, and conflicting `PLUGIN@MARKETPLACE` plus `--marketplace`
  is rejected.
- `plugin list [--marketplace MARKETPLACE]` parser surface is represented.
- Local marketplace plugin add/list/remove compatibility behavior is present in
  `pycodex/cli/parser.py`.
- Deep extension behavior remains outside this module and is intentionally
  deferred to `codex-core-plugins` parity work.

## Rust Test Inventory

The Rust module currently has no local `#[cfg(test)]` tests, so parity evidence
comes from source-level behavior contracts:

- `parse_plugin_selection`
- `PluginSubcommand::{Add,List,Marketplace,Remove}`
- `AddPluginArgs`, `ListPluginsArgs`, and `RemovePluginArgs`
- user-facing add/list/remove message shapes

Python coverage and evidence:

- `tests/test_cli_parser.py::CliParserTests::test_parse_plugin_add_accepts_marketplace_short_flag_and_explicit_marketplace_match`
- `tests/test_cli_parser.py::CliParserTests::test_plugin_selector_requires_marketplace_like_rust`
- `tests/test_cli_parser.py::CliParserTests::test_plugin_selector_rejects_marketplace_mismatch_like_rust`
- `tests/test_cli_parser.py::CliParserTests::test_plugin_help_text_for_subcommands`

## Remaining Gaps

- No known module-owned parser/selector gaps remain.
- Full plugin installation/cache and marketplace snapshot side effects remain
  `codex-core-plugins` extension behavior and are not claimed by this
  `codex-cli` module.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
