# codex-rollout test alignment

## lib.rs

- `SESSIONS_SUBDIR`, `ARCHIVED_SESSIONS_SUBDIR`, `INTERACTIVE_SESSION_SOURCES`, `SortDirection`, and `find_conversation_path_by_id_str` public surface/re-export compatibility -> `tests/test_core_rollout_reexport.py::CoreRolloutReexportTests::test_core_rollout_reexports_existing_rollout_surface`, `test_interactive_session_sources_match_rust_rollout_constant`, and `test_core_rollout_exposes_small_enums_and_local_bridges`.

Status: `complete_slice`; rollout crate public constants, interactive source list, sort direction enum, and deprecated conversation-path alias are covered.

## config.rs

- `RolloutConfig::from_view` and `Config = RolloutConfig` alias -> `tests/test_core_rollout.py::CoreRolloutTests::test_rollout_config_from_view_copies_config_values`.

Status: `complete_slice`; config view copying and alias behavior are covered.
## metadata.rs

- `metadata_tests.rs::builder_from_items_falls_back_to_filename` -> `tests/test_rollout_metadata.py::test_builder_from_items_falls_back_to_filename`.
- `metadata.rs::builder_from_items` session-meta preference -> `tests/test_rollout_metadata.py::test_builder_from_items_uses_session_meta_before_filename`.
- `metadata.rs::parse_timestamp_to_utc` -> `tests/test_rollout_metadata.py::test_parse_timestamp_to_utc_accepts_filename_timestamp_and_rfc3339`.
- `metadata.rs::backfill_watermark_for_path` -> `tests/test_rollout_metadata.py::test_backfill_watermark_for_path_strips_codex_home_and_normalizes_separators`.
- `metadata_tests.rs::extract_metadata_from_rollout_uses_session_meta` -> `tests/test_rollout_metadata.py::test_extract_metadata_from_rollout_uses_session_meta`.
- `metadata_tests.rs::extract_metadata_from_rollout_returns_latest_memory_mode` -> `tests/test_rollout_metadata.py::test_extract_metadata_from_rollout_returns_latest_memory_mode`.
- `metadata_tests.rs::backfill_sessions_resumes_from_watermark_and_marks_complete` -> `tests/test_rollout_metadata.py::test_backfill_sessions_resumes_from_watermark_and_marks_complete`.
- `metadata_tests.rs::backfill_sessions_preserves_existing_git_branch_and_fills_missing_git_fields` -> `tests/test_rollout_metadata.py::test_backfill_sessions_preserves_existing_git_branch_and_fills_missing_git_fields`.
- `metadata_tests.rs::backfill_sessions_normalizes_cwd_before_upsert` -> `tests/test_rollout_metadata.py::test_backfill_sessions_normalizes_cwd_before_upsert`.
- `metadata.rs` archived-root backfill branch -> `tests/test_rollout_metadata.py::test_backfill_sessions_marks_archived_rollout_metadata`.

Status: `complete_slice`; `metadata.rs` backfill control-flow slices are now covered at the semantic helper level.

## list.rs

- `ThreadListLayout::Flat` root-only scan behavior -> `tests/test_core_rollout.py::CoreRolloutTests::test_get_threads_in_root_flat_layout_only_scans_root_files`.

Status: `complete_slice`; flat-vs-nested scan layout behavior is covered.

## session_index.rs

- `find_thread_name_by_id` latest append-order lookup -> `tests/test_core_rollout.py::CoreRolloutTests::test_find_thread_name_by_id_prefers_latest_entry`.
- `find_thread_names_by_ids` latest entry and invalid/empty-row filtering -> `tests/test_core_rollout.py::CoreRolloutTests::test_find_thread_names_by_ids_prefers_latest_entry` and `tests/test_core_rollout.py::CoreRolloutTests::test_find_thread_names_by_ids_ignores_invalid_rows_and_empty_names`.
- `find_thread_meta_by_name_str` skips partial and historical rename entries -> `tests/test_core_rollout.py::CoreRolloutTests::test_find_thread_meta_by_name_skips_partial_or_historical_entries`.

Status: `complete_slice`; session index append-order lookup and invalid-row filtering are covered.

## policy.rs

- `EventPersistenceMode`, `should_persist_response_item`, `should_persist_response_item_for_memories`, `should_persist_event_msg`, `is_persisted_rollout_item`, and `persisted_rollout_items` -> `tests/test_core_rollout.py::CoreRolloutTests::test_policy_response_item_persistence_matches_rust`, `test_policy_memory_response_item_persistence_matches_rust`, `test_policy_event_persistence_modes_match_rust`, and `test_policy_persisted_rollout_items_sanitizes_extended_exec_output`.

Status: `complete_slice`; response item persistence, memories filtering, limited/extended event filtering, and extended exec output sanitization are covered.

## search.rs

- `search_rollout_paths` fallback filesystem scan over `sessions` and `archived_sessions`, JSON-escaped fixed-string case-insensitive matching, and missing-root empty result -> `tests/test_core_rollout.py::CoreRolloutTests::test_search_rollout_paths_scans_sessions_and_archived_roots`.
- `first_rollout_content_match_snippet` conversation-text extraction, user prefix stripping, whitespace normalization, and role/type filtering -> `tests/test_core_rollout.py::CoreRolloutTests::test_first_rollout_content_match_snippet_extracts_conversation_text`.

Status: `complete_slice`; rollout content path search and first content match snippet behavior are covered.

## sqlite_metrics.rs

- `recorder`, `OtelDbTelemetry::counter`, `OtelDbTelemetry::record_duration`, and `with_originator` originator tag forwarding/bounding -> `tests/test_core_rollout.py::CoreRolloutTests::test_sqlite_metrics_recorder_appends_bounded_originator_tag`.

