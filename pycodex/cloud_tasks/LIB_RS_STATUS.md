# codex-cloud-tasks src/lib.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/lib.rs`

Python module: `pycodex/cloud_tasks/__init__.py`

Status: `module_progress`

## Completed helper slice

- `resolve_git_ref_with_git_info`
- `resolve_environment_id` row-selection helper contract
- `resolve_query_input`
- `parse_task_id`
- `AttemptDiffData`
- `collect_attempt_diffs`
- `select_attempt`
- `task_status_label`
- `summary_line`
- `format_task_status_lines`
- `format_task_list_lines`
- `level_from_status`
- adjacent `util.rs::{normalize_base_url,task_url,format_relative_time}`

## Evidence

- Rust tests:
  - `branch_override_is_used_when_provided`
  - `trims_override_whitespace`
  - `prefers_current_branch_when_available`
  - `falls_back_to_current_branch_when_default_is_missing`
  - `falls_back_to_main_when_no_git_info_is_available`
  - `format_task_status_lines_with_diff_and_label`
  - `format_task_status_lines_without_diff_falls_back`
  - `format_task_list_lines_formats_urls`
  - `collect_attempt_diffs_includes_sibling_attempts`
  - `select_attempt_validates_bounds`
  - `parse_task_id_from_url_and_raw`
- Source-contract derived coverage for `resolve_environment_id`, `resolve_query_input`, and `level_from_status`.
- Python test: `tests/test_cloud_tasks_lib_rs.py`

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py -q --tb=short` -> `23 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py` -> passed

## Remaining gaps

The broader `src/lib.rs` runtime remains open: backend initialization/auth, command execution paths, live environment listing/header construction, real stdin/terminal integration, status/diff/apply/list/new-task commands, TUI orchestration, task update loops, and process exit behavior are not certified by this helper slice.
