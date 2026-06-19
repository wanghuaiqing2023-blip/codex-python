# codex-cli src/doctor/title.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/title.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/title.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/title.rs` owns the doctor terminal-title diagnostic: configured
title item parsing, alias normalization, invalid-item warnings, activity and
project item detection, project-source selection, display-name extraction, and
project title truncation.

## Covered Behavior Areas

- Rust `terminal_title_check` and `terminal_title_check_from_inputs` are
  represented by `doctor_terminal_title_check`.
- Rust `parse_terminal_title_items` and `terminal_title_item_id` are represented
  by `_parse_terminal_title_items` and `_TERMINAL_TITLE_ITEM_ALIASES`.
- Default items, disabled configuration, duplicate invalid-item de-duplication,
  warning summaries, remediation text, and issue-relevant detail strings are
  mirrored.
- Project title rows are emitted only when a project item is selected.
- Git/project-config/cwd project source/value behavior is represented through
  injectable `TerminalTitleCheckInputs`.
- ASCII truncation shape for long project values mirrors the Rust tests.

## Rust Test Inventory

The Rust module currently contains 7 named test functions:

- `terminal_title_reports_default_items_and_git_project_name`
- `terminal_title_reports_disabled_configuration`
- `terminal_title_reports_project_config_fallback`
- `terminal_title_omits_project_when_project_item_is_not_selected`
- `terminal_title_warns_for_invalid_configured_items`
- `terminal_title_warns_when_all_configured_items_are_invalid`
- `terminal_title_project_value_uses_tui_truncation_shape`

All 7 local Rust tests are reconciled by:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_reports_default_project_name`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_reports_disabled_configuration`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_reports_project_config_fallback`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_omits_project_when_not_selected`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_warns_for_invalid_items`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_warns_when_all_items_invalid`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_warns_for_invalid_items`
  for the ASCII truncation shape in the invalid-items/project fallback path.

Additional local parity coverage:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_terminal_title_check_normalizes_item_aliases`

## Intentional Adaptation

Rust truncates by Unicode grapheme clusters. Python currently records the
ASCII truncation shape used by the Rust test inventory; non-ASCII grapheme
parity remains part of broader crate-level validation if terminal-title Unicode
fixtures are added later.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
