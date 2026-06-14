"""Parity tests for Rust ``codex-tui::bottom_pane::mentions_v2`` facade.

Rust source: ``codex/codex-rs/tui/src/bottom_pane/mentions_v2/mod.rs``.
"""

from pycodex.tui.bottom_pane import mentions_v2
from pycodex.tui.bottom_pane.mentions_v2 import candidate, popup, search_catalog


def test_mentions_v2_parent_facade_reexports_rust_items() -> None:
    """Rust ``mod.rs`` declares child modules and re-exports selection, popup, and catalog builder."""

    assert mentions_v2.RUST_MODULE.module == "bottom_pane::mentions_v2"
    assert mentions_v2.RUST_MODULE.source == "codex/codex-rs/tui/src/bottom_pane/mentions_v2/mod.rs"
    assert mentions_v2.MENTIONS_V2_SUBMODULES == (
        "candidate",
        "filter",
        "footer",
        "popup",
        "render",
        "search_catalog",
        "search_mode",
    )

    assert mentions_v2.MentionV2Selection is candidate.Selection
    assert mentions_v2.MentionV2Popup is popup.Popup
    assert mentions_v2.build_search_catalog is search_catalog.build_search_catalog
