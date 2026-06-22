# codex-exec-server/src/server/session_registry.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/server/session_registry.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the session registry state-machine behavior:

- `ConnectionId`
- `AttachmentState`
- `SessionEntry`
- `SessionRegistry`
- `SessionHandle`
- `DETACHED_SESSION_TTL`
- a lightweight `ProcessHandler` session facade for notification sender and
  shutdown behavior needed by this module

Covered behavior includes new session attachment, resume by session id, unknown
session errors, rejection of duplicate active attachments, detach state changes,
notification sender clearing/restoring, expired detached session shutdown and
removal, and detached TTL expiry by matching connection id.

Concrete request handling in `server/handler.rs` and real process execution in
`server/process_handler.rs` / `local_process.rs` remain separate module work.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/server/session_registry.rs`
- Adjacent Rust use sites: `codex/codex-rs/exec-server/src/server/handler.rs`
  and `src/server/handler/tests.rs`
- Python tests: `tests/test_exec_server_session_registry_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_session_registry_rs.py
python -m pytest tests/test_exec_server_session_registry_rs.py -q --tb=short
python -m pytest tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py -q --tb=short
python -m pytest tests/test_exec_server_handler_rs.py tests/test_exec_server_session_registry_rs.py tests/test_exec_server_processor_rs.py tests/test_exec_server_server_registry_rs.py tests/test_exec_server_process_handler_rs.py -q --tb=short
```

Latest result:

```text
2026-06-21 handler/session registry focused validation: 12 passed
2026-06-21 adjacent processor/registry/process-handler regression: 20 passed
2026-06-21 py_compile passed for pycodex\exec_server\__init__.py, tests\test_exec_server_handler_rs.py, and tests\test_exec_server_session_registry_rs.py
```
