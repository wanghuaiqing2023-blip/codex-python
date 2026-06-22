# codex-thread-store src/local/list_threads.rs Status

Rust crate: `codex-thread-store`
Rust module: `src/local/list_threads.rs`
Python surface: `pycodex.thread_store.LocalThreadStore.list_threads`

## Status

`complete_slice`

This module-scoped behavior contract is covered for the Rust tests currently present in
`src/local/list_threads.rs`.

## Rust Anchors

- `list_threads`
- `list_rollout_threads`
- `parse_cursor`
- `stored_thread_from_rollout_item`
- `distinct_thread_metadata_title`
- `find_thread_names_by_ids`
- `set_thread_name_from_title`

## Python Coverage

- Active listings scan `sessions`; archived listings scan `archived_sessions`.
- Archived rollout results are returned only for archived listings and are marked with `archived_at`.
- Invalid cursor strings raise `ThreadStoreError.invalid_request` before listing.
- Rollouts missing `model_provider` use `LocalThreadStoreConfig.default_model_provider_id`.
- Local rollout summaries project thread id, rollout path, preview, first user message, provider, CLI version, and source.
- Source and provider filters pass through to the rollout listing layer.
- State-db-only title search can match a persisted title while preserving preview/first user message.
- SQLite titles and legacy thread-name index entries are overlaid as distinct `StoredThread.name` values.

## Rust-Derived Tests

- `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_uses_default_provider_when_rollout_omits_provider`
- `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_selects_active_or_archived_collection`
- `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_returns_local_rollout_summary`
- `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_rejects_invalid_cursor`
- `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_preserves_sqlite_title_search_results`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_local_list_threads_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `46 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `47 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_list_threads_rs.py`
  - passed

## Remaining Crate Gaps

This file does not close the whole `codex-thread-store` crate. Remaining local-store
modules include `src/local/search_threads.rs`, `src/local/archive_thread.rs`, and
`src/local/unarchive_thread.rs`; `src/local/update_thread_metadata.rs` still has git-info,
SQLite repair/indexing, archived-row, and full observed-metadata behavior gaps.
