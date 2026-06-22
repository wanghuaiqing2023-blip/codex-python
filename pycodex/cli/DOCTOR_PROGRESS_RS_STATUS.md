# codex-cli src/doctor/progress.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/progress.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/progress.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/progress.rs` owns doctor progress visibility and progress lifecycle
surface. The behavior contract that affects Python CLI parity is the selection
rule for showing transient stderr progress while preserving JSON/stdout
cleanliness.

## Covered Behavior Areas

- Rust `should_show_progress` is mirrored by
  `pycodex.cli.doctor_updates._should_show_doctor_progress`.
- JSON output is quiet so stdout remains parseable JSON.
- Non-TTY stderr is quiet.
- `TERM=dumb` is quiet.
- Human output on a TTY with a non-dumb terminal shows progress.

## Rust Test Inventory

The Rust module currently contains 4 named test functions:

- `progress_is_quiet_for_json`
- `progress_is_quiet_for_non_tty`
- `progress_is_quiet_for_dumb_terminal`
- `progress_is_shown_for_human_tty_output`

All 4 local Rust tests are reconciled by
`tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_progress_visibility_matches_rust`.

## Intentional Adaptation

Rust `DoctorProgress`, `QuietProgress`, and `StderrProgress` are lifecycle and
terminal-rendering implementation details. Python records the user-visible
selection contract here; exact carriage-return stderr rendering is not promoted
as an independent module requirement before crate-level validation.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
