# codex-cloud-tasks src/env_detect.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/env_detect.rs`

Python module: `pycodex/cloud_tasks/__init__.py`

Status: `complete`

## Anchors

- `CodeEnvironment`
- `AutodetectSelection`
- `autodetect_environment_id`
- `pick_environment_row`
- `get_json`
- `get_git_origins`
- `uniq`
- `parse_owner_repo`
- `list_environments`
- adjacent `crate::app::EnvironmentRow`

## Ported behavior

- Backend/public environment endpoint path selection.
- GitHub origin parsing for scp-style SSH, `ssh://` scp-style, HTTPS, HTTP, `git://`, and bare `github.com/` forms.
- Git origin detection order: `git config --get-regexp remote\..*\.url` first, then `git remote -v`, with sorted deduplication.
- Environment selection order: desired label case-insensitive match, single row, first pinned row, then Rust `max_by_key`-style highest task count with last-tie selection.
- Rust-shaped GET status and JSON decode error messages.
- Autodetect by-repo-first behavior, by-repo failure tolerance, global fallback, and empty-list error.
- Environment row merge behavior across by-repo and global sources, including label retention, pinned OR merge, repo hint preservation, and pinned/label/id sorting.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks/src/env_detect.rs`
- Adjacent Rust source: `codex/codex-rs/cloud-tasks/src/app.rs::EnvironmentRow`
- Python source: `pycodex/cloud_tasks/__init__.py`
- Python test: `tests/test_cloud_tasks_env_detect_rs.py`

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py -q --tb=short` -> `10 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py tests/test_cloud_tasks_env_detect_rs.py` -> passed

## Remaining crate gaps

`codex-cloud-tasks` remains `module_progress`; broader task formatting, attempt/diff helpers, git ref resolution, task command orchestration, TUI application state, modal rendering, markdown streaming, and live cloud-task runtime behavior remain open.
