# codex-cloud-tasks src/cli.rs status

Rust crate: `codex-cloud-tasks`

Rust module: `codex/codex-rs/cloud-tasks/src/cli.rs`

Python module: `pycodex/cloud_tasks/cli.py`

Status: `complete`

## Anchors

- `Cli`
- `Command`
- `ExecCommand`
- `StatusCommand`
- `ListCommand`
- `ApplyCommand`
- `DiffCommand`
- `parse_attempts`
- `parse_limit`

## Ported behavior

- Command value shapes and names for `exec`, `status`, `list`, `apply`, and `diff`.
- `ExecCommand` default attempts value and branch/query optionality.
- `ListCommand` default limit, cursor, environment filter, and JSON flag.
- Optional attempt validation for `ApplyCommand` and `DiffCommand`.
- `parse_attempts` integer/range errors matching Rust source messages.
- `parse_limit` integer/range errors matching Rust source messages.
- `Cli` root shape with skipped config overrides and optional command.

## Evidence

- Rust source: `codex/codex-rs/cloud-tasks/src/cli.rs`
- Python source: `pycodex/cloud_tasks/cli.py`
- Python test: `tests/test_cloud_tasks_cli_rs.py`

## Validation

- `python -m pytest tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py -q --tb=short` -> `34 passed`
- `python -m py_compile pycodex/cloud_tasks/__init__.py pycodex/cloud_tasks/scrollable_diff.py pycodex/cloud_tasks/cli.py tests/test_cloud_tasks_env_detect_rs.py tests/test_cloud_tasks_lib_rs.py tests/test_cloud_tasks_scrollable_diff_rs.py tests/test_cloud_tasks_cli_rs.py` -> passed

## Remaining crate gaps

`src/cli.rs` value contract is complete. Actual command execution remains in `src/lib.rs` and is not certified by this module.
