# codex-utils-path src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/path-utils/src/lib.rs`

Python coordinate: `pycodex/utils/path_utils/__init__.py`

Status: `complete`

Behavior contract:

- `normalize_for_path_comparison` canonicalizes paths and applies WSL normalization.
- `paths_match_after_normalization` compares normalized paths and falls back to raw equality when normalization fails.
- `normalize_for_native_workdir` strips Windows verbatim prefixes when running with Windows semantics.
- `normalize_for_wsl` lowercases ASCII `/mnt/<drive>` WSL mount paths when WSL is active.
- `resolve_symlink_write_paths` follows symlink chains, handles missing targets, and falls back to the original write path on cycles or metadata/readlink failures.
- `write_atomically` creates parent directories and persists text through a temporary file replacement.

Evidence:

- `tests/test_utils_path_utils.py` already maps the Rust `path_utils_tests.rs` coverage for `src/lib.rs` behavior.
- This turn did not run tests because the crate still has pending `src/env.rs` certification and the automation asks to defer actual testing until crate functional code is complete.
