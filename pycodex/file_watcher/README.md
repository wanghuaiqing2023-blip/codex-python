# pycodex.file_watcher

Rust crate: `codex-file-watcher`
Rust path: `codex/codex-rs/file-watcher`

This package carries a dependency-light Python projection of the Rust file
watcher subscription and synthetic notification contracts.

## Module Coverage

| Rust module | Python surface | Status | Notes |
|---|---|---|---|
| `src/lib.rs` | `pycodex.file_watcher` | complete | `FileWatcherEvent`, `WatchPath`, receiver coalescing/closure, throttled receiving, `FileWatcher::noop`, subscriber registration, path/scope dedupe, path ref-counting, live-mode watched-mode projection, explicit close/drop projection, matching notification routing, non-recursive filtering, ancestor-event mapping, missing-path create/delete fallback, fallback move-to-created-target behavior, event-loop mutating-event filtering, mutating-event filtering, and unregister state-lock ordering are covered by Rust-derived tests. |

## Known Gaps

- `FileWatcher.new()` projects live watch mode reconfiguration and inner
  watcher release, but it does not create a native `notify::RecommendedWatcher`
  backend.
- Exact Tokio task scheduling, cancellation, and native OS watcher lifecycle
  remain runtime boundaries. The Rust lock-order contract around live
  `unwatch` is covered by a dependency-light state-lock projection.
- Tests use explicit `close()` for Rust Drop/RAII semantics because Python
  garbage collection timing is not deterministic.

All Rust `src/lib.rs` tests now have Rust-derived Python parity coverage. Native
OS watcher integration remains an operational boundary for the dependency-light
port, so this crate is `complete`.

## Tests

- `tests/test_file_watcher_lib_rs.py`
