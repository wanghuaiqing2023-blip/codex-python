# codex-terminal-detection Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/terminal-detection/src/lib.rs`
- `codex/codex-rs/terminal-detection/src/terminal_tests.rs`

Python module:

- `pycodex/terminal_detection/__init__.py`

Parity evidence:

- `tests/test_terminal_detection_lib_rs.py`

Rust-derived coverage:

- `TERM_PROGRAM` detection and precedence over later probes
- explicit iTerm2, Apple Terminal, Ghostty, VS Code, and Warp terminal detection
- tmux multiplexer and tmux client termtype/termname handling
- Zellij multiplexer and version parsing
- WezTerm, kitty, Alacritty, Konsole, GNOME Terminal, VTE, and Windows Terminal detection
- `TERM` fallback handling for unknown, dumb, and WezTerm terms
- User-Agent token formatting and invalid-header-character sanitization

Validation:

- `python -m pytest tests\test_terminal_detection_lib_rs.py -q` -> `10 passed`
- `python -m py_compile pycodex\terminal_detection\__init__.py tests\test_terminal_detection_lib_rs.py` -> passed

Known adaptations:

- Rust hides injectable environment helpers behind private traits. Python exposes equivalent dependency injection through optional `env`, `tmux_client_info`, and `zellij_version` parameters on `terminal_info` for deterministic tests.

