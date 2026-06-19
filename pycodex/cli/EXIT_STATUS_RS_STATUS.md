# codex-cli src/exit_status.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/exit_status.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/exit_status.rs` |
| Python module | `pycodex/cli/exit_status.py` |
| Python tests | `tests/test_cli_exit_status.py` |
| Status | `complete_candidate` |

`src/exit_status.rs` owns the CLI subprocess-exit propagation contract.

## Covered Behavior Areas

- Rust `handle_exit_status` preserves normal process exit codes.
- Rust Unix signal exits map to `128 + signal`.
- Rust fallback behavior exits with code `1` when no code or signal is
  available.
- Python represents the observable contract with
  `exit_code_from_returncode`, because Python subprocess return codes expose
  signal termination as negative integers.
- Non-integer Python inputs are rejected with a clear `TypeError`.

## Rust Test Inventory

The Rust module currently contains no local `#[test]` functions.

Python parity evidence is source-contract based and covered by:

- `tests/test_cli_exit_status.py::CliExitStatusTests::test_exit_code_from_returncode_matches_rust_exit_status_mapping`

## Intentional Adaptation

Rust's helper is divergent and calls `std::process::exit`. Python keeps the
same observable exit-code mapping as a pure helper so CLI callers can decide
when to terminate and tests can inspect the result without exiting the process.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
