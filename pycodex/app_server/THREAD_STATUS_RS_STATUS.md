# src/thread_status.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/thread_status.rs`

Python mapping:

- `pycodex/app_server/thread_status.py`
- `tests/test_app_server_thread_status_rs.py`

Covered behavior:

- `ThreadWatchManager` construction with and without outgoing notification
  sender.
- Thread upsert, silent upsert, remove, loaded status lookup, and batch loaded
  status lookup.
- Turn start/completion/interruption/shutdown and system-error state updates.
- Pending permission and pending user-input guard counters with saturating
  release behavior.
- `loaded_thread_status(...)` active-flag ordering:
  `waitingOnApproval` before `waitingOnUserInput`.
- `running_turn_count()` based only on `runtime.running`.
- `resolve_thread_status(...)` upgrading `idle`/`notLoaded` to active when a
  live in-progress turn is known.
- Status changed notifications emitted only when status changes and skipped for
  silent initial upsert.
- Per-thread status subscriptions receive updates only for their own thread.

Deferred boundaries:

- Rust `tokio::sync::watch` receiver lifetime cleanup and receiver-count based
  pruning are represented by a small Python subscription object, not a full
  watch-channel implementation.
- Rust `Drop` spawns guard-release work on the current Tokio handle. Python uses
  explicit/async-context release to avoid hidden event-loop finalizer work.
- Concrete `OutgoingMessageSender` envelope/channel behavior remains owned by
  sibling outgoing-message/runtime modules; this module only requires a
  `send_server_notification(...)` method.

Validation:

- 2026-06-19: `python -m pytest tests/test_app_server_thread_status_rs.py -q`
  -> 12 passed.
- 2026-06-19: `python -m py_compile pycodex/app_server/thread_status.py tests/test_app_server_thread_status_rs.py`.
