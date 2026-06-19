# pycodex.install_context

Python port of Rust crate `codex-install-context`.

Rust coordinate:

- `codex/codex-rs/install-context/src/lib.rs`

Python coordinate:

- `pycodex/install_context/__init__.py`

Status: complete for the single Rust module.

Notes:

- Python mirrors Rust install-method detection for npm, bun, Homebrew, standalone release layouts, and package-layout installs.
- Bundled resource lookup follows Rust's file-only behavior and ignores directories.
