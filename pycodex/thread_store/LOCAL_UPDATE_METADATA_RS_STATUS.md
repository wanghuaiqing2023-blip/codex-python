# codex-thread-store src/local/update_thread_metadata.rs

Rust crate: `codex-thread-store`
Rust module: `src/local/update_thread_metadata.rs`
Python package: `pycodex.thread_store`

## Status

`complete_slice`

## Rust Anchors

- `update_thread_metadata`
- `needs_rollout_compatibility_update`
- `apply_thread_name`
- `apply_thread_memory_mode`
- `resolve_git_info_patch`
- `apply_thread_git_info_to_rollout`
- `apply_thread_git_info`
- `memory_mode_as_str`
- `resolve_rollout_path`
- `rollout_path_is_archived`

## Covered Contract

- Empty-patch handling still delegates to the existing read path.
- Explicit `name` patches update the returned thread metadata and append the
  local thread-name index entry under `codex_home`.
- Explicit `memory_mode` patches resolve the active rollout path, materialize a
  live writer if needed, verify the rollout session metadata id, and append a
  same-thread `session_meta` marker with the new memory mode.
- Combined explicit name and memory-mode patches apply both rollout
  compatibility updates.
- Explicit git-info patches require state metadata, resolve omitted fields from
  existing SQLite git metadata, support clear semantics, append a `session_meta`
  marker with `git` payload to the rollout, and update state-db git columns.
- Observed `title`, `preview`, and `first_user_message` patches update state
  metadata while returned thread summaries continue to reflect rollout content;
  observed titles can replace prior explicit names on returned summaries.
- Observed `cwd` patches are normalized before state metadata upsert and
  state-db-only list filters match the normalized path.
- Remaining observed provider/model/reasoning/source/thread-source/agent/policy
  and token-usage fields update state metadata with Rust string/clamp
  semantics.
- Archived rollout metadata updates recreate missing state rows with
  `archived_at` set, and explicit updates to existing archived state rows keep
  the row and returned summary archived.
- Resumed live archived threads keep their archived state when explicit metadata
  updates flush/persist the live writer before applying the patch.
- SQLite/Internal write failures are best-effort for legacy rollout
  compatibility and observed metadata updates, but still block explicit
  git-only updates that require SQLite metadata merging.

## Python Tests

- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_sets_name_on_active_rollout_and_indexes_name`
- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_sets_memory_mode_on_active_rollout`
- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_sets_git_info_on_active_rollout_and_state_db`
- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_clears_git_origin_url`
- `tests/test_thread_store_local_update_metadata_rs.py::test_metadata_patch_applies_title_over_existing_name`
- `tests/test_thread_store_local_update_metadata_rs.py::test_metadata_patch_applies_latest_preview_and_first_user_message`
- `tests/test_thread_store_local_update_metadata_rs.py::test_observed_metadata_normalizes_cwd_for_list_filters`
- `tests/test_thread_store_local_update_metadata_rs.py::test_observed_metadata_updates_remaining_state_fields`
- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_recreates_missing_archived_state_row_as_archived`
- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_keeps_archived_thread_archived_in_state_db`
- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_keeps_live_archived_thread_archived_in_state_db`
- `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_applies_combined_explicit_patch`
- `tests/test_thread_store_local_update_metadata_rs.py::test_sqlite_failures_are_best_effort_for_legacy_rollout_compat_updates`
- `tests/test_thread_store_local_update_metadata_rs.py::test_sqlite_failures_are_best_effort_for_observed_metadata_updates`
- `tests/test_thread_store_local_update_metadata_rs.py::test_sqlite_failures_still_block_for_explicit_git_only_updates`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `15 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `68 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `69 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 observed fields follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `12 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `65 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `66 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 live archived follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `11 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `64 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `65 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 archived-row follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `10 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `63 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `64 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 earlier explicit patch slice:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `3 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `25 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `26 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 observed cwd follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `8 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `61 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `62 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 observed title/preview follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `60 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `61 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 git-info follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `58 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `59 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

## Remaining Outside This Slice

- SQLite repair/indexing of missing rows.
- Crate-level `ThreadStore` trait/runtime audit remains open.
