# `codex-ansi-escape/src/lib.rs` alignment status

Status: `complete`

Rust owner: `codex-ansi-escape`  
Rust module: `codex/codex-rs/ansi-escape/src/lib.rs`  
Python module: `pycodex/ansi_escape/__init__.py`

## Behavior contract

- `expand_tabs` replaces each tab with four spaces before transcript rendering.
- `ansi_escape` renders ANSI-styled input into a `Text` wrapper whose `lines`
  contain rendered `Line` values; the Python port strips ANSI control
  sequences instead of preserving ratatui style spans.
- `ansi_escape_line` returns the first rendered line, matching Rust's
  single-line helper behavior when multi-line input is received.

## Python adaptation notes

- Rust uses `ansi-to-tui` and `ratatui::text::{Text, Line}`. Python keeps a
  dependency-light plain-text `Text`/`Line` wrapper because the current Python
  consumers need rendered transcript text rather than terminal style spans.
- Rust panic paths for impossible parser errors are not mirrored because the
  Python implementation strips recognized ANSI control sequences with a regex
  and validates input types directly.

## Validation

- `python -m pytest tests/test_ansi_escape_lib_rs.py -q` passed with
  `5 passed`.
- `python -m py_compile pycodex/ansi_escape/__init__.py
  tests/test_ansi_escape_lib_rs.py`
