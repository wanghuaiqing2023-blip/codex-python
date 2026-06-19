# `src/command_exec.rs` Alignment Status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/command_exec.rs`

Python mapping:

- `pycodex/app_server/command_exec.py`
- `tests/test_app_server_command_exec_rs.py`

Mapped behavior contract:

- `EXEC_TIMEOUT_EXIT_CODE`, `OUTPUT_CHUNK_SIZE_HINT`, and default output cap
  constants used by the module-local command/exec control path.
- `InternalProcessId` generated/client identity, JSON-string error rendering
  for client ids, and numeric rendering for generated ids.
- `CommandExecManager` session table projection: generated id allocation,
  duplicate active process id rejection, connection-scoped session lookup, and
  connection-close removal with terminate control recording.
- `start(...)` control-plane validation for streaming requiring client
  `processId`, empty command rejection, Windows restricted-token sandbox
  streaming rejection, custom output cap rejection, unsupported Windows sandbox
  session registration, and active non-Windows session registration.
- `write(...)` validation for actionable writes, base64 decoding, stdin
  streaming guard, and decoded write control recording.
- `terminate(...)`, `resize(...)`, unsupported Windows-sandbox control errors,
  missing/not-running process errors, and `terminal_size_from_protocol(...)`
  rows/cols validation.

Deferred dependency/runtime boundaries:

- Real PTY/pipe process spawning, sandbox execution, network proxy lifetime
  ownership, async Tokio channel semantics, process output streaming,
  output-byte cap truncation during reads, `bytes_to_string_smart(...)`, expiry
  select-loop behavior, IO drain timeout timing, and response/notification
  delivery through concrete outgoing transports.
- Platform-specific non-Windows execution tests that require spawning real
  shell processes are represented only by the control-plane projection here.

Validation:

- `python -m pytest tests/test_app_server_command_exec_rs.py -q` passed on
  2026-06-19 with 13 tests.
- `python -m py_compile pycodex/app_server/command_exec.py
  tests/test_app_server_command_exec_rs.py` passed on 2026-06-19.
