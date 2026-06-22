# codex-exec-server/src/server/process_handler.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/server/process_handler.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the module-local wrapper behavior:

- `ProcessHandler.new(notifications)` constructs a handler around a
  `LocalProcess` boundary initialized with the notification sender.
- `shutdown` delegates to the wrapped process.
- `set_notification_sender` delegates notification replacement.
- `exec`, `exec_read`, and `exec_write` delegate params unchanged.
- `terminate` delegates to the wrapped process' `terminate_process`, matching
  the Rust `LocalProcess::terminate_process` call.

The concrete `LocalProcess` runtime remains a separate, unported module
contract. The Python `LocalProcess` here is an explicit runtime boundary stub
used to preserve wrapper shape and support tests with injected fakes.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/server/process_handler.rs`
- Adjacent Rust target: `codex/codex-rs/exec-server/src/local_process.rs`
- Python tests: `tests/test_exec_server_process_handler_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_handler_rs.py
python -m pytest tests/test_exec_server_process_handler_rs.py -q --tb=short
python -m pytest tests/test_exec_server_process_handler_rs.py tests/test_exec_server_processor_rs.py -q --tb=short
python -m pytest tests/test_exec_server_process_handler_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_server_registry_rs.py -q --tb=short
```

Latest result:

```text
2026-06-21 process-handler/processor focused validation: 4 passed
2026-06-21 adjacent handler/session/registry regression: 20 passed
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py, tests\test_exec_server_process_handler_rs.py, and tests\test_exec_server_processor_rs.py
```
