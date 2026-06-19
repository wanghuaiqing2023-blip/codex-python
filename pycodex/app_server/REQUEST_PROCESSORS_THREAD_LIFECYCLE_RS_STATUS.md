# src/request_processors/thread_lifecycle.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_lifecycle.rs`

Python mapping:

- `pycodex/app_server/request_processors_thread_lifecycle.py`
- `tests/test_app_server_request_processors_thread_lifecycle_rs.py`

Behavior covered:

- `THREAD_UNLOADING_DELAY`, listener task context shape, unload state timing,
  listener attach result values, and thread shutdown result values are mirrored.
- `ensure_conversation_listener(...)` projects missing-thread invalid-request
  errors, pending-unload rejection, closed-connection return, connection
  subscription, raw-event opt-in, listener setup, and listener setup rollback
  on failure.
- `ensure_listener_task_running(...)` mirrors the local listener replacement
  gate, closing-thread invalid-request branch, skills watcher registration
  call-site, config snapshot baseline capture, and thread-state listener
  sender installation while leaving the Tokio select loop as an injected
  runtime boundary.
- `wait_for_thread_shutdown(...)`, `unload_thread_without_subscribers(...)`,
  and listener-command dispatch mirror shutdown result classification,
  request cancellation, thread-state removal, thread-manager/watch-manager
  cleanup, `ThreadClosed`, goal update/clear/snapshot, and
  `ServerRequestResolved` notifications.
- Resume helpers cover running-thread resume response composition boundaries,
  history/active-turn merge, stale in-progress turn interruption when the
  thread is no longer active, goal snapshot ordering hooks, request replay,
  and active-goal continuation call-sites.

Intentional boundaries:

- The concrete Tokio listener task, event stream select loop, bespoke core
  event handling, token-usage replay, rollout IO, exact sandbox/permission
  projection, and live thread execution remain neighboring runtime or
  dependency boundaries.
- This module is complete for its module-scoped behavior contract; concrete
  sibling-owned runtime effects remain boundaries until broader crate-level
  validation/integration.

Validation status:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_lifecycle_rs.py -q`
  -> 7 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_lifecycle.py tests/test_app_server_request_processors_thread_lifecycle_rs.py`.
