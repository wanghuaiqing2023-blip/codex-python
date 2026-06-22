# codex-thread-store src/live_thread.rs

Rust crate: `codex-thread-store`
Rust module: `src/live_thread.rs`
Python package: `pycodex.thread_store`

## Status

`complete_slice`

## Rust Anchors

- `LiveThread`
- `LiveThreadInitGuard`
- `LiveThread::create`
- `LiveThread::resume`
- `LiveThread::append_items`
- `LiveThread::persist`
- `LiveThread::flush`
- `LiveThread::shutdown`
- `LiveThread::discard`
- `LiveThread::load_history`
- `LiveThread::read_thread`
- `LiveThread::update_memory_mode`
- `LiveThread::update_metadata`
- `event_persistence_mode`

## Covered Contract

- `create` constructs metadata sync before creating the store thread and keeps
  the selected event persistence mode on the live handle.
- `resume` calls `resume_thread`, loads store history when caller history is
  missing, discards the live writer on load failure, and builds metadata sync
  from the loaded history.
- `append_items` filters through Rust rollout persistence policy, returns early
  for empty canonical output, appends canonical items, observes metadata, and
  applies the pending metadata patch with `include_archived=true`.
- `persist`, `flush`, and `shutdown` preserve Rust's pending-metadata flush
  ordering.
- `update_metadata` and `update_memory_mode` flush pending metadata before the
  caller-visible metadata patch.
- `LiveThreadInitGuard` exposes `as_ref`, `commit`, and explicit async
  `discard`.

## Python Tests

- `tests/test_thread_store_live_thread_rs.py::test_live_thread_observes_appended_items_into_store_metadata`
- `tests/test_thread_store_live_thread_rs.py::test_live_thread_skips_non_persisted_append_items`
- `tests/test_thread_store_live_thread_rs.py::test_live_thread_resume_loads_history_before_observing_metadata`
- `tests/test_thread_store_live_thread_rs.py::test_live_thread_update_metadata_flushes_pending_metadata_first`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_live_thread_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `18 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `19 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_live_thread_rs.py`
  - passed

## Remaining Outside This Slice

- Rust `Drop` behavior for `LiveThreadInitGuard` spawns asynchronous discard on
  the current Tokio runtime; Python keeps explicit async `discard` and does not
  emulate implicit destructor scheduling.
- `local_rollout_path` remains a dependency-light escape hatch that delegates to
  stores exposing `live_rollout_path`; full local rollout/state-db behavior is
  tracked under `src/local/*`.
- Exact Tokio mutex/task scheduling identity remains outside the Python slice.
