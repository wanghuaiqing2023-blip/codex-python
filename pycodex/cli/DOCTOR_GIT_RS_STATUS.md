# codex-cli src/doctor/git.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/git.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/git.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/git.rs` owns the doctor Git/environment check: Git discovery,
selected executable metadata, repository metadata, optional detail filtering,
branch normalization, `.git` entry summaries, command-output normalization, and
old Git for Windows warnings.

## Covered Behavior Areas

- Rust `git_check` is represented by `doctor_git_check` with injectable command
  runner and `GitCheckInputs`.
- Rust `git_check_from_inputs` detail, summary, warning, and remediation
  construction is mirrored.
- Rust `git_summary`, `normalized_branch`, `command_output_text`,
  `git_entry_summary`, `old_windows_git_warning`, and `parse_git_version` have
  Python helper equivalents.
- Empty branch and empty `core.fsmonitor` values are omitted.
- `HEAD` branches are displayed as `detached HEAD`.
- Old Git for Windows and `msysgit` warning branches are represented.
- No-Git/no-repo remains an ok check with `git executable not found`.

## Rust Test Inventory

The Rust module currently contains 5 named test functions:

- `parses_git_for_windows_version`
- `classifies_old_windows_git`
- `warns_when_git_repo_has_no_git_executable`
- `warns_when_selected_git_cannot_report_version`
- `reports_git_candidates_and_repo_metadata`

All 5 local Rust tests are reconciled by:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_git_parse_windows_version_matches_rust`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_git_check_warns_for_old_windows_git`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_git_check_warns_for_msysgit`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_git_check_warns_for_repo_without_git_executable`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_git_check_warns_when_selected_git_cannot_run`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_git_check_reports_git_metadata_from_inputs`

Additional local parity coverage:

- detached HEAD normalization.
- empty branch omission.
- empty `core.fsmonitor` omission.
- command output text normalization.
- `.git` entry directory, gitfile, plain file, and missing cases.
- no-Git/no-repo ok summary.

## Intentional Adaptation

Rust uses Tokio process execution with a two-second timeout. Python keeps the
same observable command-result contract through an injectable command runner;
exact async process scheduling is treated as implementation detail until
crate-level validation.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
