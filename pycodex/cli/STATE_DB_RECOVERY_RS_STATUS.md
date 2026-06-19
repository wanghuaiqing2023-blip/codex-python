# codex-cli src/state_db_recovery.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/state_db_recovery.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/state_db_recovery.rs` |
| Python module | `pycodex/cli/state_db_recovery.py` |
| Python exports | `pycodex/cli/__init__.py` state_db_* aliases |
| Python tests | `tests/test_cli_state_db_recovery.py` |
| Status | `complete_candidate` |

`src/state_db_recovery.rs` owns CLI recovery behavior for local state database
startup failures: identifying embedded startup errors, separating lock
contention from repairable corruption, prompting for safe repair, backing up
owned SQLite files and sidecars, and printing user-facing recovery guidance.

## Covered Behavior Areas

- `startup_error` extracts the local state DB startup boundary error from a
  wrapper error.
- `is_locked` classifies lock/busy startup details and leaves corruption
  details on the repair/diagnostic path.
- `confirm_repair`, `print_locked_guidance`, `print_diagnostic_guidance`,
  `print_repair_backups`, and `print_technical_details` preserve Rust stderr
  message shapes.
- `sqlite_paths` expands database paths to the DB, `-wal`, and `-shm` paths.
- `backup_path` renames to the first available
  `.<repair_suffix>.<sequence>.bak` path.
- `repair_files` backs up a blocking sqlite-home file, creates the sqlite-home
  directory when missing or replaced, backs up owned runtime DB files and
  sidecars, and errors when no repairable files are found.

## Rust Test Inventory

The Rust module currently contains 3 named local test functions:

- `repair_backs_up_owned_database_files`
- `repair_replaces_blocking_sqlite_home_file`
- `lock_failures_skip_repair`

Those local tests are reconciled by:

- `tests/test_cli_state_db_recovery.py::CliStateDbRecoveryTests::test_repair_backs_up_owned_database_files`
- `tests/test_cli_state_db_recovery.py::CliStateDbRecoveryTests::test_repair_replaces_blocking_sqlite_home_file`
- `tests/test_cli_state_db_recovery.py::CliStateDbRecoveryTests::test_is_locked_matches_rust_lock_contention_detection`

Additional source-contract coverage:

- `startup_error` wrapper extraction.
- SQLite sidecar expansion.
- backup path sequence selection.
- empty repair guard.
- locked, diagnostic, backup, and confirmation stderr guidance.

## Intentional Adaptation

Rust uses `std::io::Error::get_ref().downcast_ref::<LocalStateDbStartupError>`
and async Tokio filesystem calls. Python adapts this to exception
`__cause__`/`__context__` inspection and synchronous standard-library file
operations while preserving the module behavior contract and exported CLI
helper surface.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
