# codex-cli src/app_cmd.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/cli/src/app_cmd.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/app_cmd.rs` |
| Python module | `pycodex/cli/app_cmd.py` |
| Python parser integration | `pycodex/cli/parser.py::_run_app_command` |
| Python tests | `tests/test_cli_app_cmd.py` |
| Status | `complete_candidate` |

`src/app_cmd.rs` owns the Codex Desktop app command argument shape and the
workspace path normalization performed before delegating to the platform
desktop-app launcher.

## Covered Behavior Areas

- Rust `AppCommand::path` defaults to `.`.
- Rust `AppCommand::download_url_override` is optional.
- Existing workspace paths are canonicalized before launch.
- Paths that cannot be canonicalized are preserved unchanged.
- Python parser integration passes the normalized workspace path and optional
  download URL to the platform-specific desktop app launcher.

## Rust Test Inventory

The Rust module currently contains no local `#[test]` functions.

The source contract is reconciled by:

- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_workspace_for_app_command_canonicalizes_existing_path`
- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_workspace_for_app_command_preserves_missing_path`
- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_app_command_defaults_match_rust_cli_struct`

## Intentional Adaptation

Rust gates this module to macOS and Windows and delegates to
`crate::desktop_app::run_app_open_or_install`. Python keeps the small
module-owned argument and path behavior in `pycodex/cli/app_cmd.py`, while
`pycodex/cli/parser.py::_run_app_command` handles platform dispatch. Non-macOS
and non-Windows Python execution returns success without launching, matching the
fact that Rust does not compile this command module on other targets.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
