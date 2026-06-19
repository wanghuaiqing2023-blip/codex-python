# pycodex.terminal_detection

Python alignment target for Rust crate `codex-terminal-detection`.

Rust coordinate:

- `codex/codex-rs/terminal-detection/src/lib.rs`
- Rust test module: `codex/codex-rs/terminal-detection/src/terminal_tests.rs`

Python mapping:

- `pycodex/terminal_detection/__init__.py`

The Python module preserves the Rust terminal detection contract:

- structured `TerminalInfo`, `TerminalName`, `Multiplexer`, and `TmuxClientInfo` records
- detection from `TERM_PROGRAM`, terminal-specific environment variables, and `TERM`
- tmux and Zellij multiplexer metadata
- zellij version parsing
- User-Agent token formatting and sanitization

