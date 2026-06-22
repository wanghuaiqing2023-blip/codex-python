# codex-cloud-tasks-mock-client src/mock.rs status

Rust coordinate: `codex/codex-rs/cloud-tasks-mock-client/src/mock.rs`

Python coordinate: `pycodex/cloud_tasks_mock_client/__init__.py`

Status: `complete`

Behavior contract:

- expose a clone/default-like `MockClient` implementing the cloud backend mock
  surface.
- `list_tasks` returns deterministic mock rows, varying content and labels by
  `env-A`, `env-B`, other environment ids, or no environment.
- each listed task has a one-file `DiffSummary` derived from the mock unified
  diff, `is_review=false`, and `attempt_total=2` only for `T-1000`.
- `get_task_summary` searches the default task list and raises a mock
  `CloudTaskError` when the id is absent.
- `get_task_diff`, `get_task_messages`, `get_task_text`, `apply_task`,
  `apply_task_preflight`, `list_sibling_attempts`, and `create_task` mirror the
  Rust mock responses.
- `mock_diff_for` returns the three Rust mock unified diffs and
  `count_from_unified` counts insert/delete lines while ignoring file headers
  and hunk headers.

Evidence:

- `MockClient`, mock data shapes, `mock_diff_for`, and `count_from_unified` are
  implemented in `pycodex/cloud_tasks_mock_client/__init__.py`.
- `tests/test_cloud_tasks_mock_client.py` covers source-contract behavior
  derived from Rust `src/mock.rs`.

Validation:

- `tests/test_cloud_tasks_mock_client.py`
