# codex-cli src/doctor/output.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/doctor/output.rs`.

It intentionally excludes sibling output detail logic in
`src/doctor/output/detail.rs`, which is tracked separately in
`pycodex/cli/DOCTOR_OUTPUT_DETAIL_RS_STATUS.md`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/doctor/output.rs` |
| Python module | `pycodex/cli/doctor_updates.py` |
| Python tests | `tests/test_cli_doctor_updates.py` |
| Status | `complete` |

`src/doctor/output.rs` owns human doctor report rendering, grouping, notes,
status display, redaction, style helpers, and sample-report snapshot behavior.
Python carries these contracts through `_doctor_output_*` helpers and
`redact_doctor_detail` in `pycodex/cli/doctor_updates.py`.

## Covered Behavior Areas

The existing alignment ledger in `pycodex/cli/TEST_ALIGNMENT.md` records
covered slices for these `src/doctor/output.rs` anchors:

- report grouping and rendering constants: `GROUPS`, `NAME_WIDTH`,
  `DETAIL_LABEL_WIDTH`, and `SEPARATOR_WIDTH`.
- human output options and sample report fixtures: detailed, summary, all,
  ASCII, and color option shapes used by Rust tests.
- status display and row summaries: `display_status`, `status_marker`,
  `status_marker_slot`, `row_description`, `issue_summary`, and category
  summary helpers.
- notes and footer/header behavior: `notes_for_report`, `update_note`,
  `rollout_note`, `sandbox_note`, `auth_reachability_note`, `non_ok_notes`,
  `summary_line`, `write_footer`, and `header_suffix`.
- redaction behavior: `redact_detail`, URL userinfo/query/fragment removal,
  secret URL path segment redaction, env-var label preservation, and safe
  presence boolean preservation.
- no-color style helpers: action/flag highlighting, detail token dispatch,
  description/note styling, and color helper no-op behavior.
- sample report snapshots: summary/no-color, summary/ASCII, environment
  threads row, state health with memories DB, redacted detail lines, terminal
  warning issue rendering, and promoted notes without status changes.
- summary/no-color Unicode visible output now preserves Rust status markers,
  summary separators, row separators, and remediation dash text (`✓`, `⚠`,
  `✗`, `·`, `─`, and `—`) instead of stale replacement-character fixtures.

## Rust Test Inventory

The Rust module currently contains 17 named test functions:

- `render_human_report_includes_details_by_default_without_color`
- `render_human_report_snapshot_covers_environment_rows`
- `render_human_report_supports_summary_output_without_color`
- `render_human_report_includes_threads_row_in_environment`
- `render_human_report_includes_memories_db_in_state_health_summary`
- `render_human_report_supports_ascii_output`
- `render_human_report_includes_redacted_details`
- `render_human_report_explains_terminal_warning_issue`
- `render_human_report_promotes_notes_without_changing_statuses`
- `render_human_report_expands_feature_flags_with_all`
- `detail_value_colors_inline_statuses_and_low_signal_values`
- `update_note_emphasizes_available_version_and_dims_context`
- `redact_detail_sanitizes_urls`
- `redact_detail_sanitizes_secret_url_path_segments`
- `redact_detail_preserves_env_var_names`
- `redact_detail_preserves_secret_presence_booleans`
- `render_human_report_can_emit_color`

## Reconciled Rust Tests

All 17 local Rust test names now have explicit Python parity comments or
status-ledger entries:

- `render_human_report_includes_details_by_default_without_color`
  - Reconciled by the detailed sample-report metadata, detail-line, footer,
    redaction, and no-color style helper entries in this status file and
    `pycodex/cli/TEST_ALIGNMENT.md`.
- `render_human_report_snapshot_covers_environment_rows`
  - Reconciled by the summary/detailed sample-report environment row helpers
    and the `GROUPS` / category row-order coverage in
    `tests/test_cli_doctor_updates.py`.
- `render_human_report_supports_summary_output_without_color`
- `render_human_report_includes_threads_row_in_environment`
- `render_human_report_includes_memories_db_in_state_health_summary`
- `render_human_report_supports_ascii_output`
- `render_human_report_includes_redacted_details`
- `render_human_report_explains_terminal_warning_issue`
- `render_human_report_promotes_notes_without_changing_statuses`
- `render_human_report_expands_feature_flags_with_all`
  - Reconciled by `_doctor_output_detailed_all_no_color_unicode_options`,
    `_doctor_detail_feature_flags_summary_value`, and the status-ledger entry
    tying Rust's `--all` expansion snapshot to Python's full-list/detail
    helpers.
- `detail_value_colors_inline_statuses_and_low_signal_values`
  - Reconciled by no-color detail styling helpers including
    `_doctor_output_detail_value_no_color`,
    `_doctor_output_style_detail_text_no_color`, and the bare-token dispatch
    entries covering ok, falsy, redacted, flag, URL, and unit tokens.
- `update_note_emphasizes_available_version_and_dims_context`
  - Reconciled by `_doctor_output_update_note_summary`,
    `_doctor_output_style_update_note_summary_no_color`, and sample-report
    update-note entries.
- `redact_detail_sanitizes_urls`
- `redact_detail_sanitizes_secret_url_path_segments`
- `redact_detail_preserves_env_var_names`
- `redact_detail_preserves_secret_presence_booleans`
- `render_human_report_can_emit_color`
  - Reconciled by `_doctor_output_detailed_color_unicode_options`, color helper
    wrappers, and the status-ledger entry that separates color-enabled option
    behavior from the no-color visible text assertions.

## Validation

- Completed on 2026-06-17 after `codex-cli` functional code reached
  complete-candidate coverage.
- Focused validation for this module's shared doctor test file passed:
  `python -m pytest tests/test_cli_doctor_updates.py -q` reported
  `442 passed, 32 subtests passed`.
