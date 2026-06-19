# codex-cli src/lib.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/cli/src/lib.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/lib.rs` |
| Python package root | `pycodex/cli/__init__.py` |
| Python parser integration | `pycodex/cli/parser.py` sandbox/login dispatch |
| Supporting Python modules | `pycodex/cli/debug_sandbox.py`, `pycodex/cli/login.py`, `pycodex/cli/exit_status.py` |
| Python tests | `tests/test_cli_parser.py`, `tests/test_cli_debug_sandbox.py`, `tests/test_cli_login.py`, `tests/test_cli_exit_status.py` |
| Status | `complete_candidate` |

`src/lib.rs` owns the `codex-cli` library boundary: child-module
declarations, public re-exports for login and sandbox entrypoints, host sandbox
command option structs, and the `parse_allow_unix_socket_path` value-parser
boundary used by the Seatbelt command.

The module is now a `complete_candidate`: its module-owned public surface is
mapped to existing Python package exports, parser behavior, and focused helper
contracts. Actual pytest validation is deferred until `codex-cli` functional
code is complete, per the current crate automation rule.

## Completed Behavior Areas

- Child module ownership is mapped as:
  - `debug_sandbox` -> `pycodex/cli/debug_sandbox.py`
  - `exit_status` -> `pycodex/cli/exit_status.py`
  - `login` -> `pycodex/cli/login.py`
- Public sandbox entrypoint re-exports are represented by `pycodex.cli`
  debug-sandbox exports and the parser sandbox execution path.
- Public login re-exports are represented by `pycodex/cli/login.py` and the
  login module status file.
- `SeatbeltCommand`, `LandlockCommand`, and `WindowsCommand` option surfaces
  are represented by `pycodex/cli/parser.py` sandbox parsing and
  `pycodex/cli/debug_sandbox.py` planning helpers:
  - `--permissions-profile`
  - `--profile` / `-p`
  - `--cd` / `-C`
  - `--include-managed-config`
  - trailing command arguments
  - Seatbelt-only `--allow-unix-socket`
  - Seatbelt denial logging in the debug-sandbox helper boundary
- Clap `requires = "permissions_profile"` semantics for `--cd` and
  `--include-managed-config` are mirrored by the Python sandbox parser.
- Seatbelt `parse_allow_unix_socket_path` ownership is represented by parser
  acceptance plus debug-sandbox backend/entrypoint planning that carries Unix
  socket paths as command-scoped inputs.

## Rust Test Inventory

The Rust module currently contains no local `#[test]` functions.

The source contract is reconciled by existing Python coverage:

- `tests/test_cli_parser.py::CliParserTests::test_parse_sandbox_accepts_profile_flags_and_dependencies`
- `tests/test_cli_parser.py::CliParserTests::test_sandbox_requires_permissions_profile_with_cd_or_managed_config`
- `tests/test_cli_debug_sandbox.py` debug-sandbox entrypoint/backend planning coverage
- `tests/test_cli_login.py` login command-surface coverage
- `tests/test_cli_exit_status.py` exit-status mapping coverage

## Intentional Adaptation

Rust uses Clap derive structs in `src/lib.rs`; Python keeps command parsing in
`pycodex/cli/parser.py` and executable planning in `pycodex/cli/debug_sandbox.py`.
This status file claims the library-boundary command surface and export mapping,
not the entire `src/main.rs` top-level CLI dispatch tree.

`marketplace_cmd`, `mcp_cmd`, `plugin_cmd`, `remote_control_cmd`,
`desktop_app/*`, and `main.rs` remain separate Rust module boundaries.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
