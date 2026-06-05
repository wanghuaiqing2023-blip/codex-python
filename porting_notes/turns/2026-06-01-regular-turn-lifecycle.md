## 2026-06-01 Regular Turn Lifecycle Events

### Scope

- Added regular-turn lifecycle event emission to the Python core turn runtime.
- Session-like runtimes now receive `task_started` before sampling begins and `task_complete` after a completed turn result is finalized.
- The Python runtime also mirrors Rust's regular-turn reset of `server_reasoning_included` at turn start when the session object exposes that setter.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/tasks/regular.rs#run:37`
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/tasks/mod.rs#on_task_finished:570`
- Rust source confirmed:
  - Regular turns emit `TurnStarted` inline before `run_turn`.
  - Regular turns call `set_server_reasoning_included(false)` before sampling.
  - The task wrapper flushes rollout and emits `TurnComplete` with the final `last_agent_message` after `run_turn` returns, but does not emit completion when the task cancellation token is cancelled.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Emits `task_started` after the turn request is prepared and before sampler execution.
  - Emits `task_complete` only on completed result paths, after optional `flush_rollout()`.
  - Keeps interrupted result paths as started-without-complete, matching the Rust cancellation boundary.
  - Preserves `session_events` snapshots after lifecycle emission so callers see the terminal event.
- `tests/test_core_turn_runtime.py`
  - Added focused lifecycle coverage for started/completed payloads, `last_agent_message`, and `server_reasoning_included` reset.
  - Updated stream/tool event assertions to filter lifecycle envelopes when those tests are checking non-lifecycle stream behavior.
- `tests/test_core_session_runtime.py`, `tests/test_core_http_transport.py`, `tests/test_exec_local_runtime.py`
  - Updated integration assertions to account for lifecycle events while preserving their existing metadata, token-count, and retry checks.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py tests\test_core_turn_runtime.py tests\test_core_session_runtime.py tests\test_core_http_transport.py tests\test_exec_local_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 53 tests passed.
- `python -m unittest tests.test_core_session_runtime`
  - 73 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`
  - 609 tests passed, 1 skipped.
