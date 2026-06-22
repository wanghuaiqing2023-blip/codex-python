# codex-cloud-tasks src/app.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/app.rs`

Python module: `pycodex/cloud_tasks/app.py`

Status: `module_progress`

## Completed helper slice

- `EnvModalState`
- `BestOfModalState`
- `ApplyModalState`
- `App::{new,next,prev}`
- `AttemptView::{has_diff,has_text}`
- `DiffOverlay::{new,current_attempt,base_attempt_mut,set_view,expected_attempts,attempt_count,attempt_display_total,step_attempt,current_can_apply,apply_selection_to_fields}`
- `DetailView`
- `load_tasks`

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks/src/app.rs`
- Rust test: `load_tasks_uses_env_parameter`
- Python source: `pycodex/cloud_tasks/app.py`
- Python test: `tests/test_cloud_tasks_app_rs.py`

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py -q --tb=short` -> `41 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py pycodex/cloud_tasks/cli.py pycodex/cloud_tasks/new_task.py pycodex/cloud_tasks/app.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py` -> passed

## Remaining gaps

`src/app.rs` still has runtime/event payload integration that is not fully certified here: `AppEvent` variants and full interaction with background task event loop remain open with `src/ui.rs` and broader `src/lib.rs` runtime orchestration.
