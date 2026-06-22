# codex-exec-server/src/server/handler.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/server/handler.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the handler state-machine slice that can be validated
without concrete process execution or HTTP transport:

- `ExecServerHandler.new` stores the session registry, notification sender, and
  runtime paths.
- `initialize` may only be sent once per connection.
- successful `initialize` attaches a session through `SessionRegistry` and
  returns `InitializeResponse { session_id }`.
- failed resume resets the initialize-requested flag, matching Rust retry
  behavior after attach failure.
- `initialized` before `initialize` returns the Rust protocol string error.
- `initialized` after an attached session marks the connection initialized.
- filesystem methods require `initialize` and then `initialized` before
  delegating to `FileSystemHandler`.
- active session resume is rejected through the same `SessionRegistry` error
  shape.
- `shutdown` detaches the current session and clears process notifications.

Concrete process execution, long-poll read behavior, HTTP request streaming,
background task cancellation, and real connection processing remain separate
contracts.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/server/handler.rs`
- Rust test: `src/server/handler/tests.rs::active_session_resume_is_rejected`
- Python tests: `tests/test_exec_server_handler_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_handler_rs.py
python -m pytest tests/test_exec_server_handler_rs.py -q --tb=short
python -m pytest tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py -q --tb=short
python -m pytest tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_process_handler_rs.py -q --tb=short
```

Latest result:

```text
2026-06-21 handler/session registry focused validation: 12 passed
2026-06-21 adjacent processor/registry/process-handler regression: 20 passed
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py, tests\test_exec_server_handler_rs.py, and tests\test_exec_server_session_registry_rs.py
```
