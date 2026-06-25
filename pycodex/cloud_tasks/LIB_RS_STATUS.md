# codex-cloud-tasks src/lib.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/lib.rs`

Python module: `pycodex/cloud_tasks/__init__.py`

Status: `complete`

## Completed helper slice

- `init_backend`
- `resolve_git_ref_with_git_info`
- `resolve_environment_id` row-selection helper contract
- `resolve_query_input`
- `parse_task_id`
- `AttemptDiffData`
- `collect_attempt_diffs`
- `select_attempt`
- `ExecCommandProjection`
- `RunMainDispatchProjection`
- `run_main_dispatch_projection`
- `exec_command_projection`
- `diff_command_projection`
- `apply_command_projection`
- `ApplyJob`
- `spawn_preflight_start_projection`
- `spawn_apply_start_projection`
- `apply_preflight_finished_event_projection`
- `apply_finished_event_projection`
- `task_status_label`
- `summary_line`
- `format_task_status_lines`
- `status_command_projection`
- `format_task_list_lines`
- `list_command_json_payload`
- `format_list_command_text_lines`
- `level_from_status`
- adjacent `util.rs::{normalize_base_url,task_url,format_relative_time,append_error_log,set_user_agent_suffix,load_auth_manager,build_chatgpt_headers}`

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
- Source-contract derived coverage for `run_main` command-to-handler dispatch and no-command TUI branch selection.
- Source-contract derived coverage for `run_list_command` JSON payload shape, empty-list text output, and pagination hint text.
- Source-contract derived coverage for `run_exec_command` create-task argument projection and printed task URL.
- Source-contract derived coverage for `run_status_command` printed line projection and non-ready exit code.
- Source-contract derived coverage for `run_diff_command` selected-attempt diff output and `run_apply_command` outcome message/non-success exit code.
- Source-contract derived coverage for `spawn_preflight`/`spawn_apply` start guard status messages, inflight flag mutation, and success/error result-to-AppEvent projection.
- Python test: `tests/test_cloud_tasks_lib_rs.py`

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py -q --tb=short` -> `43 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py` -> passed

## Native Runtime Differences

The Python port intentionally keeps `src/lib.rs` dependency-light. It does not implement Rust's full Tokio/TUI runtime identity, live cloud-task backend orchestration, real terminal stdin loop, or exact process exit/stdio integration. The stable module contracts carried by Python are the tested command projections, helper behavior, backend/header initialization shape, apply/preflight AppEvent projections, and task/attempt formatting and selection rules.
