# codex-debug-client src/client.rs Status

Rust source:

- `codex/codex-rs/debug-client/src/client.rs`

Python mapping:

- `pycodex/debug_client/client.py`

Status: `complete_candidate`

Implemented behavior:

- `AppServerClient` process facade with injectable child/stdin/stdout streams.
- `spawn(...)` command construction for `codex app-server` with repeated
  `--config` overrides.
- `initialize(...)`, including initialize request, response wait, and
  initialized notification.
- Synchronous `start_thread(...)` and `resume_thread(...)` response handling.
- Asynchronous request helpers for thread start/resume/list with pending
  request tracking.
- `send_turn(...)` plain text `turn/start` request construction.
- Reader startup ownership of stdout, active thread state, known-thread memory,
  shutdown, compact JSON writes, and response-loop handling.
- Client-local approval request handling that declines command execution and
  file change approvals while waiting for a direct response.
- `build_thread_start_params(...)` and `build_thread_resume_params(...)`.

Validation:

- `python -m py_compile pycodex/debug_client/__init__.py pycodex/debug_client/client.py pycodex/debug_client/commands.py pycodex/debug_client/output.py pycodex/debug_client/state.py pycodex/debug_client/reader.py tests/test_debug_client_commands_rs.py tests/test_debug_client_output_rs.py tests/test_debug_client_state_rs.py tests/test_debug_client_reader_rs.py tests/test_debug_client_client_rs.py`
  passed on 2026-06-19.
- Focused pytest is deferred until remaining `codex-debug-client` modules are
  complete.
