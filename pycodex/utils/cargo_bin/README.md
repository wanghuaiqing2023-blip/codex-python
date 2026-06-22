# pycodex.utils.cargo_bin

Python alignment target for Rust crate `codex-utils-cargo-bin`.

Rust coordinate:

- `codex/codex-rs/utils/cargo-bin/src/lib.rs`

Python mapping:

- `pycodex/utils/cargo_bin/__init__.py`

The module preserves the Rust test-helper contract:

- `cargo_bin` resolves `CARGO_BIN_EXE_*` values before falling back to path lookup.
- dash-containing binary names also check the Cargo underscore alias.
- Cargo runfiles resolve relative to `CARGO_MANIFEST_DIR`.
- Bazel runfiles resolve through `RUNFILES_MANIFEST_ONLY` plus runfiles roots/manifests.
- `repo_root` derives the repository root by walking four parents above `repo_root.marker`.
- runfile paths normalize `.` and cancellable `..` components.
