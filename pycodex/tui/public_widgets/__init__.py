"""Semantic package boundary for codex-rs/tui/src/public_widgets/mod.rs.

Rust declares the ``composer_input`` submodule here.  Python mirrors the package
boundary and exposes the submodule name without marking the submodule behavior
complete at this level.
"""

from __future__ import annotations

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="public_widgets",
    source="codex/codex-rs/tui/src/public_widgets/mod.rs",
    status="complete",
)

PUBLIC_WIDGET_SUBMODULES = ("composer_input",)


__all__ = [
    "PUBLIC_WIDGET_SUBMODULES",
    "RUST_MODULE",
]
