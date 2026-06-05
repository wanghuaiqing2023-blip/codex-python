# Terminal Error Completion Parity

## Graph slice

- `codex-rs/core/src/session/turn.rs#run_turn:133`
- `codex-rs/core/src/tasks/lifecycle.rs#emit_turn_error_lifecycle:58`
- `codex-rs/protocol/src/error.rs#to_codex_protocol_error:220`
- `codex-rs/protocol/src/protocol.rs#TurnCompleteEvent:1853`

The upstream graph keeps terminal turn errors on the same core session turn path as regular sampling, stop hooks, and task lifecycle events.

## Rust behavior confirmed

- `run_turn` handles ordinary `CodexErr` sampling failures by converting them to protocol error info, emitting turn error lifecycle, sending an `Error` event, and breaking the turn loop so the user can continue the conversation.
- `ContextWindowExceeded` also marks the token window full before emitting the error event.
- `UsageLimitReached` records usage limit side effects before emitting the error event.
- `InvalidRequest` maps to protocol `CodexErrorInfo::Other` in the generic terminal error path.
- The task wrapper emits `TurnComplete(None)` after a completed turn with no final agent message.

## Python changes

- `pycodex/core/turn_runtime.py`
  - Terminal sampler `CodexErr` no longer escapes from the high-level user turn runner after the error event has been emitted.
  - Initial and follow-up sampling terminal failures now return a completed `UserTurnSamplingResult` with `last_agent_message=None`.
  - Existing context-window and usage-limit side effects remain in `_handle_terminal_sampling_error`.
- `tests/test_core_turn_runtime.py`
  - Updated terminal context-window and usage-limit tests to assert completed turn results plus `task_complete(None)`.
- `tests/test_core_session_runtime.py`
  - Updated in-memory session lifecycle assertions to cover completed terminal-error turns.
- `tests/test_exec_local_runtime.py`
  - Updated local HTTP exec tests to consume terminal errors from `session_events` on the completed result rather than from an escaping exception.

## Validation

- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_marks_context_window_full_on_terminal_error tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_records_usage_limit_rate_limits_on_terminal_error tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_terminal_error_lifecycle tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_records_usage_limit_error_lifecycle`
- `python -m unittest tests.test_core_turn_runtime tests.test_core_session_runtime tests.test_core_http_transport tests.test_exec_local_runtime`
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`

## Deferred

- Auto-compact terminal errors already share similar error lifecycle logic upstream, but the broader Python auto-compact path still needs a separate graph-guided slice.
- Goal-runtime `UsageLimitReached` side effects are still represented by existing Python rate-limit/session side effects rather than a full goal runtime port.
