# codex-debug-client src/output.rs Status

Rust source:

- `codex/codex-rs/debug-client/src/output.rs`

Python mapping:

- `pycodex/debug_client/output.py`

Status: `complete_candidate`

Implemented behavior:

- `LabelColor` variants and ANSI label formatting.
- `Output.server_json_line(...)` JSONL file writing and filtered stdout
  behavior.
- `Output.server_line(...)` prompt clear/write/redraw behavior.
- `Output.client_line(...)` stderr write and prompt clear behavior.
- `prompt(...)` and `set_prompt(...)` state handling.
- injectable stdout/stderr/jsonl file streams for future module integration and
  tests.

Validation:

- `python -m py_compile pycodex/debug_client/__init__.py pycodex/debug_client/commands.py pycodex/debug_client/output.py tests/test_debug_client_commands_rs.py tests/test_debug_client_output_rs.py`
  passed on 2026-06-19.
- Focused pytest is deferred until remaining `codex-debug-client` modules are
  complete.
