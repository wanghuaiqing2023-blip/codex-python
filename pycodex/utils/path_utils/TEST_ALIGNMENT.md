# codex-utils-path test alignment

Rust crate: `codex-utils-path`

Python module: `pycodex/utils/path_utils/__init__.py`

Status: `complete`

Certified modules:

- `codex/codex-rs/utils/path-utils/src/lib.rs` -> `pycodex/utils/path_utils/__init__.py`
- `codex/codex-rs/utils/path-utils/src/env.rs`

Rust-derived coverage already present:

- `path_utils_tests.rs::symlinks::symlink_cycles_fall_back_to_root_write_path`
- `path_utils_tests.rs::wsl::wsl_mnt_drive_paths_lowercase`
- `path_utils_tests.rs::wsl::wsl_non_drive_paths_unchanged`
- `path_utils_tests.rs::wsl::wsl_non_mnt_paths_unchanged`
- `path_utils_tests.rs::native_workdir::windows_verbatim_paths_are_simplified`
- `path_utils_tests.rs::native_workdir::non_windows_paths_are_unchanged`
- `path_utils_tests.rs::path_comparison::matches_identical_existing_paths`
- `path_utils_tests.rs::path_comparison::falls_back_to_raw_equality_when_paths_cannot_be_normalized`
- source-contract tests for missing symlink targets and atomic writes.
- source-contract test for `env.rs::is_wsl` Linux environment and proc-version behavior.

`src/lib.rs` and `src/env.rs` are both certified. `src/path_utils_tests.rs` is a Rust test module and is mapped through `tests/test_utils_path_utils.py`.

Validation:

- `python -m pytest tests/test_utils_path_utils.py -q`
- `python -m py_compile pycodex/utils/path_utils/__init__.py tests/test_utils_path_utils.py`
