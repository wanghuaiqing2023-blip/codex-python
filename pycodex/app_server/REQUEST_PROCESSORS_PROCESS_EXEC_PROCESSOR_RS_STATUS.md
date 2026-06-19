# request_processors/process_exec_processor.rs Status

Rust module: `codex-app-server/src/request_processors/process_exec_processor.rs`

Python module: `pycodex/app_server/request_processors_process_exec_processor.py`

Status: `complete`

## Covered Contract

- Processor construction preserves Rust's injected outgoing sender,
  environment manager, and process exec manager boundary.
- `process_spawn` requires a local environment, validates empty command,
  empty `processHandle`, and `size` without `tty: true`, projects environment
  overrides, timeout double-option semantics, output cap defaults, and terminal
  size conversion before delegating to the manager.
- `ProcessExecManager.start` preserves connection/process-handle keying,
  duplicate active process-handle rejection, tty-implied stdin/stdout streaming,
  spawn failure cleanup, and spawn response sending through an injected
  outgoing sender.
- `process_write_stdin`, `process_resize_pty`, `process_kill`, and
  `connection_closed` preserve Rust control routing, base64 validation,
  missing-session errors, stdin-streaming checks, resize validation, and
  close-triggered kill controls.
- Helper functions preserve Rust error text for no-active/no-longer-running
  process handles, terminal-size validation, timeout exit code, output chunk
  size hint, output capture, output cap, and streamed delta-base64 projection.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/process_exec_processor.rs`
- Python parity tests staged in
  `tests/test_app_server_request_processors_process_exec_processor_rs.py`.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_process_exec_processor_rs.py -q`
  -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_process_exec_processor.py tests/test_app_server_request_processors_process_exec_processor_rs.py`.

## Known Gaps

- Real PTY/pipe process spawning, Tokio task scheduling, expiration waiting,
  stdout/stderr drain timing, and process-exit notification delivery remain
  injected runtime responsibilities.
