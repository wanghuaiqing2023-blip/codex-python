# codex-cli src/doctor/output/detail.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/output/detail.rs`.

It intentionally excludes sibling modules under `src/doctor/output/`, such as
`mod.rs` and any higher-level report rendering owned by `src/doctor/output.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/output/detail.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete_candidate` |

`src/doctor/output/detail.rs` has no local Rust `#[test]` functions. Its
completion evidence is therefore based on Rust source anchors plus
Rust-derived Python parity entries in `pycodex/cli/TEST_ALIGNMENT.md`.
It remains a `complete_candidate` until the crate-level functional-code sweep
is done and actual pytest validation is run per the current automation rule.

## Covered Behavior Areas

The existing alignment ledger in `pycodex/cli/TEST_ALIGNMENT.md` records
covered slices for these `src/doctor/output/detail.rs` anchors:

- public detail APIs: `detail_lines`, `detail_value`, `rollout_summary`,
  `rollout_files_and_bytes`, `format_bytes`, `format_count`, and `is_falsy`.
- parsing and value helpers: `parsed_details`, `value`, `numbered_values`,
  `list_items`, `override_names`, `yes_no`, and `display_label`.
- humanization helpers: `humanize_detail`, `humanize_value`,
  `humanize_timestamp`, `shorten_path_prefix`, `home_shortened_path`,
  `middle_truncate`, and `looks_like_path`.
- category renderers: `system_details`, `runtime_details`, `install_details`,
  `git_details`, `title_details`, `config_details`, `state_details`, and
  `generic_details`.
- row assembly helpers: `push_feature_flags`, `push_list_row`,
  `push_database_row`, `push_row_if_present`, and `push_remaining`.
- issue metadata: `attach_issue_metadata`, `issue_expected_for_label`, and
  `issue_remedies`.
- presentation limits and pipeline constants: `LIST_LIMIT`, `PATH_LIMIT`, and
  the `detail_lines` parse-dispatch-metadata-humanize-remedy pipeline.

## Source Anchor Audit

This pass confirms that all important non-test items in the Rust module are
represented by Python helper equivalents under `pycodex/cli/doctor_updates.py`
with `_doctor_detail_*` names or by the detail-line pipeline helper
`_doctor_detail_lines_for_check`.

Intentional adaptations and non-scope notes:

- Python represents Rust `HumanDetail` rows as small tuple/list values in test
  helpers rather than mirroring the enum type exactly.
- Exact terminal report layout is owned by sibling Rust module
  `src/doctor/output.rs`; this status file only tracks detail row production
  and value transformation.
- Current automation defers actual pytest execution until `codex-cli`
  functional code is complete.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
