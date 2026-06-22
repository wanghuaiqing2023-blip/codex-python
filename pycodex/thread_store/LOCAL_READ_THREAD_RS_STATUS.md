# codex-thread-store local/read_thread.rs status

Rust crate: `codex-thread-store`
Rust module: `codex/codex-rs/thread-store/src/local/read_thread.rs`
Python surface: `pycodex.thread_store.LocalThreadStore`

## Status

`complete_slice`

This slice covers dependency-light active and archived rollout-file reads
without SQLite/state-db metadata. The implemented contract mirrors the Rust
fallback path from
`read_thread` through `resolve_rollout_path`, `read_thread_from_rollout_path`,
`stored_thread_from_rollout_item`, `stored_thread_from_session_meta`, and
`attach_history_if_requested`.

## Covered Rust-Derived Contracts

- `read_thread_returns_active_rollout_summary`
  - `read_thread` locates an active rollout by id, reads preview and
    first-user-message from the first user event, and attaches rollout history.
- `read_thread_returns_rollout_path_summary`
  - `read_thread_by_rollout_path` accepts a path relative to `codex_home`,
    canonicalizes it, and builds the summary without history.
- `read_thread_by_rollout_path_prefers_sqlite_git_info`
  - `read_thread_by_rollout_path` overlays SQLite git fields while preserving
    missing git fields from rollout metadata.
- `read_thread_returns_forked_from_id`
  - `forked_from_id` from session metadata is preserved on the stored thread.
- `read_thread_returns_archived_rollout_when_requested`
  - Active-only lookup ignores archived rollouts; include-archived lookup
    resolves them and marks `archived_at`.
- `read_thread_prefers_active_rollout_over_archived`
  - Active rollouts take precedence over archived rollouts even when archived
    lookup is enabled.
- `read_thread_uses_legacy_thread_name_when_sqlite_title_is_missing`
  - Rollout-backed reads apply the legacy thread-name index when SQLite metadata
    has no title.
- `read_thread_uses_sqlite_metadata_for_rollout_without_user_preview`
  - SQLite metadata fields are returned when a rollout can load history but has
    no preview of its own.
- `read_thread_applies_sqlite_thread_name`
  - Without requested history, rollout preview/cwd/provider can be used while a
    distinct SQLite title is preserved as `name`.
- `read_thread_falls_back_to_sqlite_summary`
  - Valid SQLite metadata can be returned without a readable rollout when
    history is not requested.
- `read_thread_sqlite_fallback_respects_include_archived`
  - Archived SQLite metadata is hidden from active-only reads and returned when
    `include_archived` is true.
- `read_thread_sqlite_fallback_loads_archived_history`
  - Archived SQLite metadata can load archived rollout history when both include
    flags are true.
- `read_thread_falls_back_to_rollout_search_when_sqlite_path_is_stale`
  - History reads verify the SQLite rollout path and fall back to filesystem
    rollout search when it is missing.
- `read_thread_falls_back_when_sqlite_path_points_to_another_thread`
  - History reads verify the SQLite rollout path belongs to the requested
    thread before trusting it.
- `read_thread_uses_session_meta_for_rollout_without_user_preview_or_sqlite_metadata`
  - When no user preview exists, the thread is built from `session_meta` and can
    still load one-item history.
- `read_thread_fails_without_rollout`
  - Missing rollout lookup returns an invalid-request no-rollout error.

## Python Tests

- `tests/test_thread_store_local_read_thread_rs.py`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_local_read_thread_rs.py -q --tb=short`
  - `16 passed`
- `python -m pytest tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `41 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `42 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_read_thread_rs.py`
  - passed

## Remaining Module Gaps

- No independent `src/local/read_thread.rs` behavior gaps remain in this status file.
- Crate-level completion still depends on neighboring local modules and update-metadata state-db paths.
