# codex-cli src/doctor/updates.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/updates.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/updates.rs` |
| Python modules | `pycodex/cli/doctor_updates.py`, `pycodex/cli/update_action.py`, `pycodex/cli/update_versions.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/updates.rs` owns the doctor update diagnostic: startup-update
preference detail emission, version-cache detail parsing, update-action labels,
latest-version probing, npm update target consistency, and semver comparison.

## Covered Behavior Areas

- Rust `updates_check` is represented by `doctor_updates_check` and
  `doctor_updates_check_from_config`, with explicit injection points for version
  file, command runner, latest-version success, and latest-version failure.
- Rust `push_cached_version_details` is represented by
  `push_cached_version_details` and `cached_version_details`, including missing
  cache, read failures, parse failures, cached latest version, last checked
  timestamp, and dismissed version details.
- Rust `push_latest_version_details` and probe-error detail helpers are
  represented by `push_latest_version_details`,
  `latest_version_details`, `push_latest_version_probe_error_details`, and
  `latest_version_probe_error_details`.
- Rust `update_action_label` is represented by `update_action_label`, covering
  npm, bun, brew, standalone, and manual/unknown install contexts.
- Rust `fetch_latest_version`, `fetch_latest_github_release_version`,
  `fetch_homebrew_cask_version`, and `http_get_json` are represented with
  injectable JSON and command runners.
- Rust `is_newer` / `parse_version` semantics are represented by
  `pycodex/cli/update_versions.py`.
- Rust npm-root target consistency branches are represented by
  `NpmRootCheck`, `npm_global_root_check`, and `build_doctor_update_check`.

## Rust Test Inventory

The Rust module currently contains 2 named local test functions:

- `is_newer_compares_plain_semver`
- `update_action_labels_install_contexts`

Both local Rust tests are reconciled by:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_latest_version_details_reports_newer_version`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_latest_version_details_reports_not_older_for_equal_older_or_unknown`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_update_action_label_matches_rust_install_contexts`

Additional local parity coverage:

- version-cache detail missing/valid/parse-error/read-error branches.
- latest-version success and probe-error detail branches.
- default latest-version fetch dispatch by update action.
- GitHub `rust-v` tag stripping and unexpected-tag rejection.
- Homebrew cask `version` field extraction.
- doctor update check assembly from config and install context.
- npm target match, mismatch, missing package root, and unavailable npm branches.

## Intentional Adaptation

Rust performs live HTTP probing through reqwest. Python keeps the observable
update-diagnostic contract while using injectable fetch/JSON/command runners for
deterministic parity checks. The actual network path remains dependency-light
and standard-library first.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
