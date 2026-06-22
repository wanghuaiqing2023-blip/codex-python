# codex-cli src/wsl_paths.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/cli/src/wsl_paths.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-cli` |
| Rust module | `codex/codex-rs/cli/src/wsl_paths.rs` |
| Python module | `pycodex/cli/wsl_paths.py` |
| Python tests | `tests/test_cli_wsl_paths.py` |
| Status | `complete_candidate` |

`src/wsl_paths.rs` owns CLI path normalization when the process runs under
WSL.

## Covered Behavior Areas

- Rust `win_path_to_wsl` is represented by `win_path_to_wsl`.
- Absolute Windows drive paths using `\` or `/` are mapped to
  `/mnt/<drive>/...`.
- Drive letters are lowercased.
- Drive-root paths map to `/mnt/<drive>`.
- Non-drive and UNC-style paths are rejected.
- Rust `normalize_for_wsl` is represented by `normalize_for_wsl`.
- Normalization maps Windows drive paths only when WSL is active; otherwise it
  returns the input unchanged.

## Rust Test Inventory

The Rust module currently contains 2 named local test functions:

- `win_to_wsl_basic`
- `normalize_is_noop_on_unix_paths`

Both local Rust tests are reconciled by:

- `tests/test_cli_wsl_paths.py::CliWslPathsTests::test_win_path_to_wsl_basic`
- `tests/test_cli_wsl_paths.py::CliWslPathsTests::test_normalize_for_wsl_maps_only_when_wsl`

Additional local parity coverage:

- drive-root conversion.
- UNC-style path rejection.
- deterministic WSL/non-WSL branch selection through an explicit test flag.

## Intentional Adaptation

Rust re-exports `codex_utils_path::is_wsl`. Python imports the canonical
`pycodex.utils.path.is_wsl` helper and exposes an optional `wsl` override so the
module contract can be verified without depending on the host platform.

## Completion Criteria

Before promoting this module:

1. Defer actual pytest execution until `codex-cli` functional code is complete,
   per the current crate automation instruction.
2. After validation, update this file to `complete`, then update
   `CRATE_COMPLETION_STATUS.md`.
