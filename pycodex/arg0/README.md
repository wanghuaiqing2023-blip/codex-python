# pycodex.arg0

Python alignment target for Rust crate `codex-arg0`.

Rust coordinate:

- `codex/codex-rs/arg0/src/lib.rs`

Python mapping:

- `pycodex/arg0/__init__.py`

The Python module preserves the dependency-light `src/lib.rs` behavior contract:

- `Arg0DispatchPaths` and `Arg0PathEntryGuard` path/guard records.
- Linux sandbox executable path preference through `linux_sandbox_exe_path`.
- dotenv loading with Rust's `CODEX_` environment-variable filter.
- CODEX_HOME-scoped helper alias directory creation and PATH prepending.
- stale helper directory cleanup through `.lock` files.
- injected-handler arg0/argv1 dispatch facade for process modes owned by neighboring crates.

Concrete process-mode execution remains delegated to the owning modules, matching the
project policy for extension and runtime-heavy boundaries.

