# codex-cli src/desktop_app/mac.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/desktop_app/mac.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/desktop_app/mac.rs` |
| Python helper module | `pycodex/cli/app_cmd.py` |
| Python parser integration | `pycodex/cli/parser.py::_run_app_command_macos` |
| Python tests | `tests/test_cli_app_cmd.py` |
| Status | `complete_candidate` |

`src/desktop_app/mac.rs` owns the macOS Codex Desktop open/install flow:
finding an existing app bundle, opening it with `open -a`, selecting an
architecture-specific DMG URL, downloading the DMG, mounting it, locating the
`.app` bundle, installing it into an Applications directory, detaching the DMG,
and parsing `hdiutil attach` output.

This module is `complete_candidate`: Python mirrors the Rust macOS open/install
behavior contract, including existing app discovery, native DMG download,
mount, app-bundle discovery, Applications-directory install attempts, detach
warnings, and workspace launch. Full pytest validation is deferred until
`codex-cli` functional code is complete, per the current crate automation rule.

## Completed Behavior Areas

- `parse_hdiutil_attach_mount_point` is mirrored by
  `parse_hdiutil_attach_mount_point`.
- Existing app discovery candidates are represented by the Python macOS runner:
  `/Applications/Codex.app` and `$HOME/Applications/Codex.app`.
- Existing app launch keeps the Rust message shape:
  `Opening Codex Desktop at ...` followed by `Opening workspace ...`.
- Architecture-based default installer URL selection is represented by the
  Python macOS runner's arm64/aarch64, Rosetta `sysctl.proc_translated`, and
  `hw.optional.arm64` versus x64 URL choice.
- Candidate app paths are mirrored by `candidate_codex_app_paths`.
- Candidate installation directories are mirrored by `candidate_applications_dirs`.
- The `open -a`, `curl`, `hdiutil attach`, `hdiutil detach`, and `ditto`
  command shapes are mirrored by `mac_*_command` helpers.
- The temporary installer directory prefix and downloaded DMG filename are
  mirrored by `mac_app_install_plan`.
- The macOS runner now executes the native installer chain instead of opening
  the installer URL in a browser: `curl` download, `hdiutil attach`, mounted
  `.app` discovery, `ditto` install attempts, best-effort `hdiutil detach`,
  and launch from the installed app.
- Mounted-volume `.app` discovery is mirrored by `find_codex_app_in_mount`,
  including direct `Codex.app` priority before generic `.app` bundles.

## Rust Test Inventory

The Rust module currently contains two local tests:

- `parses_mount_point_from_tab_separated_hdiutil_output`
- `parses_mount_point_with_spaces`

They are covered by:

- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_parse_hdiutil_attach_mount_point_matches_rust`
- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_mac_app_command_shapes_match_rust`
- `tests/test_cli_app_cmd.py::CliAppCommandTests::test_find_codex_app_in_mount_matches_rust_priority`

## Remaining Gaps

- No known module-owned functional gaps remain.
- Focused pytest validation is intentionally deferred until `codex-cli`
  functional code is complete, per the current crate automation instruction.

## Completion Criteria

Before final promotion from `complete_candidate`:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
