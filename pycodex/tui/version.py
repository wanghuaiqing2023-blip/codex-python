"""Behavior port for Rust ``codex-tui::version``.

Upstream source: ``codex/codex-rs/tui/src/version.rs``.
"""

from __future__ import annotations

from pycodex import __version__ as _pycodex_version

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="version", source="codex/codex-rs/tui/src/version.rs")

# Rust uses ``env!("CARGO_PKG_VERSION")``.  In the Python port the package
# version is the single runtime source, so the session header and /status card
# must not drift apart.
CODEX_CLI_VERSION = _pycodex_version

__all__ = [
    "CODEX_CLI_VERSION",
    "RUST_MODULE",
]
