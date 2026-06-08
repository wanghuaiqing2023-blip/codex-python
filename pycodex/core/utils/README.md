# pycodex.core.utils

Rust counterpart:

```text
Rust crate: codex-core
Rust module path: codex/codex-rs/core/src/utils
```

`codex-core::utils` is a small module namespace. Its `path_utils` module
re-exports the external Rust `codex-utils-path-utils` public surface. The
Python counterpart keeps that coordinate as `pycodex.core.utils.path_utils`
while delegating the implementation to `pycodex.utils.path_utils`.
