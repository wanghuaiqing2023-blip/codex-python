# codex-cloud-tasks src/ui.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/ui.rs`

Python module: `pycodex/cloud_tasks/ui.py`

Status: `module_progress`

## Certified Slice

The pure rendering helper slice is mapped from Rust source contracts:

- `attempt_status_span`
- `style_diff_line`
- `conversation_header_line`
- `conversation_gutter_span`
- `conversation_text_spans`
- `style_conversation_lines`
- `render_task_item`

These helpers preserve the Rust module's stable text/style projection behavior without pulling in a terminal UI framework.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks/src/ui.rs`
- Python implementation: `pycodex/cloud_tasks/ui.py`
- Python tests: `tests/test_cloud_tasks_ui_rs.py`

There are no direct Rust inline tests for this helper slice; the Python tests are source-contract derived from the Rust module.

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py -q --tb=short` -> `46 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py pycodex/cloud_tasks/cli.py pycodex/cloud_tasks/new_task.py pycodex/cloud_tasks/app.py pycodex/cloud_tasks/ui.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py` passed

## Remaining Gaps

- Full ratatui frame rendering and layout integration in `src/ui.rs`
- AppEvent/background event-loop integration in `src/app.rs`
- Broader command/runtime orchestration in `src/lib.rs`
