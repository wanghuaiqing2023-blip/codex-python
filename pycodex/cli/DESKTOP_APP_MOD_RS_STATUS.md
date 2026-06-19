# codex-cli src/desktop_app/mod.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/desktop_app/mod.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/desktop_app/mod.rs` |
| Python parser integration | `pycodex/cli/parser.py::_run_app_command` |
| Sibling Rust modules | `desktop_app/mac.rs`, `desktop_app/windows.rs` |
| Related Python helpers | `pycodex/cli/app_cmd.py`, platform app runners in `pycodex/cli/parser.py` |
| Python tests | `tests/test_cli_parser.py`, `tests/test_cli_app_cmd.py` |
| Status | `complete_candidate` |

`src/desktop_app/mod.rs` owns only the current-OS dispatch boundary for the
Codex Desktop open/install flow. On macOS it delegates to
`mac::run_mac_app_open_or_install`; on Windows it delegates to
`windows::run_windows_app_open_or_install`.

The module is now a `complete_candidate`: the dispatch contract is mirrored by
Python's app command runner, while macOS and Windows installer/open details stay
in their own module boundaries. Actual pytest validation is deferred until
`codex-cli` functional code is complete, per the current crate automation rule.

## Completed Behavior Areas

- The Rust macOS dispatch branch is represented by
  `pycodex/cli/parser.py::_run_app_command` selecting
  `_run_app_command_macos` when `sys.platform == "darwin"`.
- The Rust Windows dispatch branch is represented by
  `pycodex/cli/parser.py::_run_app_command` selecting
  `_run_app_command_windows` when `sys.platform.startswith("win")`.
- Workspace and download URL inputs are carried from the app command parser
  into the selected platform runner.
- Non-macOS/non-Windows Python execution returns success without launching,
  matching the fact that this Rust module only provides
  `run_app_open_or_install` on macOS and Windows targets.

## Rust Test Inventory

The Rust module currently contains no local `#[test]` functions.

The dispatch contract is reconciled by existing Python coverage:

- `tests/test_cli_parser.py::CliParserTests::test_parse_app_accepts_path_and_download_url`
- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_app_command_defaults_match_rust_cli_struct`
- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_workspace_for_app_command_canonicalizes_existing_path`
- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_workspace_for_app_command_preserves_missing_path`

## Intentional Adaptation

Rust uses target-specific `cfg` gates in `desktop_app/mod.rs`. Python performs
runtime platform dispatch in `pycodex/cli/parser.py` because the same package is
importable on every supported host.

This status file does not claim the macOS installer/open implementation in
`desktop_app/mac.rs` or the Windows installer/open implementation in
`desktop_app/windows.rs`; those remain separate Rust module boundaries.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
