# codex-cloud-tasks test alignment

Rust crate: `codex-cloud-tasks`

Python package: `pycodex/cloud_tasks`

Status: `complete`

Certified modules:

- `codex/codex-rs/cloud-tasks/src/app.rs` helper/state slice -> `pycodex/cloud_tasks/app.py`
  - `EnvironmentRow` ownership and package-root re-export
  - `AppEvent` variant payload shapes
  - AppEvent match-dispatch facade
  - `TasksLoaded`, `EnvironmentsLoaded`, `EnvironmentAutodetected`, `NewTaskSubmitted`, `ApplyPreflightFinished`, and `ApplyFinished` event state transitions
  - `DetailsDiffLoaded`, `DetailsMessagesLoaded`, and `DetailsFailed` event state transitions
  - `DetailsMessagesLoaded` sibling-attempt load runtime registration hook
  - `AttemptsLoaded` attempt merge/sort/clamp state transition
  - `conversation_lines`
  - `pretty_lines_from_error`
- `codex/codex-rs/cloud-tasks/src/cli.rs` -> `pycodex/cloud_tasks/cli.py`
- `codex/codex-rs/cloud-tasks/src/env_detect.rs` -> `pycodex/cloud_tasks/__init__.py`
- `codex/codex-rs/cloud-tasks/src/new_task.rs` -> `pycodex/cloud_tasks/new_task.py`
- `codex/codex-rs/cloud-tasks/src/scrollable_diff.rs` -> `pycodex/cloud_tasks/scrollable_diff.py`

Certified module slices:

- `codex/codex-rs/cloud-tasks/src/ui.rs` pure rendering helper slice -> `pycodex/cloud_tasks/ui.py`
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
  - `attempt_status_span`
  - `style_diff_line`
  - `conversation_header_line`
  - `conversation_gutter_span`
  - `conversation_text_spans`
  - `style_conversation_lines`
  - `render_task_item`
- `codex/codex-rs/cloud-tasks/src/lib.rs` helper/test slice -> `pycodex/cloud_tasks/__init__.py`
  - `init_backend`
  - `resolve_git_ref_with_git_info`
  - `resolve_environment_id` row-selection contract
  - `resolve_query_input`
  - `parse_task_id`
  - `format_task_status_lines`
  - `RunMainDispatchProjection`
  - `run_main_dispatch_projection`
  - `exec_command_projection`
  - `status_command_projection`
  - `format_task_list_lines`
  - `list_command_json_payload`
  - `format_list_command_text_lines`
  - `collect_attempt_diffs`
  - `select_attempt`
  - `diff_command_projection`
  - `apply_command_projection`
  - `ApplyJob`
  - `spawn_preflight_start_projection`
  - `spawn_apply_start_projection`
  - `apply_preflight_finished_event_projection`
  - `apply_finished_event_projection`
  - `level_from_status`
  - adjacent `util.rs::{normalize_base_url,task_url,format_relative_time,append_error_log,set_user_agent_suffix,load_auth_manager,build_chatgpt_headers}`

Native Runtime Differences:

- `codex/codex-rs/cloud-tasks/src/ui.rs` full ratatui draw/frame integration and terminal backend identity are not implemented in Python.
- `codex/codex-rs/cloud-tasks/src/app.rs`/`src/lib.rs` Tokio background event-loop, real terminal input loop, live backend runtime, and process exit/stdio identity are not implemented in Python.
- These are recorded as Rust-native runtime differences for the dependency-light port. The stable module-scoped contracts that Python carries are the tested helper/state/command projection, AppEvent transition, and pure UI layout/text behavior listed above.

Rust tests and fixtures:

