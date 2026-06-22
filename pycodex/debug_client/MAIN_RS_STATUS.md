# codex-debug-client src/main.rs Status

Rust source:

- `codex/codex-rs/debug-client/src/main.rs`

Python mapping:

- `pycodex/debug_client/main.py`
- `pycodex/debug_client/__main__.py`

Status: `complete_candidate`

Implemented behavior:

- CLI argument parsing for codex binary, repeated config overrides, optional
  thread id, approval policy, auto-approve, final-only, output file, model,
  model provider, and cwd.
- Approval policy parsing with Rust aliases and error message.
- Main startup flow: output construction, app-server client spawn,
  initialize, start/resume thread, connected message, prompt state, reader
  startup, help output, stdin loop, and shutdown.
- Interactive command dispatch for help, quit, new thread, resume, use, and
  refresh-thread.
- Message dispatch to the active thread and no-active-thread reporting.
- Reader event draining for thread-ready and thread-list events.
- Help text output.

Validation:

- `python -m pytest tests/test_debug_client_commands_rs.py tests/test_debug_client_output_rs.py tests/test_debug_client_state_rs.py tests/test_debug_client_reader_rs.py tests/test_debug_client_client_rs.py tests/test_debug_client_main_rs.py -q`
  passed on 2026-06-19 with `61 passed`.
- `python -m py_compile pycodex/debug_client/__init__.py pycodex/debug_client/__main__.py pycodex/debug_client/main.py pycodex/debug_client/client.py pycodex/debug_client/commands.py pycodex/debug_client/output.py pycodex/debug_client/state.py pycodex/debug_client/reader.py tests/test_debug_client_commands_rs.py tests/test_debug_client_output_rs.py tests/test_debug_client_state_rs.py tests/test_debug_client_reader_rs.py tests/test_debug_client_client_rs.py tests/test_debug_client_main_rs.py`
  passed on 2026-06-19.
