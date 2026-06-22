# codex-thread-store src/local/search_threads.rs Status

Rust crate: `codex-thread-store`
Rust module: `src/local/search_threads.rs`
Python surface: `pycodex.thread_store.LocalThreadStore.search_threads`

## Status

`complete_slice`

This module-scoped behavior contract is covered by Rust-source-derived Python
tests for the search flow in `src/local/search_threads.rs`.

## Rust Anchors

- `search_threads`
- `search_rollout_paths`
- `first_rollout_content_match_snippet`
- `list_rollout_threads`
- `cursor_from_thread_search_item`
- `set_thread_search_result_names`
- `distinct_thread_metadata_title`
- `find_thread_names_by_ids`
- `set_thread_name_from_title`

## Python Coverage

- Empty `search_term` returns `ThreadStoreError.invalid_request`.
- Invalid cursor strings return `ThreadStoreError.invalid_request`.
- No matching rollout content returns an empty `ThreadSearchPage`.
- Matching rollout content is converted into `StoredThreadSearchResult` values with snippets.
- Search scans results in the same sorted listing order used by `list_threads`.
- Search keeps one extra matching item to decide whether a next cursor is available.
- The next cursor is derived from the last returned matching thread item timestamp.
- Source filters and active/archived roots are delegated through the local list/rollout path.
- Distinct state-db titles and legacy thread names are overlaid on search result threads.

## Rust-Derived Tests

- `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_rejects_empty_search_term`
- `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_rejects_invalid_cursor`
- `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_returns_empty_page_when_no_rollout_matches`
- `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_returns_snippet_and_rollout_summary`
- `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_paginates_by_matching_sorted_rollouts`
- `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_applies_sqlite_title_to_result_name`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_local_search_threads_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `52 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `53 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_search_threads_rs.py`
  - passed

## Remaining Crate Gaps

This file does not close the whole `codex-thread-store` crate. Remaining local-store
modules include `src/local/archive_thread.rs` and `src/local/unarchive_thread.rs`;
`src/local/update_thread_metadata.rs` still has git-info, SQLite repair/indexing,
archived-row, and full observed-metadata behavior gaps.
