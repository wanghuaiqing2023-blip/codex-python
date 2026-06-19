# `src/thread_state.rs` Alignment Status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/thread_state.rs`

Python mapping:

- `pycodex/app_server/thread_state.py`
- `tests/test_app_server_thread_state_rs.py`

Mapped behavior contract:

- `PendingThreadResumeRequest`, `ThreadListenerCommand`, `TurnSummary`,
  `ThreadState`, `ConnectionCapabilities`, `ThreadEntry`, and
  `ThreadStateManager` local state shapes.
- Listener replacement, previous cancellation notification, listener generation
  increment/wrapping, listener command sender installation, listener matching,
  listener clearing, experimental raw event toggling, and listener command
  lookup.
- Active turn snapshot delegation to `ThreadHistoryBuilder`,
  `track_current_turn_event(...)` started-at tracking, terminal-turn id storage,
  and current-turn history reset after terminal events.
- `note_thread_settings(...)` change detection, matching the Rust local test.
- Ordered `ResolveServerRequest` command enqueueing through the listener
  command channel.
- Thread/connection subscription bookkeeping, reverse connection index cleanup,
  has-connections watcher updates, connection removal empty-thread reporting,
  subscriber lookup, and attestation-capable connection selection by lowest
  connection id.

Deferred dependency/runtime boundaries:

- Real Tokio `Mutex`, `mpsc`, `oneshot`, and `watch` channel scheduling.
- Concrete `CodexThread` weak-pointer lifetime behavior beyond identity
  matching, `WatchRegistration` behavior, listener task execution, state DB
  goal snapshot delivery, and request processor/listener integration.

Validation:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_thread_state_rs.py -q` -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/thread_state.py tests/test_app_server_thread_state_rs.py`.
