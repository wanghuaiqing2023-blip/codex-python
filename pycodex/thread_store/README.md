# pycodex.thread_store

Rust crate: `codex-thread-store`
Rust path: `codex/codex-rs/thread-store`

This package carries dependency-light Python projections for thread-store public
types and selected store implementations.

## Module Coverage

| Rust module | Python surface | Status | Notes |
|---|---|---|---|
| `src/in_memory.rs` | `pycodex.thread_store.InMemoryThreadStore` | complete_slice | Shared store registry, call counters, create/resume/append/history/read/list/update/archive/unarchive behavior, Rust default unsupported pagination errors, rollout-path lookup, string-sorted listing, and Rust default `StoredThread` fields are covered by Rust-derived tests. |
| `src/types.rs` | `pycodex.thread_store` | complete_slice | Public dataclass/enum projections exist; `ThreadMetadataPatch` and `GitInfoPatch` now cover Rust optional-clear serde shape, missing-field no-op decoding, and merge-by-field-presence semantics with Rust-derived tests. Broader type inventory remains tracked by crate-level follow-up only where it depends on unported local/live store behavior. |
| `src/thread_metadata_sync.rs` | `pycodex.thread_store.ThreadMetadataSync` | complete_slice | Resume-history metadata derivation, pending-update retry/generation semantics, append barriers, user-message/goal preview rules, and updated-at touch coalescing are covered by direct Rust-derived tests. |
| `src/live_thread.rs` | `pycodex.thread_store.LiveThread` | complete_slice | Create/resume lifecycle, history loading before metadata observation, canonical rollout persistence filtering, append-derived metadata application, pending metadata flushing before explicit updates, and basic guard discard behavior are covered by Rust-derived tests. |
| `src/local/create_thread.rs` and `src/local/live_writer.rs` | `pycodex.thread_store.LocalThreadStore` | complete_slice | Local live-writer creation requires cwd, rejects duplicate live writers, exposes live rollout paths, writes canonical JSONL through `RolloutRecorder`, supports persist/flush/shutdown/discard, and removes writers on close/discard with Rust-derived tests. |
| `src/local/read_thread.rs` | `pycodex.thread_store.LocalThreadStore.read_thread` | complete_slice | Active and archived rollout lookup by thread id, active-over-archived precedence, relative/canonical rollout-path reads, session-meta fallback without user preview, fork metadata overlay, legacy thread-name index lookup, SQLite metadata projection, SQLite git-info overlay for rollout-path reads, stale/mismatched SQLite rollout-path fallback, SQLite summary fallback, archived SQLite filtering/history loading, history loading, and missing-rollout invalid-request behavior are covered by Rust-derived tests. |
| `src/local/list_threads.rs` | `pycodex.thread_store.LocalThreadStore.list_threads` | complete_slice | Active versus archived rollout collection selection, invalid cursor rejection, default-provider fallback, local rollout summary projection, source/provider filters, state-db-only title search preservation, and SQLite/legacy thread-name overlay are covered by Rust-derived tests. |
| `src/local/search_threads.rs` | `pycodex.thread_store.LocalThreadStore.search_threads` | complete_slice | Empty search and invalid cursor errors, rollout content path search, list-order scanning, snippet extraction, search pagination cursor generation, source filters, no-match empty pages, and SQLite/legacy thread-name overlay are covered by Rust-derived tests. |
| `src/local/archive_thread.rs` | `pycodex.thread_store.LocalThreadStore.archive_thread` | complete_slice | Active rollout lookup, scoped sessions-path validation, thread-id filename matching, move to `archived_sessions`, archived listing visibility, and optional state-db `mark_archived` updates are covered by Rust-derived tests. |
| `src/local/unarchive_thread.rs` | `pycodex.thread_store.LocalThreadStore.unarchive_thread` | complete_slice | Archived rollout lookup, scoped archived-path validation, thread-id filename matching, dated sessions restore, mtime touch, active `StoredThread` return, and optional state-db `mark_unarchived` updates are covered by Rust-derived tests. |
| `src/local/update_thread_metadata.rs` | `pycodex.thread_store.LocalThreadStore.update_thread_metadata` | complete_slice | Explicit name, memory-mode, and git-info rollout compatibility updates are covered; observed title/preview/first-user-message/cwd/provider/model/reasoning/source/thread-source/agent/policy/token metadata updates write state metadata while returned summaries still come from rollout content; normalized cwd values match state-db-only list filters; archived rollout updates recreate/preserve archived state rows, including resumed live archived threads; partial git updates rebuild missing state rows; SQLite write failures are best-effort for legacy/observed updates and blocking for git-only updates. |
| `src/store.rs` | `pycodex.thread_store.ThreadStore` | complete_slice | Protocol-style surface exposes the Rust `ThreadStore` operation set, including rollout-path reads, list/search, turn/item pagination, metadata update, archive, and unarchive methods. |
| `src/error.rs` | `pycodex.thread_store.ThreadStoreError` | complete_slice | Rust enum variants, field names, and display-message shapes are covered by Rust-derived tests. |
| `src/local/*` | `pycodex.thread_store.LocalThreadStore` | complete_slice | Local live-writer creation/lifecycle plus rollout/state-db read/list/search/archive/unarchive/update behavior are covered by module-scoped Rust-derived tests. |

## Known Gaps

- Exact Tokio locking/runtime identity is outside this dependency-light slice; this is a non-blocking implementation difference for the Python port because the crate's storage contracts are covered at the public/module boundary.

With `src/store.rs`, `src/error.rs`, and the local store modules covered by
Rust-derived tests, `codex-thread-store` is tracked as `complete`.

## Tests

- `tests/test_thread_store_in_memory_rs.py`
- `tests/test_thread_store_store_error_rs.py`
- `tests/test_thread_store_types_rs.py`
- `tests/test_thread_store_metadata_sync_rs.py`
- `tests/test_thread_store_live_thread_rs.py`
- `tests/test_thread_store_local_live_writer_rs.py`
- `tests/test_thread_store_local_read_thread_rs.py`
- `tests/test_thread_store_local_list_threads_rs.py`
- `tests/test_thread_store_local_search_threads_rs.py`
- `tests/test_thread_store_local_archive_unarchive_rs.py`
- `tests/test_thread_store_local_update_metadata_rs.py`
- `tests/test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract`
