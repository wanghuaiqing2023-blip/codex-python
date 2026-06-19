# codex-cli src/doctor/system.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/system.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/system.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/system.rs` owns the doctor system/environment check: OS metadata,
OS language detection, locale environment details, and the fixed locale detail
ordering from `LOCALE_ENV_VARS`.

## Covered Behavior Areas

- Rust `system_check` is represented by `doctor_system_check`.
- Rust `SystemCheckInputs::detect` is adapted through Python platform/locale
  detection plus injectable `SystemCheckInputs` for parity tests.
- Rust `system_check_from_inputs` detail and summary construction is mirrored:
  `os`, `os type`, `os version`, `os language`, and locale env details.
- Locale env details preserve Rust `LOCALE_ENV_VARS` order:
  `LC_ALL`, `LC_CTYPE`, then `LANG`.
- Missing OS language produces the Rust summary/detail text
  `OS language unavailable` / `os language: unavailable`.

## Rust Test Inventory

The Rust module currently contains 2 named test functions:

- `system_check_reports_os_language_and_locale_env`
- `system_check_handles_missing_os_language`

Both local Rust tests are reconciled by:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_system_check_reports_os_language_and_locale_env`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_system_check_handles_missing_os_language`

Additional local parity coverage:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_system_check_reports_locale_env_in_rust_order`

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
