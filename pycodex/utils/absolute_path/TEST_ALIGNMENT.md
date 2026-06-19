# codex-utils-absolute-path test alignment

Rust crate: `codex-utils-absolute-path`

Python module: `pycodex/utils/absolute_path/__init__.py`

Status: `complete`

Certified modules:

- `codex/codex-rs/utils/absolute-path/src/absolutize.rs`
- `codex/codex-rs/utils/absolute-path/src/lib.rs`

Rust-derived coverage added for `src/absolutize.rs`:

- `tests::absolute_path_without_dots_is_unchanged`
- `tests::absolute_path_dots_are_removed`
- `tests::relative_path_without_dot_uses_base`
- `tests::relative_path_with_current_dir_uses_base`
- `tests::relative_path_with_parent_dir_uses_base_parent`
- `tests::parent_dir_above_root_stays_at_root`
- `tests::empty_path_uses_base`

Rust-derived/source-contract coverage added for `src/lib.rs`:

- `tests::create_with_absolute_path_ignores_base_path`
- `tests::from_absolute_path_checked_rejects_relative_path`
- `tests::relative_path_dots_are_normalized_against_base_path`
- `tests::canonicalize_returns_absolute_path_buf`
- `tests::canonicalize_returns_error_for_missing_path`
- `tests::ancestors_returns_absolute_path_bufs`
- `tests::guard_used_in_deserialization`
- `tests::home_directory_root_is_expanded_in_deserialization`
- `tests::home_directory_subpath_is_expanded_in_deserialization`
- `tests::home_directory_double_slash_is_expanded_in_deserialization`
- `tests::normalize_windows_device_path_strips_supported_verbatim_prefixes`
- source-contract coverage for `join`.

Validation:

- `python -m pytest tests/test_utils_absolute_path_absolutize.py -q`
- `python -m py_compile pycodex/utils/absolute_path/__init__.py tests/test_utils_absolute_path_absolutize.py`
