# codex-file-search src/main.rs Status

Rust source:

- `codex/codex-rs/file-search/src/main.rs`

Python mapping:

- `pycodex/file_search/main.py`
- `pycodex/file_search/__main__.py`

Status: `complete_candidate`

Implemented behavior:

- `StdioReporter` JSON output for `FileMatch` values.
- Plain path output and ANSI-bold index rendering when `--compute-indices` is
  active and stdout is terminal-like.
- Truncated result warnings in both JSON and human-readable forms.
- No-pattern warning plus directory-listing branch.
- `Cli` to `FileSearchOptions` mapping before invoking the real Python
  `run(...)` file-search interface.
- `python -m pycodex.file_search` executable handoff.

Intentional adaptation:

- Rust exposes `run_main` from `src/lib.rs` for the binary. Python keeps the
  executable orchestration in `main.py` so the package library surface remains
  focused on search data/session APIs while still preserving the binary's
  behavior contract.

Validation:

- `python -m py_compile pycodex/file_search/__init__.py pycodex/file_search/cli.py pycodex/file_search/main.py pycodex/file_search/__main__.py tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py`
- `python -m pytest tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py -q`
  passed with 17 tests on 2026-06-19.
