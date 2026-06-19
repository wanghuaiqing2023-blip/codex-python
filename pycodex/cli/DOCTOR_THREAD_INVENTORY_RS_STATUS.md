# codex-cli src/doctor/thread_inventory.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/thread_inventory.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/thread_inventory.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/thread_inventory.rs` owns the doctor check that compares rollout
JSONL files with the SQLite thread inventory: file scanning, state DB row
reading, missing/stale/archive-mismatch detection, duplicate detection, source
and provider summaries, scan samples, and warning issue construction.

## Covered Behavior Areas

- Rust `thread_inventory_check` and `thread_inventory_check_for_roots` are
  represented by `doctor_thread_inventory_check`.
- Rust missing state DB behavior is mirrored for the empty ok case and the
  warning cases where rollout files or scan problems exist.
- Rust DB read-error behavior is mirrored with a warning summary and issue.
- Rust parity checks are represented by `_thread_inventory_parity_check`,
  including missing active/archived rows, stale rows, archive mismatches,
  duplicate rollout thread IDs, and duplicate DB paths.
- Rust scan/sample helpers are represented by `_scan_rollout_inventory`,
  `_push_samples`, and related path helpers.
- Rust `source_category` and `count_summary` behavior is represented by
  `_source_category` and `_count_summary`, including the 8-category summary cap.
- Rust warning `DoctorIssue` payloads are mirrored for missing DB, read errors,
  missing/stale/mismatched rows, duplicate entries, and scan issues.

## Rust Test Inventory

The Rust module currently contains 4 named local test functions:

- `thread_inventory_check_ok_when_rollouts_match_db`
- `thread_inventory_check_warns_for_missing_stale_and_mismatched_rows`
- `source_category_coarsens_structured_sources`
- `count_summary_caps_distinct_values`

All 4 local Rust tests are reconciled by:

- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_thread_inventory_check_ok_when_rollouts_match_db`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_thread_inventory_check_warns_for_missing_stale_and_mismatched_rows`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_thread_inventory_check_summarizes_sources_like_rust`
- `tests/test_cli_doctor_updates.py::DoctorUpdateDetailsTests::test_doctor_thread_inventory_count_summary_caps_distinct_values`

Additional local parity coverage:

- no rollout/state DB inventory ok summary.
- `session_meta` ID preference over filename ID.
- empty rollout and malformed JSONL scan errors.
- model provider and structured source summaries.

## Intentional Adaptation

Rust loads rollout items through `codex-rollout` and reads state rows through
`codex-state`. Python keeps the same observable doctor contract using local
JSONL and sqlite readers, while preserving Rust-shaped detail labels, summaries,
and issue payloads.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
