# codex-cli src/doctor/background.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/background.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/background.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/background.rs` owns passive app-server daemon diagnostics: daemon
state directory inspection, settings/PID/update-loop file details, control
socket state, running/not-running/stale summaries, app-server version detail,
persistent/ephemeral mode, and concise probe-error rendering.

## Covered Behavior Areas

- Rust `background_server_check` is represented by
  `doctor_background_server_check`.
- Rust daemon state details are mirrored: state dir, settings file, PID file,
  update-loop PID file, control socket, status, app-server version, and mode.
- Rust `push_file_detail` behavior is represented by `_push_file_detail` for
  file, not-file, missing, and OS-error detail shapes.
- Rust `server_mode` behavior is represented by `_background_server_mode`.
- Rust `SocketStatus` observable branches are represented by ok not-running,
  ok running, and warning stale/unreachable result construction.
- Rust `socket_status` probe behavior is represented by an injectable
  `version_probe` plus `_default_app_server_version_probe`.
- Rust `concise_probe_error` is represented by `_concise_probe_error`,
  including socket-path replacement, whitespace normalization, empty-message
  fallback, and 120-character truncation with ellipsis.

## Rust Test Inventory

The Rust module currently contains 3 named local test functions:

- `not_running_background_server_stays_ok_without_version`
- `running_background_server_reports_app_server_version`
- `failed_version_probe_reports_unavailable`

All 3 local Rust tests are reconciled by:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_background_server_check_reports_not_running`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_background_server_check_reports_running_version`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_background_server_check_warns_for_stale_socket`

Additional local parity coverage:

- default app-server initialize probe request shape and user-agent version
  parsing.
- persistent vs ephemeral mode.
- concise probe-error socket-path replacement, whitespace normalization, and
  truncation.

## Intentional Adaptation

Rust probes the app-server daemon asynchronously through daemon crates. Python
keeps the observable passive doctor contract with an injectable version probe
and a dependency-light standard-library WebSocket path for the default probe.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
