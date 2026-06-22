# codex-cli src/desktop_app/windows.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/desktop_app/windows.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/desktop_app/windows.rs` |
| Python helper module | `pycodex/cli/app_cmd.py` |
| Python parser integration | `pycodex/cli/parser.py::_run_app_command_windows` |
| Python tests | `tests/test_cli_app_cmd.py` |
| Status | `complete_candidate` |

`src/desktop_app/windows.rs` owns the Windows Codex Desktop open/install flow:
detecting an installed app, launching the AppsFolder target, opening the
installer when needed, falling back to the Microsoft Store URL for the default
installer, and rendering workspace paths without Windows extended prefixes.

The module is now a `complete_candidate`: its module-owned user-visible
messages and local helper behavior are mirrored in Python. Actual pytest
validation is deferred until `codex-cli` functional code is complete, per the
current crate automation rule.

## Completed Behavior Areas

- `display_workspace_path` is mirrored by `display_windows_workspace_path`,
  including:
  - removing `\\?\` from extended local paths,
  - converting `\\?\UNC\server\share` to `\\server\share`, and
  - leaving regular paths unchanged.
- Installed app detection keeps the Rust command shape:
  `powershell.exe -NoProfile -Command "Get-StartApps -Name 'Codex' | Select-Object -First 1 -ExpandProperty AppID"`.
- Installed app launch keeps the Rust AppsFolder target shape:
  `shell:AppsFolder\<app_id>`.
- Explorer launch is treated as a best-effort handoff: non-zero process status
  is not a module-level failure, matching Rust's `open_shell_target`.
- The installed-app path prints `Opening Codex Desktop...` followed by
  `In Codex Desktop, open workspace ...`.
- The installer path prints `Codex Desktop not found; opening Windows
  installer...`, opens the selected installer URL, falls back to the Microsoft
  Store URL only for the default installer, and prints
  `After installing Codex Desktop, open workspace ...`.

## Rust Test Inventory

The Rust module currently contains three local tests:

- `display_workspace_path_removes_windows_extended_prefix`
- `display_workspace_path_preserves_unc_prefix`
- `display_workspace_path_leaves_regular_paths_unchanged`

They are covered by:

- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_display_windows_workspace_path_matches_rust_extended_prefix_handling`

## Intentional Adaptation

Rust uses `tokio::process::Command` and Windows-only APIs. Python keeps the
same command shapes in `pycodex/cli/parser.py` and exposes only the pure
workspace display helper from `pycodex/cli/app_cmd.py` for focused parity
coverage.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
