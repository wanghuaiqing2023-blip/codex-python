# codex-v8-poc

Rust crate: `codex-v8-poc`

Rust anchor: `codex/codex-rs/v8-poc`

Current certified modules:

- `v8-poc/src/lib.rs`

The upstream crate is a Bazel-wired V8 proof of concept. PyCodex keeps a
standard-library facade in `pycodex/v8_poc/__init__.py`: it preserves the public
crate API (`bazel_target`, `embedded_v8_version`, `linked_v8_has_sandbox`) and
mirrors the Rust smoke-test contracts with narrow helper functions rather than
embedding V8.

Remaining Rust modules: none.
