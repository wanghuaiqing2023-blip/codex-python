# codex-thread-store src/thread_metadata_sync.rs

Rust crate: `codex-thread-store`
Rust module: `src/thread_metadata_sync.rs`
Python package: `pycodex.thread_store`

## Status

`complete_slice`

## Rust Anchors

- `ThreadMetadataSync`
- `PendingThreadMetadataPatch`
- `ThreadMetadataSync::for_create`
- `ThreadMetadataSync::for_resume`
- `take_pending_update`
- `take_pending_update_for_existing_history`
- `mark_pending_update_applied`
- `observe_appended_items`
- `parse_memory_mode`
- `parse_session_timestamp`
- `strip_user_message_prefix`
- `user_message_preview`
- `thread_updated_at_touch`
- `update_has_metadata_facts`

## Covered Contract

- Resume history is scanned once to derive pending metadata without producing
  an `updated_at` touch.
- `take_pending_update` clones retry state and does not clear the pending
  update.
- `mark_pending_update_applied` clears only the matching generation and records
  an updated-at touch timestamp when applicable.
- Resume-derived metadata waits for the first append barrier before flushing
  through `take_pending_update_for_existing_history`.
- User-message previews, first-user-message, titles, and goal-derived previews
  follow the Rust seen-flag ordering.
- Metadata-irrelevant appends produce updated-at touches, and repeated touches
  inside the Rust test coalescing interval return `None` while leaving a
  barrier update pending.

## Python Tests

- `tests/test_thread_store_metadata_sync_rs.py::test_resume_history_keeps_derived_metadata_pending_until_applied`
- `tests/test_thread_store_metadata_sync_rs.py::test_goal_update_sets_preview_without_overriding_existing_preview`
- `tests/test_thread_store_metadata_sync_rs.py::test_later_user_messages_do_not_emit_existing_preview_fields`
- `tests/test_thread_store_metadata_sync_rs.py::test_metadata_irrelevant_items_coalesce_updated_at_touches`
- `tests/test_thread_store_metadata_sync_rs.py::test_resume_history_waits_for_append_before_flushing_metadata`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_metadata_sync_rs.py -q --tb=short`
  - `5 passed`
- `python -m pytest tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `14 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_metadata_sync_rs.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `15 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_metadata_sync_rs.py`
  - passed

## Remaining Outside This Slice

- `for_create` uses the dependency-light Python projection for startup
  metadata and does not perform Rust's async `codex_git_utils::collect_git_info`
  filesystem probe unless git metadata is already present in observed rollout
  items.
- `src/local/*` still owns the rollout/state-db backed persistence integration
  around this helper.
- Exact Tokio timing/runtime identity remains outside the dependency-light
  Python slice.
