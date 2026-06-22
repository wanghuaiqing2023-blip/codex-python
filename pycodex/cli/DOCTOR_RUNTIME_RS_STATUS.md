# codex-cli src/doctor/runtime.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/runtime.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/runtime.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/runtime.rs` owns process runtime provenance and search-command
readiness diagnostics: running version, platform, install method, build commit,
current executable path, ripgrep command selection, bundled/system provider
classification, and remediation for unverifiable search commands.

## Covered Behavior Areas

- Rust `runtime_check` is represented by `doctor_runtime_check`.
- Rust runtime details are mirrored: version, platform, install method, commit,
  and current executable.
- Rust install-method summary labels are represented by
  `_runtime_install_method_name` plus install-context detection helpers.
- Rust `search_check` is represented by `doctor_search_check`.
- Bundled ripgrep paths are checked as filesystem paths and report file,
  not-file, or missing readiness details.
- System ripgrep commands are probed with `--version`.
- Successful system probes with empty stdout report `rg version unknown`.
- Search warnings use the Rust remediation text:
  `Install ripgrep or repair the bundled Codex package.`
- Rust `search_provider` behavior is represented by
  `_select_rg_command_and_provider` for package-layout and standalone bundled
  paths, otherwise system `rg`.

## Rust Test Inventory

The Rust module currently contains no local `#[test]` functions.

Python parity evidence is source-contract based and covered by:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_runtime_check_reports_process_provenance`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_runtime_check_names_managed_install_methods`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_search_check_verifies_system_rg_version`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_search_check_uses_unknown_version_for_empty_system_rg_output`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_search_check_warns_when_system_rg_cannot_run`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_search_check_verifies_bundled_rg_file`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_search_check_warns_when_bundled_path_is_not_file`

## Intentional Adaptation

Rust obtains platform data from compile-time `env::consts` and probes system
commands with `std::process::Command`. Python derives the same observable fields
from the standard library and keeps command probing injectable for deterministic
parity checks.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
