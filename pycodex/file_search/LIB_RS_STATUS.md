# file-search/src/lib.rs status

Status: `complete_candidate`

Rust source:

- `codex/codex-rs/file-search/src/lib.rs`

Python target:

- `pycodex/file_search/__init__.py`

Implemented public API:

- `FileMatch`
- `MatchType`
- `FileSearchResults`
- `FileSearchSnapshot`
- `FileSearchOptions`
- `SessionReporter`
- `FileSearchSession`
- `create_session`
- `Reporter`
- `run`
- `cmp_by_score_desc_then_path_asc`
- `file_name_from_path`

Implemented behavior:

- fuzzy file/directory matching with deterministic score-desc/path-asc ordering
- optional match indices for highlighting
- result limiting and total match count
- cancel flag short-circuiting
- session update/complete reporter callbacks
- local `.gitignore` handling only when the search root is in a git context,
  including simple negated whitelist patterns used by the Rust regression tests
- exclude pattern filtering

Notes:

- The Rust implementation uses `ignore` and `nucleo`; the Python port uses a
  dependency-light standard-library walker and subsequence fuzzy matcher while
  preserving the module contract and result shapes.
- Crate-level validation now includes the CLI and executable entrypoint modules.

Validation:

- `python -m py_compile pycodex/file_search/__init__.py pycodex/file_search/cli.py pycodex/file_search/main.py pycodex/file_search/__main__.py tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py`
  (passed)
- `python -m pytest tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py -q`
  (17 passed)
