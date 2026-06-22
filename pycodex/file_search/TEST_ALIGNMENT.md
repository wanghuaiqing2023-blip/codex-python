# codex-file-search test alignment

Rust crate: `codex-file-search`

Python package: `pycodex/file_search`

Status: `complete`

Module mapping:

- `codex/codex-rs/file-search/src/lib.rs` ->
  `pycodex/file_search/__init__.py` (`complete_candidate`)
- `codex/codex-rs/file-search/src/cli.rs` ->
  `pycodex/file_search/cli.py` (`complete_candidate`)
- `codex/codex-rs/file-search/src/main.rs` ->
  `pycodex/file_search/main.py` and `pycodex/file_search/__main__.py`
  (`complete_candidate`)

Rust behavior prepared in `tests/test_file_search_lib_rs.py`:

- `tie_breakers_sort_by_path_when_scores_equal`
- `file_name_from_path_uses_basename`
- `file_name_from_path_falls_back_to_full_path`
- `run_returns_matches_for_query`
- `run_returns_directory_matches_for_query`
- `cancel_exits_run`
- `session_accepts_query_updates_after_walk_complete`
- `parent_gitignore_outside_repo_does_not_hide_repo_files`
- `git_repo_still_respects_local_gitignore_when_enabled`

Rust behavior prepared in `tests/test_file_search_cli_rs.py`:

- `Cli` clap defaults: `json=false`, `limit=64`, `cwd=None`,
  `compute_indices=false`, `threads=2`, empty excludes, no pattern
- short/long option parsing for `-l/--limit`, `-C/--cwd`, `--compute-indices`,
  `--threads`, and repeated `-e/--exclude`
- `NonZero<usize>` zero rejection for `limit` and `threads`

Rust behavior covered in `tests/test_file_search_main_rs.py`:

- `StdioReporter::report_match` JSON line serialization
- `StdioReporter::report_match` ANSI bold rendering for sorted match indices
- `run_main` `Cli` to `FileSearchOptions` mapping
- truncated-result warning behavior
- no-pattern warning plus directory listing branch
- `show_indices = cli.compute_indices && stdout().is_terminal()` terminal gate

Validation:

- `python -m py_compile pycodex/file_search/__init__.py pycodex/file_search/cli.py pycodex/file_search/main.py pycodex/file_search/__main__.py tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py`
  (passed)
- `python -m pytest tests/test_file_search_lib_rs.py tests/test_file_search_cli_rs.py tests/test_file_search_main_rs.py -q`
  (17 passed)
