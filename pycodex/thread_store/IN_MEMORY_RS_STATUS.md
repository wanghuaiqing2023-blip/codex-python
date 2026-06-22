# codex-thread-store src/in_memory.rs

Rust crate: `codex-thread-store`
Rust module: `src/in_memory.rs`
Python package: `pycodex.thread_store`

## Status

`complete_slice`

## Rust Anchors

- `InMemoryThreadStore`
- `InMemoryThreadStoreCalls`
- `InMemoryThreadStore::for_id`
- `InMemoryThreadStore::remove_id`
- `InMemoryThreadStore::calls`
- `ThreadStore for InMemoryThreadStore`
- `stored_thread_from_state`
- Rust test `default_turn_pagination_methods_return_unsupported`

## Covered Contract

- Default turn and item pagination return `ThreadStoreError::Unsupported`
  with operation names `list_turns` and `list_items`.
- `for_id` returns a globally shared store until `remove_id` removes it.
- Call counters are incremented by the in-memory store methods and returned by
  `calls`.
- `create_thread` records params and initializes an empty history.
- `resume_thread` initializes an empty history and records `rollout_path`
  lookup without importing caller-provided replay history.
- `append_items` appends rollout items in order, and `load_history` returns the
  stored replay items or `thread_not_found`.
- `read_thread_by_rollout_path` resolves the recorded rollout path or returns
  an `invalid_request` message matching the Rust source contract.
- `list_threads` returns thread summaries sorted by `ThreadId` string and no
  continuation cursor.
- `update_thread_metadata` merges metadata by field presence; archive is a
  call-count no-op; unarchive returns the stored thread.
- Unpatched `StoredThread` defaults match Rust's test implementation:
  `model_provider = "test"`, `cli_version = "test"`, empty `cwd`, approval
  `Never`, and read-only sandbox policy.

## Python Tests

- `tests/test_thread_store_in_memory_rs.py::test_in_memory_default_turn_pagination_methods_return_unsupported`
- `tests/test_thread_store_in_memory_rs.py::test_in_memory_for_id_remove_id_and_call_counts_are_shared`
- `tests/test_thread_store_in_memory_rs.py::test_in_memory_resume_tracks_rollout_path_without_preloading_history`
- `tests/test_thread_store_in_memory_rs.py::test_in_memory_create_append_read_list_and_metadata_defaults_match_rust`
- `tests/test_thread_store_in_memory_rs.py::test_in_memory_metadata_patch_merges_and_archive_unarchive_call_paths`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `6 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_in_memory_rs.py`
  - passed

## Remaining Outside This Slice

- Full `src/types.rs` serde optional-clear shape and all type tests.
- `src/thread_metadata_sync.rs`.
- `src/live_thread.rs`.
- `src/local/*` rollout/state-db backed local store behavior.
- Exact Tokio mutex/runtime identity.
