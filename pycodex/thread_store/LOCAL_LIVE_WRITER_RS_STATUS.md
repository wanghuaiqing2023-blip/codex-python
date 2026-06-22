# codex-thread-store src/local/create_thread.rs and src/local/live_writer.rs

Rust crate: `codex-thread-store`
Rust modules: `src/local/create_thread.rs`, `src/local/live_writer.rs`
Python package: `pycodex.thread_store`

## Status

`complete_slice`

## Rust Anchors

- `create_thread::create_thread`
- `live_writer::create_thread`
- `live_writer::resume_thread`
- `live_writer::append_items`
- `live_writer::persist_thread`
- `live_writer::flush_thread`
- `live_writer::shutdown_thread`
- `live_writer::discard_thread`
- `live_writer::rollout_path`
- `LocalThreadStore::ensure_live_recorder_absent`
- `LocalThreadStore::insert_live_recorder`

## Covered Contract

- Local thread creation requires `ThreadPersistenceMetadata.cwd`.
- Local create/resume reject duplicate live writers for the same thread id.
- Local live writers expose a rollout path before materialization.
- Raw local append writes canonical JSONL through `RolloutRecorder`, and
  persist/flush materialize queued items.
- Shutdown flushes then removes the live writer; later appends return
  `thread_not_found`.
- Discard removes an unmaterialized writer without creating the rollout file.

## Python Tests

- `tests/test_thread_store_local_live_writer_rs.py::test_local_live_writer_lifecycle_writes_and_closes`
- `tests/test_thread_store_local_live_writer_rs.py::test_local_create_thread_rejects_missing_cwd`
- `tests/test_thread_store_local_live_writer_rs.py::test_local_discard_thread_drops_unmaterialized_live_writer`
- `tests/test_thread_store_local_live_writer_rs.py::test_local_create_and_resume_reject_duplicate_live_writer`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_local_live_writer_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `22 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `23 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_live_writer_rs.py`
  - passed

## Remaining Outside This Slice

- Full `src/local/read_thread.rs`, `list_threads.rs`, `search_threads.rs`,
  `update_thread_metadata.rs`, `archive_thread.rs`, and `unarchive_thread.rs`
  rollout/state-db behavior remains open.
- `sync_materialized_rollout_path` state-db repair is not implemented in this
  dependency-light live-writer slice.
- Exact Tokio mutex/task identity remains outside the Python slice.
