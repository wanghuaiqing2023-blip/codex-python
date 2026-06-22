# pycodex.ansi_escape

Canonical Python package for helpers ported from the Rust workspace crate:

- Rust crate: `codex/codex-rs/ansi-escape`
- Rust module: `src/lib.rs`
- Python package: `pycodex/ansi_escape`

## Completion status

`codex-ansi-escape` is complete as of 2026-06-17. The single Rust module
contract is covered by `tests/test_ansi_escape_lib_rs.py`, which passed with:

```text
python -m pytest tests/test_ansi_escape_lib_rs.py -q
5 passed
```

`python -m py_compile pycodex/ansi_escape/__init__.py
tests/test_ansi_escape_lib_rs.py` also passed.

## Module correspondence

| Rust behavior area | Python module |
| --- | --- |
| `src/lib.rs` tab normalization and ANSI escape rendering helpers | `pycodex/ansi_escape/__init__.py` |

## `src/lib.rs`

Rust returns `ratatui::text::Text` and `Line` values after parsing ANSI styled
strings through `ansi-to-tui`. The Python port keeps the dependency-light
behavior needed by transcript rendering: every tab is expanded to four spaces,
ANSI control sequences are stripped, `ansi_escape` returns a small `Text`
wrapper containing rendered `Line` values, and `ansi_escape_line` returns the
first rendered line when given multi-line input.
