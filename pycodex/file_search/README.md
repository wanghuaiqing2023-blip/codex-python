# pycodex.file_search

Rust crate: `codex-file-search`

Rust anchor: `codex/codex-rs/file-search`

Module map:

- `codex/codex-rs/file-search/src/lib.rs` ->
  `pycodex/file_search/__init__.py` (`complete_candidate`)
- `codex/codex-rs/file-search/src/cli.rs` ->
  `pycodex/file_search/cli.py` (`complete_candidate`)
- `codex/codex-rs/file-search/src/main.rs` ->
  `pycodex/file_search/main.py` and `pycodex/file_search/__main__.py`
  (`complete_candidate`)

The current Python module mirrors the Rust library data shapes and search
contract with a standard-library fuzzy matcher/walker. CLI parsing is mapped in
`cli.py`; executable stdout/stderr reporting and command orchestration are
mapped in `main.py`.
