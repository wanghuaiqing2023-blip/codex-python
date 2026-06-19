# codex-state `src/runtime/remote_control.rs`

Status: `complete`

Python module: `pycodex/state/runtime/remote_control.py`

## Scope

This pass mirrors the remote-control enrollment persistence contract:

- `RemoteControlEnrollmentRecord`
- `remote_control_app_server_client_name_key`
- `app_server_client_name_from_key`
- `get_remote_control_enrollment`
- `upsert_remote_control_enrollment`
- `delete_remote_control_enrollment`

## Rust Evidence

- Rust module: `codex/codex-rs/state/src/runtime/remote_control.rs`
- Rust migration: `codex/codex-rs/state/migrations/0024_remote_control_enrollments.sql`
- Rust tests:
  - `remote_control_enrollment_round_trips_by_target_and_account`
  - `delete_remote_control_enrollment_removes_only_matching_entry`

## Python Evidence

- Python stores `None` app-server client names as the Rust empty-string key and
  converts the key back to `None` on read.
- Upsert uses Rust's conflict target:
  `(websocket_url, account_id, app_server_client_name)`.
- Delete returns the affected row count, mirroring `rows_affected()`.

## Deferred

- Full `StateRuntime` initialization, migrations, and pool management remain
  owned by `src/runtime.rs`.
- This module assumes the `remote_control_enrollments` table has already been
  created by migrations/runtime initialization.

## Validation

Formal parity validation passed on 2026-06-17:

```text
python -m pytest tests\test_state_runtime_remote_control_rs.py -q
5 passed

python -m py_compile pycodex\state\runtime\remote_control.py pycodex\state\runtime\__init__.py pycodex\state\__init__.py
python -m py_compile tests\test_state_runtime_remote_control_rs.py
```

The pytest suite maps Rust's two in-module tests and adds focused coverage for
the ON CONFLICT update fields, empty-string `None` client key conversion, and
the Python path-based SQLite compatibility shim.
