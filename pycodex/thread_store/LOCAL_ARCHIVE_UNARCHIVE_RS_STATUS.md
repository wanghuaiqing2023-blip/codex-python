# codex-thread-store src/local/archive_thread.rs and unarchive_thread.rs Status

Rust crate: `codex-thread-store`
Rust modules:

- `src/local/archive_thread.rs`
- `src/local/unarchive_thread.rs`

Python surface:

- `pycodex.thread_store.LocalThreadStore.archive_thread`
- `pycodex.thread_store.LocalThreadStore.unarchive_thread`

## Status

`complete_slice`

The module-scoped behavior contracts covered by the Rust inline tests in both
modules are mirrored by Python tests.

## Rust Anchors

- `archive_thread`
- `unarchive_thread`
- `find_thread_path_by_id_str`
- `find_archived_thread_path_by_id_str`
- `scoped_rollout_path`
- `matching_rollout_file_name`
- `rollout_date_parts`
- `touch_modified_time`
- `read_thread_item_from_rollout`
- state-db `mark_archived` / `mark_unarchived` runtime calls

## Python Coverage

- Active rollouts are located by thread id and moved from `sessions` to `archived_sessions`.
- Archived rollouts are located by thread id and restored into dated `sessions/YYYY/MM/DD`.
- Source and destination paths are constrained to the expected rollout roots.
- Rollout filenames must match the requested thread id.
- Archived listings can see archived files and mark `archived_at`.
- Unarchive returns an active `StoredThread` summary from the restored rollout.
- Optional state-db runtimes receive archive/unarchive metadata updates.

## Rust-Derived Tests

- `tests/test_thread_store_local_archive_unarchive_rs.py::test_archive_thread_moves_rollout_to_archived_collection`
- `tests/test_thread_store_local_archive_unarchive_rs.py::test_archive_thread_updates_sqlite_metadata_when_present`
- `tests/test_thread_store_local_archive_unarchive_rs.py::test_unarchive_thread_restores_rollout_and_returns_updated_thread`
- `tests/test_thread_store_local_archive_unarchive_rs.py::test_unarchive_thread_updates_sqlite_metadata_when_present`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_local_archive_unarchive_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `56 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `57 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_archive_unarchive_rs.py`
  - passed

## Crate Status

`codex-thread-store` is tracked as `complete`; the remaining exact Tokio
locking/runtime identity difference is documented as non-blocking for the
dependency-light Python port.
