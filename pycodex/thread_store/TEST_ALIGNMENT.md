# codex-thread-store Test Alignment

Rust crate: `codex-thread-store`
Python package: `pycodex.thread_store`

## Alignment Table

| Rust source/test | Rust behavior | Python test | Status |
|---|---|---|---|
| `src/types.rs::thread_metadata_patch_round_trips_optional_clears` | Clearable `ThreadMetadataPatch` fields serialize as explicit JSON null and deserialize as present clear requests. | `tests/test_thread_store_types_rs.py::test_thread_metadata_patch_round_trips_optional_clears` | complete |
| `src/types.rs::git_info_patch_round_trips_optional_clears` | Nested `GitInfoPatch` omits absent fields, serializes present values, and preserves explicit clear requests. | `tests/test_thread_store_types_rs.py::test_git_info_patch_round_trips_optional_clears` | complete |
| `src/types.rs::thread_metadata_patch_accepts_missing_fields` | Missing fields deserialize as omitted no-op patch values and leave the patch empty. | `tests/test_thread_store_types_rs.py::test_thread_metadata_patch_accepts_missing_fields` | complete |
| `src/types.rs::thread_metadata_patch_merge_uses_presence_semantics` | Omitted fields leave current values unchanged; present clear requests clear values; nested git patch fields merge independently. | `tests/test_thread_store_types_rs.py::test_thread_metadata_patch_merge_uses_presence_semantics` | complete |
| `src/store.rs::ThreadStore` | The storage-neutral public trait exposes create/resume/append/persist/flush/shutdown/discard/history/read/path-read/list/search/turns/items/update/archive/unarchive operation names. | `tests/test_thread_store_store_error_rs.py::test_thread_store_protocol_exposes_rust_trait_surface` | complete |
| `src/error.rs::ThreadStoreError` | Error variants keep Rust field names and display-message shapes for not-found, invalid request, conflict, unsupported, and internal failures. | `tests/test_thread_store_store_error_rs.py::test_thread_store_error_variants_match_rust_messages_and_fields` | complete |
| `src/in_memory.rs::default_turn_pagination_methods_return_unsupported` | Default in-memory turn/item pagination methods return `ThreadStoreError::Unsupported` with operation names `list_turns` and `list_items`. | `tests/test_thread_store_in_memory_rs.py::test_in_memory_default_turn_pagination_methods_return_unsupported` | complete |
| `src/in_memory.rs::{for_id,remove_id,calls}` | In-memory stores are shared by id until removal and expose cloned call counters. | `tests/test_thread_store_in_memory_rs.py::test_in_memory_for_id_remove_id_and_call_counts_are_shared` | complete_slice |
| `src/in_memory.rs::resume_thread/read_thread_by_rollout_path/load_history` | Resume initializes an empty history, records rollout-path lookup, and does not import caller-provided history. | `tests/test_thread_store_in_memory_rs.py::test_in_memory_resume_tracks_rollout_path_without_preloading_history` | complete_slice |
| `src/in_memory.rs::create_thread/append_items/read_thread/list_threads/stored_thread_from_state` | Created threads have empty histories, appended items replay in order, list results sort by thread id string, and unpatched stored-thread fields use Rust test defaults. | `tests/test_thread_store_in_memory_rs.py::test_in_memory_create_append_read_list_and_metadata_defaults_match_rust` | complete_slice |
| `src/in_memory.rs::update_thread_metadata/archive_thread/unarchive_thread` | Metadata patches merge by field presence; archive is call-count-only; unarchive returns the stored thread. | `tests/test_thread_store_in_memory_rs.py::test_in_memory_metadata_patch_merges_and_archive_unarchive_call_paths` | complete_slice |
| `src/thread_metadata_sync.rs::resume_history_keeps_derived_metadata_pending_until_applied` | Resume history derives metadata, `take_pending_update` is retry-safe, and applying the matching generation clears pending state. | `tests/test_thread_store_metadata_sync_rs.py::test_resume_history_keeps_derived_metadata_pending_until_applied` | complete |
| `src/thread_metadata_sync.rs::goal_update_sets_preview_without_overriding_existing_preview` | A goal objective claims preview first while the first user message still fills title and first-user-message. | `tests/test_thread_store_metadata_sync_rs.py::test_goal_update_sets_preview_without_overriding_existing_preview` | complete |
| `src/thread_metadata_sync.rs::later_user_messages_do_not_emit_existing_preview_fields` | Once preview/title/first_user_message have been seen, later user messages only produce an updated-at touch. | `tests/test_thread_store_metadata_sync_rs.py::test_later_user_messages_do_not_emit_existing_preview_fields` | complete |
| `src/thread_metadata_sync.rs::metadata_irrelevant_items_coalesce_updated_at_touches` | Metadata-irrelevant appends coalesce updated-at touches inside the Rust test interval but keep a barrier update pending. | `tests/test_thread_store_metadata_sync_rs.py::test_metadata_irrelevant_items_coalesce_updated_at_touches` | complete |
| `src/thread_metadata_sync.rs::resume_history_waits_for_append_before_flushing_metadata` | Resume-derived metadata is deferred from existing-history flush until the first append barrier. | `tests/test_thread_store_metadata_sync_rs.py::test_resume_history_waits_for_append_before_flushing_metadata` | complete |
| `src/live_thread.rs::append_items` and `src/local/mod.rs::live_thread_observes_appended_items_into_sqlite_metadata` | LiveThread appends canonical persisted items, observes metadata, applies the pending metadata patch, and flushes the thread. | `tests/test_thread_store_live_thread_rs.py::test_live_thread_observes_appended_items_into_store_metadata` | complete_slice |
| `src/live_thread.rs::append_items` | If `persisted_rollout_items` yields no canonical items, LiveThread returns without appending or updating metadata. | `tests/test_thread_store_live_thread_rs.py::test_live_thread_skips_non_persisted_append_items` | complete_slice |
| `src/live_thread.rs::resume` and `src/local/mod.rs::live_thread_resume_loads_history_before_observing_metadata` | Resume with no provided history loads store history before constructing metadata sync, so historical session facts win over resume params and later appends. | `tests/test_thread_store_live_thread_rs.py::test_live_thread_resume_loads_history_before_observing_metadata` | complete_slice |
| `src/live_thread.rs::update_metadata` | Explicit metadata updates flush pending metadata before applying the caller's patch. | `tests/test_thread_store_live_thread_rs.py::test_live_thread_update_metadata_flushes_pending_metadata_first` | complete_slice |
| `src/local/mod.rs::live_writer_lifecycle_writes_and_closes` | Local live writer create/append/persist/flush writes JSONL, and shutdown removes the writer so later appends return thread-not-found. | `tests/test_thread_store_local_live_writer_rs.py::test_local_live_writer_lifecycle_writes_and_closes` | complete_slice |
| `src/local/mod.rs::create_thread_rejects_missing_cwd` | Local thread creation requires `metadata.cwd` and returns the Rust invalid-request message. | `tests/test_thread_store_local_live_writer_rs.py::test_local_create_thread_rejects_missing_cwd` | complete |
| `src/local/mod.rs::discard_thread_drops_unmaterialized_live_writer` | Discarding a never-materialized local live writer removes it without creating the rollout file and later appends return thread-not-found. | `tests/test_thread_store_local_live_writer_rs.py::test_local_discard_thread_drops_unmaterialized_live_writer` | complete_slice |
| `src/local/mod.rs::{create_thread_rejects_duplicate_live_writer,resume_thread_rejects_duplicate_live_writer}` | Local create and resume reject duplicate live writers for the same thread id. | `tests/test_thread_store_local_live_writer_rs.py::test_local_create_and_resume_reject_duplicate_live_writer` | complete_slice |
| `src/local/read_thread.rs::read_thread_returns_active_rollout_summary` | `read_thread` locates an active rollout by id, builds preview/first-user-message from the first user event, and attaches rollout history when requested. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_returns_active_rollout_summary` | complete_slice |
| `src/local/read_thread.rs::read_thread_returns_rollout_path_summary` | `read_thread_by_rollout_path` accepts a path relative to `codex_home`, canonicalizes it, and builds the rollout summary without history. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_returns_rollout_path_summary` | complete_slice |
| `src/local/read_thread.rs::read_thread_by_rollout_path_prefers_sqlite_git_info` | `read_thread_by_rollout_path` overlays SQLite git fields and preserves missing git fields from rollout metadata. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_by_rollout_path_prefers_sqlite_git_info` | complete_slice |
| `src/local/read_thread.rs::read_thread_returns_forked_from_id` | `read_thread` overlays `forked_from_id` from the session metadata after reading the rollout summary. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_returns_forked_from_id` | complete_slice |
| `src/local/read_thread.rs::read_thread_returns_archived_rollout_when_requested` | Active-only lookup ignores archived rollouts; `include_archived` resolves them and marks `archived_at`. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_returns_archived_rollout_when_requested` | complete_slice |
| `src/local/read_thread.rs::read_thread_prefers_active_rollout_over_archived` | When active and archived rollouts share an id, `include_archived` still returns the active rollout first. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_prefers_active_rollout_over_archived` | complete_slice |
| `src/local/read_thread.rs::read_thread_uses_legacy_thread_name_when_sqlite_title_is_missing` | Rollout-backed reads apply the legacy thread-name index when SQLite metadata has no title. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_uses_legacy_thread_name_when_sqlite_title_is_missing` | complete_slice |
| `src/local/read_thread.rs::read_thread_uses_sqlite_metadata_for_rollout_without_user_preview` | If SQLite metadata is present and the rollout can load history but has no preview, SQLite metadata fields are returned while history loads from rollout. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_uses_sqlite_metadata_for_rollout_without_user_preview` | complete_slice |
| `src/local/read_thread.rs::read_thread_applies_sqlite_thread_name` | Without requested history, read_thread may use rollout preview/cwd/provider while preserving a distinct SQLite title as the thread name. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_applies_sqlite_thread_name` | complete_slice |
| `src/local/read_thread.rs::read_thread_falls_back_to_sqlite_summary` | When history is not requested, valid SQLite metadata can be returned even if the rollout path is external or missing. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_falls_back_to_sqlite_summary` | complete_slice |
| `src/local/read_thread.rs::read_thread_sqlite_fallback_respects_include_archived` | Archived SQLite metadata is hidden from active-only reads and returned when `include_archived` is true. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_sqlite_fallback_respects_include_archived` | complete_slice |
| `src/local/read_thread.rs::read_thread_sqlite_fallback_loads_archived_history` | Archived SQLite metadata can load archived rollout history when both include flags are true. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_sqlite_fallback_loads_archived_history` | complete_slice |
| `src/local/read_thread.rs::read_thread_falls_back_to_rollout_search_when_sqlite_path_is_stale` | If history is requested and the SQLite rollout path is missing, read_thread falls back to filesystem rollout search. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_falls_back_to_rollout_search_when_sqlite_path_is_stale` | complete_slice |
| `src/local/read_thread.rs::read_thread_falls_back_when_sqlite_path_points_to_another_thread` | If history is requested and the SQLite rollout path points to a different thread, read_thread falls back to filesystem rollout search. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_falls_back_when_sqlite_path_points_to_another_thread` | complete_slice |
| `src/local/read_thread.rs::read_thread_uses_session_meta_for_rollout_without_user_preview_or_sqlite_metadata` | If a rollout has no user preview, `read_thread` falls back to session metadata and can still attach one-item history. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_uses_session_meta_when_rollout_has_no_user_preview` | complete_slice |
| `src/local/read_thread.rs::read_thread_fails_without_rollout` | Missing rollout lookup returns an invalid-request error with the Rust no-rollout message. | `tests/test_thread_store_local_read_thread_rs.py::test_read_thread_fails_without_rollout` | complete_slice |
| `src/local/list_threads.rs::list_threads_uses_default_provider_when_rollout_omits_provider` | Missing rollout `model_provider` fields are filled from `LocalThreadStoreConfig.default_model_provider_id`. | `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_uses_default_provider_when_rollout_omits_provider` | complete_slice |
| `src/local/list_threads.rs::list_threads_selects_active_or_archived_collection` | Active listings scan `sessions`, archived listings scan `archived_sessions`, and archived results are marked archived. | `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_selects_active_or_archived_collection` | complete_slice |
| `src/local/list_threads.rs::list_threads_returns_local_rollout_summary` | Local rollout listings project thread id/path/preview/first message/provider/version/source and honor source/provider filters. | `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_returns_local_rollout_summary` | complete_slice |
| `src/local/list_threads.rs::list_threads_rejects_invalid_cursor` | Invalid cursor strings fail as `invalid_request` before any rollout listing. | `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_rejects_invalid_cursor` | complete_slice |
| `src/local/list_threads.rs::list_threads_preserves_sqlite_title_search_results` | State-db-only title search can match SQLite title while preserving the first user message preview and distinct thread name. | `tests/test_thread_store_local_list_threads_rs.py::test_list_threads_preserves_sqlite_title_search_results` | complete_slice |
| `src/local/search_threads.rs::search_threads empty search branch` | Empty search terms fail as `invalid_request` before rollout scanning. | `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_rejects_empty_search_term` | complete_slice |
| `src/local/search_threads.rs::search_threads parse_cursor boundary` | Invalid cursor strings fail as `invalid_request` before listing search pages. | `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_rejects_invalid_cursor` | complete_slice |
| `src/local/search_threads.rs::search_threads matching_paths.is_empty branch` | No rollout content matches returns an empty `ThreadSearchPage` with no next cursor. | `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_returns_empty_page_when_no_rollout_matches` | complete_slice |
| `src/local/search_threads.rs::search_threads + first_rollout_content_match_snippet` | Matching rollout content yields a `StoredThreadSearchResult` summary and first content snippet. | `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_returns_snippet_and_rollout_summary` | complete_slice |
| `src/local/search_threads.rs::cursor_from_thread_search_item` | Search scans in list order, keeps one extra match for pagination, and resumes after the returned cursor. | `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_paginates_by_matching_sorted_rollouts` | complete_slice |
| `src/local/search_threads.rs::set_thread_search_result_names` | Search results receive distinct state-db titles without replacing the first message snippet. | `tests/test_thread_store_local_search_threads_rs.py::test_search_threads_applies_sqlite_title_to_result_name` | complete_slice |
| `src/local/archive_thread.rs::archive_thread_moves_rollout_to_archived_collection` | Active rollout files are moved into `archived_sessions`, disappear from active path, and are visible through archived listing with `archived_at`. | `tests/test_thread_store_local_archive_unarchive_rs.py::test_archive_thread_moves_rollout_to_archived_collection` | complete_slice |
| `src/local/archive_thread.rs::archive_thread_updates_sqlite_metadata_when_present` | When state metadata exists, archiving updates rollout path and archived timestamp through `mark_archived`. | `tests/test_thread_store_local_archive_unarchive_rs.py::test_archive_thread_updates_sqlite_metadata_when_present` | complete_slice |
| `src/local/unarchive_thread.rs::unarchive_thread_restores_rollout_and_returns_updated_thread` | Archived rollout files are restored into dated `sessions` directories and returned as active `StoredThread` summaries. | `tests/test_thread_store_local_archive_unarchive_rs.py::test_unarchive_thread_restores_rollout_and_returns_updated_thread` | complete_slice |
| `src/local/unarchive_thread.rs::unarchive_thread_updates_sqlite_metadata_when_present` | When state metadata exists, unarchiving updates rollout path and clears archived timestamp through `mark_unarchived`. | `tests/test_thread_store_local_archive_unarchive_rs.py::test_unarchive_thread_updates_sqlite_metadata_when_present` | complete_slice |
| `src/local/update_thread_metadata.rs::update_thread_metadata_sets_name_on_active_rollout_and_indexes_name` | Explicit name patches update returned thread metadata and append the local thread-name index entry. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_sets_name_on_active_rollout_and_indexes_name` | complete_slice |
| `src/local/update_thread_metadata.rs::update_thread_metadata_sets_memory_mode_on_active_rollout` | Memory-mode patches append a same-thread `session_meta` marker with the new memory mode to the active rollout. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_sets_memory_mode_on_active_rollout` | complete_slice |
| `src/local/update_thread_metadata.rs::update_thread_metadata_applies_combined_explicit_patch git branch path` | Explicit git patches resolve unspecified fields from SQLite, append git session metadata to the rollout, and update state-db git columns. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_sets_git_info_on_active_rollout_and_state_db` | complete_slice |
| `src/local/update_thread_metadata.rs::resolve_git_info_patch` | Clearable git fields resolve to `None` while omitted fields preserve existing SQLite values. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_clears_git_origin_url` | complete_slice |
| `src/local/update_thread_metadata.rs::metadata_patch_applies_title_over_existing_name` | Observed title metadata can replace an earlier explicit thread name on returned thread summaries while preserving rollout preview. | `tests/test_thread_store_local_update_metadata_rs.py::test_metadata_patch_applies_title_over_existing_name` | complete_slice |
| `src/local/update_thread_metadata.rs::metadata_patch_applies_latest_preview_and_first_user_message` | Later observed preview/first-user-message updates replace state metadata while returned thread summaries continue to reflect rollout content. | `tests/test_thread_store_local_update_metadata_rs.py::test_metadata_patch_applies_latest_preview_and_first_user_message` | complete_slice |
| `src/local/update_thread_metadata.rs::observed_metadata_normalizes_cwd_for_list_filters` | Observed cwd metadata is normalized before state-db upsert and state-db-only list filters match the normalized path. | `tests/test_thread_store_local_update_metadata_rs.py::test_observed_metadata_normalizes_cwd_for_list_filters` | complete_slice |
| `src/local/update_thread_metadata.rs::apply_metadata_update observed field assignments` | Observed provider/model/reasoning/source/thread-source/agent/policy/token metadata fields update the state row using Rust string/clamp semantics. | `tests/test_thread_store_local_update_metadata_rs.py::test_observed_metadata_updates_remaining_state_fields` | complete_slice |
| `src/local/update_thread_metadata.rs::update_thread_metadata_recreates_missing_archived_sqlite_row_as_archived` | Updating an archived rollout without an existing state row recreates metadata with `archived_at` set. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_recreates_missing_archived_state_row_as_archived` | complete_slice |
| `src/local/update_thread_metadata.rs::update_thread_metadata_keeps_archived_thread_archived_in_sqlite` | Explicit updates to archived state rows preserve `archived_at` on the state row and returned summary. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_keeps_archived_thread_archived_in_state_db` | complete_slice |
| `src/local/update_thread_metadata.rs::update_thread_metadata_keeps_live_archived_thread_archived_in_sqlite` | Explicit updates to resumed live archived threads preserve `archived_at` on the state row and returned summary. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_keeps_live_archived_thread_archived_in_state_db` | complete_slice |
| `src/local/update_thread_metadata.rs::update_thread_metadata_applies_combined_explicit_patch` | Name and memory-mode rollout compatibility updates can be applied in one explicit patch. | `tests/test_thread_store_local_update_metadata_rs.py::test_update_thread_metadata_applies_combined_explicit_patch` | complete_slice |
| `src/local/update_thread_metadata.rs::sqlite_failures_are_best_effort_for_legacy_rollout_compat_updates` | Internal state-db failures during legacy rollout compatibility updates do not block JSONL/index compatibility updates. | `tests/test_thread_store_local_update_metadata_rs.py::test_sqlite_failures_are_best_effort_for_legacy_rollout_compat_updates` | complete_slice |
| `src/local/update_thread_metadata.rs::sqlite_failures_are_best_effort_for_observed_metadata_updates` | Internal state-db failures during observed metadata updates do not block rollout summary reads. | `tests/test_thread_store_local_update_metadata_rs.py::test_sqlite_failures_are_best_effort_for_observed_metadata_updates` | complete_slice |
| `src/local/update_thread_metadata.rs::sqlite_failures_still_block_for_explicit_git_only_updates` | Git-only updates still block on state DB failures because omitted git fields merge from SQLite metadata. | `tests/test_thread_store_local_update_metadata_rs.py::test_sqlite_failures_still_block_for_explicit_git_only_updates` | complete_slice |

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_store_error_rs.py -q --tb=short`
  - `2 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_store_error_rs.py`
  - passed
- `python -m pytest tests\test_thread_store_store_error_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract -q --tb=short`
  - `72 passed`

- `python -m pytest tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `6 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_in_memory_rs.py`
  - passed

