# codex-ansi-escape test alignment

This ledger records module-scoped Rust behavior contracts for
`codex-ansi-escape` that have Python parity evidence.

`codex-ansi-escape` contains one tracked Rust module and is complete.

## complete

### `src/lib.rs` ANSI escape rendering helpers

- Rust owner: `codex-ansi-escape`
- Rust module: `codex/codex-rs/ansi-escape/src/lib.rs`
- Python module: `pycodex/ansi_escape/__init__.py`
- Python status file: `pycodex/ansi_escape/LIB_RS_STATUS.md`
- Status: `complete`
- Evidence: Rust defines `expand_tabs`, `ansi_escape`, and
  `ansi_escape_line`. Python mirrors the behavior needed by Codex transcript
  rendering: tabs are replaced with four spaces before rendering, ANSI control
  sequences are removed from rendered text, `Text` contains rendered `Line`
  values, and the line helper returns the first rendered line for multi-line
  input.
- Validation: `python -m pytest tests/test_ansi_escape_lib_rs.py -q` passed
  with `5 passed`; `python -m py_compile pycodex/ansi_escape/__init__.py
  tests/test_ansi_escape_lib_rs.py` also passed on 2026-06-17.
