# pycodex.file_watcher Test Alignment

Rust crate: `codex-file-watcher`
Rust path: `codex/codex-rs/file-watcher`

## Status

`complete`

The dependency-light contracts in `src/lib.rs` are implemented for synthetic
event delivery, subscription matching, live-mode watched-mode projection, and
event-loop filtering. The Rust live unwatch lock-order contract is projected
with standard-library locks. Native `notify` backend integration, exact Tokio
task scheduling, and live watch/unwatch task cancellation remain operational
runtime boundaries for the Python port.

## Rust-Derived Tests

| Rust module | Rust tests/contracts | Python tests | Status |
|---|---|---|---|
| `src/lib.rs` | `throttled_receiver_coalesces_within_interval` | `tests/test_file_watcher_lib_rs.py::test_throttled_receiver_coalesces_within_interval` | complete |
| `src/lib.rs` | `throttled_receiver_flushes_pending_on_shutdown` | `tests/test_file_watcher_lib_rs.py::test_throttled_receiver_flushes_pending_on_shutdown` | complete |
| `src/lib.rs` | `is_mutating_event_filters_non_mutating_event_kinds` | `tests/test_file_watcher_lib_rs.py::test_is_mutating_event_filters_non_mutating_event_kinds` | complete |
| `src/lib.rs` | `register_dedupes_by_path_and_scope` | `tests/test_file_watcher_lib_rs.py::test_register_dedupes_by_path_and_scope` | complete |
| `src/lib.rs` | `watch_registration_drop_unregisters_paths`, `subscriber_drop_unregisters_paths` | `tests/test_file_watcher_lib_rs.py::test_watch_registration_and_subscriber_close_unregister_paths` | complete |
| `src/lib.rs` | `missing_path_registers_nearest_existing_parent`, `deeply_missing_path_registers_nearest_existing_directory_ancestor` | `tests/test_file_watcher_lib_rs.py::test_missing_paths_register_nearest_existing_directory_ancestor` | complete |
| `src/lib.rs` | `receiver_closes_when_subscriber_drops` | `tests/test_file_watcher_lib_rs.py::test_receiver_closes_when_subscriber_closes` | complete |
| `src/lib.rs` | `recursive_registration_downgrades_to_non_recursive_after_drop` | `tests/test_file_watcher_lib_rs.py::test_recursive_registration_downgrades_to_non_recursive_after_drop` | complete_slice |
| `src/lib.rs` | `matching_subscribers_are_notified` | `tests/test_file_watcher_lib_rs.py::test_matching_subscribers_are_notified` | complete |
| `src/lib.rs` | `ancestor_events_notify_child_watches` | `tests/test_file_watcher_lib_rs.py::test_ancestor_events_notify_child_watches` | complete |
| `src/lib.rs` | `non_recursive_watch_ignores_grandchildren` | `tests/test_file_watcher_lib_rs.py::test_non_recursive_watch_ignores_grandchildren` | complete |
| `src/lib.rs` | `missing_file_watch_reports_requested_path_when_parent_changes` | `tests/test_file_watcher_lib_rs.py::test_missing_file_watch_reports_requested_path_when_parent_changes` | complete |
| `src/lib.rs` | `missing_file_watch_reports_requested_path_when_parent_delete_event_arrives` | `tests/test_file_watcher_lib_rs.py::test_missing_file_watch_reports_requested_path_when_parent_delete_event_arrives` | complete |
| `src/lib.rs` | `missing_directory_watch_moves_to_created_directory_for_child_events` | `tests/test_file_watcher_lib_rs.py::test_missing_directory_watch_moves_to_created_directory_for_child_events` | complete |
| `src/lib.rs` | `spawn_event_loop_filters_non_mutating_events` | `tests/test_file_watcher_lib_rs.py::test_spawn_event_loop_filters_non_mutating_events` | complete_slice |
| `src/lib.rs` | `dropping_live_watcher_releases_inner_watcher` | `tests/test_file_watcher_lib_rs.py::test_dropping_live_watcher_releases_inner_watcher` | complete_slice |
| `src/lib.rs` | `unregister_holds_state_lock_until_unwatch_finishes` | `tests/test_file_watcher_lib_rs.py::test_unregister_holds_state_lock_until_unwatch_finishes` | complete |

## Validation

2026-06-22:

- `python -m pytest tests\test_file_watcher_lib_rs.py -q --tb=short`
  - `16 passed`
- `python -m py_compile pycodex\file_watcher\__init__.py tests\test_file_watcher_lib_rs.py`
  - passed

2026-06-22:

- `python -m pytest tests\test_file_watcher_lib_rs.py -q --tb=short`
  - `17 passed`
- `python -m py_compile pycodex\file_watcher\__init__.py tests\test_file_watcher_lib_rs.py`
  - passed
