# pycodex.utils.absolute_path

Python alignment target for Rust crate `codex-utils-absolute-path`.

Rust coordinates:

- `codex/codex-rs/utils/absolute-path/src/absolutize.rs`
- `codex/codex-rs/utils/absolute-path/src/lib.rs`

Python mapping:

- `pycodex/utils/absolute_path/__init__.py`

Current status: complete.

Certified modules:

- `src/absolutize.rs`: local path absolutization and dot/parent normalization behavior.
- `src/lib.rs`: `AbsolutePathBuf`, guard-based deserialization, home expansion, public path helpers, Windows device-path normalization, and symlink-preserving canonicalization.

Focused validation:

- `python -m pytest tests/test_utils_absolute_path_absolutize.py -q`
- `python -m py_compile pycodex/utils/absolute_path/__init__.py tests/test_utils_absolute_path_absolutize.py`