Status: `complete_slice`; SQLite DB telemetry wrapper tag enrichment is covered by a Rust-derived semantic test.

## state_db.rs

- `cursor_to_anchor` millisecond UTC anchor conversion and `list_thread_ids_db` context-none/error fallback plus runtime argument mapping -> `tests/test_core_rollout.py::CoreRolloutTests::test_state_db_list_thread_ids_maps_cursor_filters_and_errors`.
- `list_threads_db` filter option mapping, cwd normalization, stale rollout path dropping, and delete-thread repair notification -> `tests/test_core_rollout.py::CoreRolloutTests::test_state_db_list_threads_maps_filters_and_drops_stale_paths`.
- `find_rollout_path_by_id`, `mark_thread_memory_mode_polluted`, and `touch_thread_updated_at` context-none/error fallback plus runtime forwarding -> `tests/test_core_rollout.py::CoreRolloutTests::test_state_db_small_adapters_forward_and_swallow_errors`.
- `read_repair_rollout_path` fast existing-row repair and slow rollout-metadata rebuild path -> `tests/test_core_rollout.py::CoreRolloutTests::test_state_db_read_repair_rollout_path_fast_path_updates_existing_metadata` and `test_state_db_read_repair_rollout_path_slow_path_rebuilds_missing_row`.
- `apply_rollout_items` builder fallback, default-provider fill, rollout-path/cwd normalization, runtime forwarding, and error fallback -> `tests/test_core_rollout.py::CoreRolloutTests::test_state_db_apply_rollout_items_normalizes_builder_and_falls_back_safely`.

Status: `complete_slice`; state DB adapter behavior is covered at the protocol-shaped runtime boundary.

## recorder.rs

- `recorder_tests.rs::load_rollout_items_skips_legacy_ghost_snapshot_lines` -> `tests/test_core_rollout.py::CoreRolloutTests::test_load_rollout_items_skips_legacy_ghost_snapshot_lines`.
- `recorder_tests.rs::load_rollout_items_preserves_legacy_guardian_assessment_lines` -> `tests/test_core_rollout.py::CoreRolloutTests::test_load_rollout_items_preserves_legacy_guardian_assessment_lines`.
- `recorder_tests.rs::load_rollout_items_filters_legacy_ghost_snapshots_from_compaction_history` -> `tests/test_core_rollout.py::CoreRolloutTests::test_load_rollout_items_filters_legacy_ghost_snapshots_from_compaction_history`.
- `recorder_tests.rs::recorder_materializes_on_flush_with_pending_items` -> `tests/test_core_rollout.py::CoreRolloutTests::test_recorder_materializes_on_flush_with_pending_items`.
- `recorder_tests.rs::persist_reports_filesystem_error_and_retries_buffered_items` -> `tests/test_core_rollout.py::CoreRolloutTests::test_persist_reports_filesystem_error_and_retries_buffered_items`.
- `recorder_tests.rs::writer_state_retries_write_error_before_reporting_flush_success` -> `tests/test_core_rollout.py::CoreRolloutTests::test_writer_state_retries_write_error_before_reporting_flush_success`.
- `recorder_tests.rs::list_threads_db_disabled_does_not_skip_paginated_items` -> `tests/test_core_rollout.py::CoreRolloutTests::test_get_threads_db_disabled_does_not_skip_paginated_items`.
- `recorder_tests.rs::list_threads_default_filter_returns_filesystem_scan_results` -> `tests/test_core_rollout.py::CoreRolloutTests::test_get_threads_default_filter_returns_filesystem_scan_results`.
- `recorder_tests.rs::list_threads_search_repairs_stale_state_db_hits_before_returning` -> `tests/test_core_rollout.py::CoreRolloutTests::test_get_threads_search_repairs_stale_state_db_hits_before_returning` plus positive session-index search coverage.
- `recorder_tests.rs::list_threads_state_db_only_skips_jsonl_repair_scan` -> `tests/test_core_rollout.py::CoreRolloutTests::test_list_threads_state_db_only_skips_jsonl_repair_scan`.
- `recorder_tests.rs::list_threads_db_enabled_drops_missing_rollout_paths` -> `tests/test_core_rollout.py::CoreRolloutTests::test_list_threads_db_enabled_drops_missing_rollout_paths`.
- `recorder_tests.rs::list_threads_db_enabled_repairs_stale_rollout_paths` -> `tests/test_core_rollout.py::CoreRolloutTests::test_list_threads_db_enabled_repairs_stale_rollout_paths`.
- `recorder_tests.rs::resume_candidate_matches_cwd_reads_latest_turn_context` -> `tests/test_core_rollout.py::CoreRolloutTests::test_get_threads_cwd_filter_reads_latest_turn_context`.
- `recorder_tests.rs::fill_missing_thread_item_metadata_preserves_identity_and_prefers_state_git_fields` -> `tests/test_core_rollout.py::CoreRolloutTests::test_fill_missing_thread_item_metadata_preserves_identity_and_prefers_state_git_fields`.
- `recorder_tests.rs::list_threads_metadata_filter_overlays_state_db_list_metadata` -> `tests/test_core_rollout.py::CoreRolloutTests::test_list_threads_metadata_filter_overlays_state_db_list_metadata`.

Status: `complete_slice`; state init backfill-before-return, legacy loader compatibility, flush materialization/idempotent persist, failed-persist buffered retry, writer-state write-error retry, default filesystem cwd filtering, session-index search filtering/stale-hit exclusion, state-db-only no-JSONL-scan listing, missing state rollout path drop, stale state rollout path repair, DB-disabled pagination, latest turn-context cwd filtering, and filesystem/state metadata merge and state-list metadata overlay behavior are covered.













