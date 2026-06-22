# pycodex.bwrap

Python port of the Rust `codex-bwrap` binary crate.

Rust coordinate:

- `codex/codex-rs/bwrap/src/main.rs`

Python coordinate:

- `pycodex/bwrap/__init__.py`

Status: complete for the single Rust module.

Notes:

- The Rust crate links and calls the bundled bubblewrap C entrypoint when built for Linux with `bwrap_available`.
- Python exposes a testable branch plan and runner hook. It preserves Rust cfg-gated branch behavior and argv validation without embedding bubblewrap C sources.