2026-06-22 types follow-up:

- `python -m pytest tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `9 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `10 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py`
  - passed

2026-06-22 thread metadata sync follow-up:

- `python -m pytest tests\test_thread_store_metadata_sync_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `14 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `15 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_metadata_sync_rs.py`
  - passed

2026-06-22 live thread follow-up:

- `python -m pytest tests\test_thread_store_live_thread_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `18 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `19 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_live_thread_rs.py`
  - passed

2026-06-22 local live-writer follow-up:

- `python -m pytest tests\test_thread_store_local_live_writer_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `22 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `23 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_live_writer_rs.py`
  - passed

2026-06-22 local update metadata follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `3 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `25 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `26 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 local update metadata git-info follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `58 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `59 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 local update metadata observed title/preview follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `7 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `60 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `61 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 local update metadata observed cwd follow-up:

- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py -q --tb=short`
  - `8 passed`
- `python -m pytest tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `61 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `62 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_update_metadata_rs.py`
  - passed

2026-06-22 local read thread follow-up:

- `python -m pytest tests\test_thread_store_local_read_thread_rs.py -q --tb=short`
  - `16 passed`
- `python -m pytest tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `41 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `42 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_read_thread_rs.py`
  - passed

2026-06-22 local list threads follow-up:

- `python -m pytest tests\test_thread_store_local_list_threads_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `46 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `47 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_list_threads_rs.py`
  - passed

2026-06-22 local search threads follow-up:

- `python -m pytest tests\test_thread_store_local_search_threads_rs.py -q --tb=short`
  - `6 passed`
- `python -m pytest tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `52 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `53 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_search_threads_rs.py`
  - passed

2026-06-22 local archive/unarchive follow-up:

- `python -m pytest tests\test_thread_store_local_archive_unarchive_rs.py -q --tb=short`
  - `4 passed`
- `python -m pytest tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `56 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_local_archive_unarchive_rs.py tests\test_thread_store_local_search_threads_rs.py tests\test_thread_store_local_list_threads_rs.py tests\test_thread_store_local_read_thread_rs.py tests\test_thread_store_local_update_metadata_rs.py tests\test_thread_store_local_live_writer_rs.py tests\test_thread_store_live_thread_rs.py tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `57 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_local_archive_unarchive_rs.py`
  - passed

## Notes

- `python -m pytest tests\test_external_crate_interfaces.py tests\test_thread_store_in_memory_rs.py -q --tb=short` currently reports unrelated failures in `test_model_provider_bearer_auth_and_configured_provider` and `test_utils_cache_lru_and_sha1_digest`; the thread-store-specific external interface test passes when run directly with the new Rust-derived tests.
