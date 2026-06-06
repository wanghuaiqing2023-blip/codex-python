# pycodex.utils.home_dir

Python counterpart for the Rust `codex-utils-home-dir` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-home-dir
Rust path: codex/codex-rs/utils/home-dir
Cargo role: resolve the Codex configuration directory
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/home_dir/__init__.py` | crate public surface and `CODEX_HOME` resolution |

## Alignment Unit

The acceptance unit is the crate public behavior contract:

```text
utils.home_dir.env_valid_directory
utils.home_dir.env_missing_path
utils.home_dir.env_file_path
utils.home_dir.default_home
```

## Current Status

Status: module_completed_with_focused_validation.

The Python implementation preserves Rust's user-visible behavior: non-empty
`CODEX_HOME` must exist, must be a directory, and is resolved/canonicalized;
missing or empty `CODEX_HOME` falls back to `home/.codex` without requiring that
directory to exist. Python accepts any mapping-like environment object for
testability while keeping the same environment-key semantics.

## Test Sources

Rust tests:

```text
codex/codex-rs/utils/home-dir/src/lib.rs
```

Python parity tests:

```text
tests/test_core_paths.py
```

## Stop Rule

This module contract is complete once `tests/test_core_paths.py` passes. Do not
rescan this slice unless a related test fails, Rust source changes, or a future
task explicitly targets Codex home-directory behavior.
