# codex-debug-client src/commands.rs Status

Rust source:

- `codex/codex-rs/debug-client/src/commands.rs`

Python mapping:

- `pycodex/debug_client/commands.py`

Status: `complete_candidate`

Implemented behavior:

- `InputAction` message/command variants.
- `UserCommand` variants and aliases.
- `ParseError` variants and message text.
- `parse_input(...)` trimming, command dispatch, required argument handling,
  empty-command handling, and unknown-command errors.

Validation:

- `python -m py_compile pycodex/debug_client/__init__.py pycodex/debug_client/commands.py tests/test_debug_client_commands_rs.py`
  passed on 2026-06-19.
- Focused pytest is deferred until remaining `codex-debug-client` modules are
  complete.
