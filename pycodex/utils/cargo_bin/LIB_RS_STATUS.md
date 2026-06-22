# codex-utils-cargo-bin src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/cargo-bin/src/lib.rs`

Python coordinate: `pycodex/utils/cargo_bin/__init__.py`

Status: `complete`

Behavior contract:

- Generate Cargo binary env keys and dash-to-underscore aliases.
- Resolve binary paths from `CARGO_BIN_EXE_*`, Bazel runfiles, or fallback path lookup.
- Preserve Rust-shaped error metadata for current executable/current directory, missing resolved paths, and missing binaries.
- Resolve Cargo and Bazel resource paths.
- Derive `repo_root` by walking four parents above `repo_root.marker`.
- Normalize runfile paths by dropping `.` and cancelling normal `..` components.

Evidence:

- `tests/test_utils_cargo_bin.py` covers the Rust source contracts because the Rust crate has no unit tests.
- `python -m pytest tests/test_utils_cargo_bin.py -q` passed.
- `python -m py_compile pycodex/utils/cargo_bin/__init__.py tests/test_utils_cargo_bin.py` passed.
