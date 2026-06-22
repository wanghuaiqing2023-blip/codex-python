# codex-cloud-tasks test alignment

Rust crate: `codex-cloud-tasks`

Python package: `pycodex/cloud_tasks`

Status: `module_progress`

Certified modules:

- `codex/codex-rs/cloud-tasks/src/app.rs` helper/state slice -> `pycodex/cloud_tasks/app.py`
- `codex/codex-rs/cloud-tasks/src/cli.rs` -> `pycodex/cloud_tasks/cli.py`
- `codex/codex-rs/cloud-tasks/src/env_detect.rs` -> `pycodex/cloud_tasks/__init__.py`
- `codex/codex-rs/cloud-tasks/src/new_task.rs` -> `pycodex/cloud_tasks/new_task.py`
- `codex/codex-rs/cloud-tasks/src/scrollable_diff.rs` -> `pycodex/cloud_tasks/scrollable_diff.py`

Certified module slices:

- `codex/codex-rs/cloud-tasks/src/ui.rs` pure rendering helper slice -> `pycodex/cloud_tasks/ui.py`
  - `attempt_status_span`
  - `style_diff_line`
  - `conversation_header_line`
  - `conversation_gutter_span`
  - `conversation_text_spans`
  - `style_conversation_lines`
  - `render_task_item`
- `codex/codex-rs/cloud-tasks/src/lib.rs` helper/test slice -> `pycodex/cloud_tasks/__init__.py`
  - `resolve_git_ref_with_git_info`
  - `resolve_environment_id` row-selection contract
  - `resolve_query_input`
  - `parse_task_id`
  - `format_task_status_lines`
  - `format_task_list_lines`
  - `collect_attempt_diffs`
  - `select_attempt`
  - `level_from_status`
  - adjacent `util.rs::{normalize_base_url,task_url,format_relative_time}`

Remaining Rust gaps:

- `codex/codex-rs/cloud-tasks/src/ui.rs` full ratatui draw/frame integration
- `codex/codex-rs/cloud-tasks/src/app.rs` AppEvent/background event-loop integration
- broader command/runtime orchestration in `codex/codex-rs/cloud-tasks/src/lib.rs`

Rust tests and fixtures:

- No direct Rust inline tests are registered in `src/env_detect.rs`.
- Python tests are source-contract derived from `src/env_detect.rs` and the adjacent `src/app.rs::EnvironmentRow` data shape.
- Rust unit tests in `src/lib.rs` describe the helper slice covered by `tests/test_cloud_tasks_lib_rs.py`.
- No direct Rust inline tests are registered in `src/scrollable_diff.rs`; Python tests are source-contract derived from the Rust module.
- No direct Rust inline tests are registered in `src/cli.rs`; Python tests are source-contract derived from the Rust module.
- No direct Rust inline tests are registered in `src/new_task.rs`; Python tests are source-contract derived from the Rust module.
- Rust unit test `load_tasks_uses_env_parameter` and source contracts in `src/app.rs` describe the app helper/state slice covered by `tests/test_cloud_tasks_app_rs.py`.
- No direct Rust inline tests are registered in `src/ui.rs`; Python tests are source-contract derived from the Rust module's pure rendering helpers.
- `codex/codex-rs/cloud-tasks/tests/env_filter.rs` belongs to the environment-filtered mock backend behavior and is covered by `pycodex/cloud_tasks_mock_client`, not this `env_detect.rs` slice.

Python tests:

- `tests/test_cloud_tasks_env_detect_rs.py`
- `tests/test_cloud_tasks_lib_rs.py`
- `tests/test_cloud_tasks_scrollable_diff_rs.py`
- `tests/test_cloud_tasks_cli_rs.py`
- `tests/test_cloud_tasks_new_task_rs.py`
- `tests/test_cloud_tasks_app_rs.py`
- `tests/test_cloud_tasks_ui_rs.py`

Validation:

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py -q --tb=short` (`46 passed`)
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py pycodex/cloud_tasks/cli.py pycodex/cloud_tasks/new_task.py pycodex/cloud_tasks/app.py pycodex/cloud_tasks/ui.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py` (passed)
