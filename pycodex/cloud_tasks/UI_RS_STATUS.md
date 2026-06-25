# codex-cloud-tasks src/ui.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/ui.rs`

Python module: `pycodex/cloud_tasks/ui.py`

Status: `complete`

## Certified Slice

The pure rendering helper slice is mapped from Rust source contracts:

- `attempt_status_span`
- `rounded_enabled`
- `overlay_outer`
- `overlay_content`
- `spinner_dot`
- `inline_spinner_line`
- `centered_spinner_area`
- `filter_environment_rows`
- `env_modal_selected_index`
- `render_environment_item`
- `env_modal_item_lines`
- `best_of_modal_area`
- `best_of_selected_index`
- `render_best_of_option`
- `best_of_option_lines`
- `footer_help_line`
- `footer_spinner_visible`
- `footer_status_line`
- `new_task_title_line`
- `new_task_content_area`
- `new_task_composer_desired_height`
- `new_task_composer_area`
- `task_list_dimmed`
- `task_list_env_suffix`
- `task_list_percent_span`
- `task_list_title_line`
- `task_list_inner_area`
- `task_list_rows_area`
- `style_diff_line`
- `conversation_header_line`
- `conversation_gutter_span`
- `conversation_text_spans`
- `style_conversation_lines`
- `render_task_item`

These helpers preserve the Rust module's stable overlay geometry, spinner blink/line geometry, environment modal filter/item projection, best-of modal area/selection/option projection, footer help/spinner/status projection, new-task title/content/composer layout projection, task-list title/selection/layout projection, and text/style projection behavior without pulling in a terminal UI framework.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks/src/ui.rs`
- Python implementation: `pycodex/cloud_tasks/ui.py`
- Python tests: `tests/test_cloud_tasks_ui_rs.py`

There are no direct Rust inline tests for this helper slice; the Python tests are source-contract derived from the Rust module.

## Validation

- `python -m pytest tests/test_cloud_tasks_ui_rs.py -q --tb=short` -> `12 passed`
- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_ui_rs.py -q --tb=short` -> `55 passed`
- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py -q --tb=short` -> `86 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py pycodex/cloud_tasks/cli.py pycodex/cloud_tasks/new_task.py pycodex/cloud_tasks/app.py pycodex/cloud_tasks/ui.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py` passed

## Native Runtime Differences

- Full ratatui frame rendering, terminal backend identity, and live draw-loop integration are intentionally not implemented in Python.
- Python carries the stable pure rendering helper contracts for geometry, list/modal/footer/new-task layout, spinner projection, and text/style spans without pulling in a terminal UI framework.