- No direct Rust inline tests are registered in `src/env_detect.rs`.
- Python tests are source-contract derived from `src/env_detect.rs` and the adjacent `src/app.rs::EnvironmentRow` data shape, including package-root re-export identity so environment listing does not create a second Python row type.
- Rust unit tests in `src/lib.rs` describe the helper slice covered by `tests/test_cloud_tasks_lib_rs.py`.
- `codex/codex-rs/cloud-tasks/src/lib.rs::run_main` has no direct Rust inline test; Python coverage is source-contract derived from the command dispatch body and verifies `Command::{Exec,Status,List,Apply,Diff}` route to the corresponding `run_*_command` branch before TUI initialization, while absent command enters the TUI path.
- `codex/codex-rs/cloud-tasks/src/lib.rs::run_list_command` JSON and text output branches have no direct Rust inline tests; Python coverage is source-contract derived from the command body and verifies JSON payload shape, task URL projection, summary object fields, cursor propagation, empty-list message, and pagination hint text.
- `codex/codex-rs/cloud-tasks/src/lib.rs::run_exec_command` has no direct Rust inline test; Python coverage is source-contract derived from the command body and verifies `CloudBackend::create_task` argument projection, `qa_mode=false`, `attempts` to best-of-N forwarding, and printed task URL projection.
- `codex/codex-rs/cloud-tasks/src/lib.rs::run_status_command` has no direct Rust inline test; Python coverage is source-contract derived from the command body and verifies printed status lines plus exit-code projection where non-ready tasks exit with code 1.
- `codex/codex-rs/cloud-tasks/src/lib.rs::run_diff_command` has no direct Rust inline test; Python coverage is source-contract derived from the command body and verifies selected-attempt diff output.
- `codex/codex-rs/cloud-tasks/src/lib.rs::run_apply_command` has no direct Rust inline test; Python coverage is source-contract derived from the command body and verifies printed outcome message plus exit-code projection where non-success apply outcomes exit with code 1.
- `codex/codex-rs/cloud-tasks/src/lib.rs::spawn_preflight` and `spawn_apply` have no direct Rust inline tests; Python coverage is source-contract derived from the function bodies and verifies `ApplyJob` shape, start guard status messages/flag mutation, success/error mapping into `AppEvent::ApplyPreflightFinished` and `AppEvent::ApplyFinished`, including the Rust `Preflight failed: {e}` error message and `ApplyResultLevel` mapping.
- `codex/codex-rs/cloud-tasks/src/lib.rs::init_backend` has no direct Rust inline test; Python coverage is source-contract derived from the Rust function body and uses injected factories/loaders to verify mock-mode, base URL, User-Agent, auth, and logging behavior without claiming full live cloud runtime parity.
- `codex/codex-rs/cloud-tasks/src/util.rs::append_error_log` has no direct Rust inline test; Python coverage is source-contract derived from the Rust function body.
- `codex/codex-rs/cloud-tasks/src/util.rs::load_auth_manager` has no direct Rust inline test; Python coverage is source-contract derived from the Rust function body and verifies config/home/base-url/store-mode parameters through an injected `AuthManager` factory.
- `codex/codex-rs/cloud-tasks/src/util.rs::build_chatgpt_headers` has no direct Rust inline test; Python coverage is source-contract derived from the Rust function body and uses an injected auth manager to avoid treating real config/auth loading as complete.
- No direct Rust inline tests are registered in `src/scrollable_diff.rs`; Python tests are source-contract derived from the Rust module.
- No direct Rust inline tests are registered in `src/cli.rs`; Python tests are source-contract derived from the Rust module.
- No direct Rust inline tests are registered in `src/new_task.rs`; Python tests are source-contract derived from the Rust module.
- Rust unit test `load_tasks_uses_env_parameter` and source contracts in `src/app.rs` describe the app helper/state slice covered by `tests/test_cloud_tasks_app_rs.py`.
- `codex/codex-rs/cloud-tasks/src/app.rs::AppEvent` has no direct Rust inline test; Python coverage is source-contract derived from the Rust enum variant definitions and payload field names.
- `codex/codex-rs/cloud-tasks/src/lib.rs` AppEvent match dispatch has no direct Rust inline test; Python coverage is source-contract derived from the Rust event-loop `match ev` arms and verifies dispatcher routing, selected follow-up work hooks, and unknown-kind rejection for Python's non-exhaustive runtime.
- `codex/codex-rs/cloud-tasks/src/lib.rs` AppEvent handler branches for `TasksLoaded`, `EnvironmentsLoaded`, `EnvironmentAutodetected`, `NewTaskSubmitted`, `ApplyPreflightFinished`, and `ApplyFinished` have no direct Rust inline tests; Python coverage is source-contract derived from the event-loop match arms and verifies state mutation, race dropping, logging, modal id guarding, environment preseed behavior, refresh/list-load scheduling registration, new-task submit success/failure projection, and apply success/failure projection.
- `codex/codex-rs/cloud-tasks/src/lib.rs` details AppEvent handler branches and helpers have no direct Rust inline tests; Python coverage is source-contract derived from the `DetailsDiffLoaded`, `DetailsMessagesLoaded`, `DetailsFailed`, `conversation_lines`, and `pretty_lines_from_error` Rust bodies, including the sibling-attempt load registration condition for existing overlays.
- `codex/codex-rs/cloud-tasks/src/lib.rs` `AttemptsLoaded` AppEvent handler branch has no direct Rust inline test; Python coverage is source-contract derived from the event-loop match arm and verifies overlay task-id guarding, turn-id dedupe, attempt-placement sort order, selected-attempt clamp, total hint update, and selected field projection.
- No direct Rust inline tests are registered in `src/ui.rs`; Python tests are source-contract derived from the Rust module's pure rendering helpers, including overlay geometry helpers, spinner blink/line/center geometry helpers, environment modal filter/item projections, best-of modal area/selection/option projections, footer help/spinner/status projections, new-task title/content/composer layout projections, task-list title/selection/layout projections, and conversation/task item projections.
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

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py -q --tb=short` (`86 passed`)
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py pycodex/cloud_tasks/cli.py pycodex/cloud_tasks/new_task.py pycodex/cloud_tasks/app.py pycodex/cloud_tasks/ui.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py tests/test_cloud_tasks_new_task_rs.py tests/test_cloud_tasks_app_rs.py tests/test_cloud_tasks_ui_rs.py` (passed)
