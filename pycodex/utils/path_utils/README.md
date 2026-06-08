# pycodex.utils.path_utils

Python counterpart for the Rust `codex-utils-path-utils` crate.

## Rust Counterpart

```text
Rust crate: codex-utils-path-utils
Rust path: codex/codex-rs/utils/path-utils
Cargo role: path normalization, symlink write-path resolution, and atomic writes
```

## Rust Modules Covered

| Rust module/file | Python module/file | Alignment role |
|---|---|---|
| `src/lib.rs` | `pycodex/utils/path_utils/__init__.py` | crate public surface and local helper behavior |
| `src/env.rs` | `pycodex/utils/path_utils/__init__.py` | WSL environment detection |
| `src/path_utils_tests.rs` | `tests/test_utils_path_utils.py` | Rust-derived parity tests |

## Alignment Unit

The acceptance unit is a module-scoped behavior contract:

```text
utils.path_utils.path_comparison
utils.path_utils.wsl_normalization
utils.path_utils.native_workdir_normalization
utils.path_utils.symlink_write_paths
utils.path_utils.atomic_write
utils.path_utils.wsl_detection
```

## Current Status

Status: module_completed_with_focused_validation.

The Python module covers the Rust public surface used by core paths:
canonicalized path comparison with raw-equality fallback, WSL `/mnt/<drive>`
ASCII lowering, Windows native workdir simplification, symlink write/read path
resolution, atomic text writes, and WSL detection. The existing shell runtime
snapshot comparison now uses this package-level helper instead of a local
runtime-only duplicate.

## Test Sources

Primary Python parity tests:

```text
tests/test_utils_path_utils.py
tests/test_core_tool_runtimes.py
```

Rust test/source anchors:

```text
codex/codex-rs/utils/path-utils/src/lib.rs
codex/codex-rs/utils/path-utils/src/env.rs
codex/codex-rs/utils/path-utils/src/path_utils_tests.rs
```

## Stop Rule

This module contract is complete once the focused path-utils tests and runtime
snapshot tests pass. Revisit only if Rust source changes, path comparison tests
fail, or a future core file-tool slice needs deeper filesystem behavior.
