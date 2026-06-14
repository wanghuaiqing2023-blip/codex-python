"""Shared UI constants for layout and alignment within the TUI.

Upstream source: ``codex/codex-rs/tui/src/ui_consts.rs``.
"""

from __future__ import annotations

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ui_consts",
    source="codex/codex-rs/tui/src/ui_consts.rs",
)

# Width, in terminal columns, reserved for the left gutter/prefix used by live
# cells and aligned widgets.
LIVE_PREFIX_COLS: int = 2
FOOTER_INDENT_COLS: int = LIVE_PREFIX_COLS

__all__ = [
    "FOOTER_INDENT_COLS",
    "LIVE_PREFIX_COLS",
    "RUST_MODULE",
]
