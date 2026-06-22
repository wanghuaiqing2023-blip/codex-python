# codex-cloud-tasks src/new_task.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/new_task.rs`

Python module: `pycodex/cloud_tasks/new_task.py`

Status: `complete`

## Anchors

- `NewTaskPage`
- `NewTaskPage::new`
- `Default for NewTaskPage`
- `ComposerInput::set_hint_items`

## Ported behavior

- New-task page state shape: `composer`, `submitting`, `env_id`, and `best_of_n`.
- `NewTaskPage::new` constructs a fresh `ComposerInput`.
- Rust footer hint registrations are mirrored as `NEW_TASK_HINT_ITEMS`.
- `submitting` starts as `false`.
- `env_id` and `best_of_n` are preserved from constructor inputs.
- Default construction uses `env_id=None` and `best_of_n=1`.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks/src/new_task.rs`
- Adjacent Rust/Python dependency: `codex-tui::ComposerInput` / `pycodex.tui.public_widgets.ComposerInput`
- Python source: `pycodex/cloud_tasks/new_task.py`
- Python test: `tests/test_cloud_tasks_new_task_rs.py`

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py -q --tb=short` -> `36 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py pycodex/cloud_tasks/cli.py pycodex/cloud_tasks/new_task.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py` -> passed

## Remaining crate gaps

`src/new_task.rs` is complete. `codex-cloud-tasks` remains `module_progress`; remaining modules include `src/app.rs`, `src/ui.rs`, and broader runtime command orchestration in `src/lib.rs`.
