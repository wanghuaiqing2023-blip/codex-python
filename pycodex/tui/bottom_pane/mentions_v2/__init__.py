"""Package boundary for Rust ``codex-tui::bottom_pane::mentions_v2``.

Rust source: ``codex/codex-rs/tui/src/bottom_pane/mentions_v2/mod.rs``.
This module mirrors the parent module's public re-exports while keeping the
submodule behavior contracts in their own Python files.
"""

from __future__ import annotations

from ..._porting import RustTuiModule
from .candidate import Selection as MentionV2Selection
from .popup import Popup as MentionV2Popup
from .search_catalog import build_search_catalog

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/mod.rs",
)

MENTIONS_V2_SUBMODULES = (
    "candidate",
    "filter",
    "footer",
    "popup",
    "render",
    "search_catalog",
    "search_mode",
)

__all__ = [
    "MENTIONS_V2_SUBMODULES",
    "MentionV2Popup",
    "MentionV2Selection",
    "RUST_MODULE",
    "build_search_catalog",
]
