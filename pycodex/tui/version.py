"""Behavior port for Rust ``codex-tui::version``.

Upstream source: ``codex/codex-rs/tui/src/version.rs``.
"""

from __future__ import annotations

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="version", source="codex/codex-rs/tui/src/version.rs")

# Rust uses ``env!("CARGO_PKG_VERSION")``.  The upstream ``codex-tui`` crate
# inherits ``version.workspace = true`` from ``codex/codex-rs/Cargo.toml``.
CODEX_CLI_VERSION = "0.0.0"

__all__ = [
    "CODEX_CLI_VERSION",
    "RUST_MODULE",
]
