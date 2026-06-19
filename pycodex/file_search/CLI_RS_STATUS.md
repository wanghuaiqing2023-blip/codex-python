# file-search/src/cli.rs status

Status: `complete_candidate`

Rust source:

- `codex/codex-rs/file-search/src/cli.rs`

Python target:

- `pycodex/file_search/cli.py`

Implemented public API:

- `Cli`
- `Cli.parse_args`

Implemented behavior:

- `--json` defaults to `false` and sets `json=true`.
- `--limit`/`-l` defaults to `64` and rejects zero values.
- `--cwd`/`-C` parses an optional search directory as `Path`.
- `--compute-indices` defaults to `false`.
- `--threads` defaults to `2` and rejects zero values.
- `--exclude`/`-e` appends repeated exclude patterns.
- optional positional `pattern` maps to `None` when absent.

Validation:

- `python -m py_compile pycodex/file_search/__init__.py pycodex/file_search/cli.py pycodex/file_search/main.py pycodex/file_search/__main__.py tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py`
  (passed)
- `python -m pytest tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py -q`
  (17 passed)
