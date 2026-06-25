# codex-cloud-tasks

Rust crate: `codex-cloud-tasks`

Python package for Rust crate `codex-cloud-tasks`.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/env_detect.rs` | `pycodex/cloud_tasks/__init__.py` | `complete` | Environment autodetection helpers, GitHub origin parsing, environment URL construction, JSON/status/decode error projection, row selection, and TUI environment row merge/sort behavior using the `src/app.rs` `EnvironmentRow` model. |
| `src/lib.rs` | `pycodex/cloud_tasks/__init__.py` | `complete` | Rust-tested/source-contract command/helper slice is mapped: backend init helper, task id parsing, environment id row resolution, query input rules, git-ref fallback, task URL/relative-time/error-log helpers, auth-manager loading helper, ChatGPT header construction helper, task status/list formatting, run-main command dispatch projection, exec-command create-task/output projection, apply/preflight start guard and AppEvent result projection, status-command output/exit projection, list-command JSON/text output projection, diff-command output projection, apply-command message/exit projection, attempt diff collection, attempt selection, and apply status level mapping. |
| `src/scrollable_diff.rs` | `pycodex/cloud_tasks/scrollable_diff.py` | `complete` | Scroll state, content/viewport geometry, source-indexed wrapping, tab/newline/soft-break handling, wide-character display width, and percent scrolled behavior are mapped. |
| `src/cli.rs` | `pycodex/cloud_tasks/cli.py` | `complete` | Command value shapes, defaults, optional fields, and attempts/limit validators are mapped. |
| `src/app.rs` | `pycodex/cloud_tasks/app.py` | `complete` | App state defaults/navigation, `EnvironmentRow`, modal state shapes, AppEvent variant payload shapes, AppEvent match-dispatch facade, `TasksLoaded`, `EnvironmentsLoaded`, `EnvironmentAutodetected`, `NewTaskSubmitted`, `ApplyPreflightFinished`, `ApplyFinished`, details event state transitions with sibling-attempt load hook, `AttemptsLoaded` attempt merge/sort/clamp behavior, conversation/error detail helpers, attempt/diff overlay helpers, and `load_tasks` filtering are mapped. |
| `src/new_task.rs` | `pycodex/cloud_tasks/new_task.py` | `complete` | New-task page state, default constructor, and composer hint registration are mapped. |
| `src/ui.rs` | `pycodex/cloud_tasks/ui.py` | `complete` | Pure rendering helper slice is mapped: rounded flag projection, overlay geometry/content helpers, spinner blink/line/center geometry helpers, environment modal filter/item projection, best-of modal area/selection/option projection, footer help/spinner/status projection, new-task title/content/composer layout projection, task-list title/selection/layout projection, status span styling, diff-line styling, conversation header/gutter/text spans, conversation line projection, and task item text projection. |

## Native Runtime Differences

`codex-cloud-tasks` is marked complete for the dependency-light Python port because the module-scoped contracts with stable public shapes, helper behavior, command projections, AppEvent transitions, state models, and pure UI layout/text projections are covered by Rust-derived tests.

The following Rust-native integrations are intentionally not treated as active gaps under the current core-first project policy:

- full ratatui frame drawing and terminal backend identity in `src/ui.rs`
- Tokio background task/event-loop orchestration and terminal input loop identity in `src/app.rs`/`src/lib.rs`
- live cloud-task backend runtime behavior and real process exit/stdio integration beyond the tested command projections

Focused validation passed: `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py -q --tb=short` -> `86 passed`.
