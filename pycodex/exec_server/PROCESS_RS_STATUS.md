# codex-exec-server/src/process.rs Status

Rust crate: `codex-exec-server`

Rust module: `codex/codex-rs/exec-server/src/process.rs`

Python module: `pycodex.exec_server`

Status: `complete`

## Behavior Contract

The Python port mirrors the independently testable `process.rs` contract:

- `StartedExecProcess` carries the executor-managed process handle.
- `ExecProcessEvent` exposes `Output`, `Exited`, `Closed`, and `Failed`
  variants through constructors, `seq()`, and `retained_len()`.
- `ExecProcessEventLog` keeps a bounded replay history by event count and
  retained bytes, and fans out published events to subscribers.
- `ExecProcessEventReceiver` drains replayed events before awaiting live
  events.
- `ExecProcess` and `ExecBackend` expose the runtime trait boundary while
  concrete process execution remains unported.

Concrete process startup, retained-output reads, stdin writes, termination, and
runtime wake channels require separate module work in the process/backend/server
implementation path.

## Evidence

- Rust source: `codex/codex-rs/exec-server/src/process.rs`
- Rust test: `event_history_replay_is_bounded_by_retained_bytes`
- Python tests: `tests/test_exec_server_process_rs.py`

Focused validation:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_rs.py
python -m pytest tests/test_exec_server_process_rs.py -q --tb=short
```

Latest result:

```text
7 passed
```

Completion validation on 2026-06-21:

```text
python -m py_compile pycodex\exec_server\__init__.py tests\test_exec_server_process_rs.py
python -m pytest tests/test_exec_server_process_rs.py -q --tb=short
7 passed
python -m pytest tests/test_exec_server_process_rs.py tests/test_exec_server_local_process_rs.py tests/test_exec_server_remote_process_rs.py tests/test_exec_server_process_handler_rs.py tests/test_exec_server_client_rs.py -q --tb=short
37 passed
```
