# codex-app-server/src/fs_watch.rs status

Rust source:

- `codex/codex-rs/app-server/src/fs_watch.rs`

Python target:

- `pycodex/app_server/fs_watch.py`

Status: `complete`

## Covered contract

- `FS_CHANGED_NOTIFICATION_DEBOUNCE` is represented as
  `FS_CHANGED_NOTIFICATION_DEBOUNCE_MS = 200`.
- `FsWatchManager.watch(...)` keys watches by `(connection_id, watch_id)`.
- New watches register a non-recursive watch path and return
  `FsWatchResponse { path }`.
- Duplicate watch IDs are rejected only within the same connection scope with
  `invalid_request("watchId already exists: ...")`.
- The same watch ID may be used by different connections.
- `unwatch(...)` removes only the creating connection's watch entry and returns
  `FsUnwatchResponse`.
- `connection_closed(...)` removes only entries owned by that connection.
- Changed-file notification projection joins watcher-relative paths to the
  watch root, sorts by path, emits `ServerNotification::FsChanged` only for
  non-empty changes, and preserves the typed `FsChangedNotification` payload.
- Debounce projection accumulates unique changed paths into a single drained
  event.

## Deferred boundaries

- Concrete `codex-file-watcher` construction, fallback-to-noop internals,
  subscriber registration handles, watch registration lifetimes, and receiver
  delivery remain dependency boundaries.
- Tokio task spawning, biased select cancellation, exact debounce timing, and
  oneshot termination wait ordering remain runtime boundaries.
- Concrete `OutgoingMessageSender::send_server_notification_to_connection_and_wait`
  I/O remains a transport/runtime boundary.

## Python parity tests

- `tests/test_app_server_fs_watch_rs.py`

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_fs_watch_rs.py -q`
  -> 8 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/fs_watch.py tests/test_app_server_fs_watch_rs.py`.
