# codex-cloud-tasks

Rust crate: `codex-cloud-tasks`

Python package for Rust crate `codex-cloud-tasks`.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/env_detect.rs` | `pycodex/cloud_tasks/__init__.py` | `complete` | Environment autodetection helpers, GitHub origin parsing, environment URL construction, JSON/status/decode error projection, row selection, and TUI environment row merge/sort behavior. |
| `src/lib.rs` | `pycodex/cloud_tasks/__init__.py` | `module_progress` | Rust-tested/source-contract helper slice is mapped: task id parsing, environment id row resolution, query input rules, git-ref fallback, task URL/relative-time formatting, task status/list formatting, attempt diff collection, attempt selection, and apply status level mapping. Command orchestration and runtime entrypoints remain open. |
| `src/scrollable_diff.rs` | `pycodex/cloud_tasks/scrollable_diff.py` | `complete` | Scroll state, content/viewport geometry, source-indexed wrapping, tab/newline/soft-break handling, wide-character display width, and percent scrolled behavior are mapped. |
| `src/cli.rs` | `pycodex/cloud_tasks/cli.py` | `complete` | Command value shapes, defaults, optional fields, and attempts/limit validators are mapped. |
| `src/app.rs` | `pycodex/cloud_tasks/app.py` | `module_progress` | App state defaults/navigation, modal state shapes, attempt/diff overlay helpers, and `load_tasks` filtering are mapped. AppEvent/background event-loop integration remains open. |
| `src/new_task.rs` | `pycodex/cloud_tasks/new_task.py` | `complete` | New-task page state, default constructor, and composer hint registration are mapped. |
| `src/ui.rs` | `pycodex/cloud_tasks/ui.py` | `module_progress` | Pure rendering helper slice is mapped: status span styling, diff-line styling, conversation header/gutter/text spans, conversation line projection, and task item text projection. Full ratatui frame rendering remains open. |

Focused validation passed: `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py -q --tb=short` -> `46 passed`.
