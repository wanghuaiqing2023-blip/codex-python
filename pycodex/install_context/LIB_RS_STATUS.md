# codex-install-context src/lib.rs status

Rust coordinate: `codex/codex-rs/install-context/src/lib.rs`

Python coordinate: `pycodex/install_context/__init__.py`

Status: `complete`

Behavior contract:

- detect `InstallMethod::{Standalone,Npm,Bun,Brew,Other}` from executable path and manager environment.
- detect package layouts rooted at `bin/` with `codex-package.json`.
- prefer package `codex-path/rg` over standalone resource `rg`, then fall back to default `rg`.
- resolve bundled resources and zsh paths only when target files exist.

Evidence:

- `tests/test_install_context_lib_rs.py` ports the Rust test scenarios and covers public layout constants.
