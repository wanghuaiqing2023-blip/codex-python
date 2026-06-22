# codex-utils-cargo-bin test alignment

Rust crate: `codex-utils-cargo-bin`

Rust module: `codex/codex-rs/utils/cargo-bin/src/lib.rs`

Python module: `pycodex/utils/cargo_bin/__init__.py`

Status: `complete`

Validation:

- `python -m pytest tests/test_utils_cargo_bin.py -q`
- `python -m py_compile pycodex/utils/cargo_bin/__init__.py tests/test_utils_cargo_bin.py`

Rust-derived coverage:

- No Rust unit tests are present in this crate.
- Python tests are source-contract tests derived from `src/lib.rs`.

Covered contracts:

- Cargo binary env key generation, including dash-to-underscore aliasing.
- `RUNFILES_MANIFEST_ONLY` readiness detection.
- env-provided binary resolution and missing-path errors.
- `cargo_bin` env precedence and lookup failure metadata.
- Cargo resource joining with `CARGO_MANIFEST_DIR`.
- Bazel runfile path construction under `_main/<package>/<resource>`.
- missing Bazel package error behavior.
- repository-root derivation from `repo_root.marker`.
- runfile path normalization.

Known gaps: none for `src/lib.rs`. The Rust `find_resource!` macro is represented by the Python `find_resource` helper because Python does not have call-site compile-time environment macros.
