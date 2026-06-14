"""Parity tests for Rust ``codex-tui::public_widgets``.

Rust source: ``codex/codex-rs/tui/src/public_widgets/mod.rs``.
"""

from pycodex.tui.public_widgets import PUBLIC_WIDGET_SUBMODULES, RUST_MODULE


def test_public_widgets_declares_composer_input_submodule() -> None:
    """Rust ``mod.rs`` only declares ``composer_input``."""

    assert RUST_MODULE.module == "public_widgets"
    assert RUST_MODULE.source == "codex/codex-rs/tui/src/public_widgets/mod.rs"
    assert PUBLIC_WIDGET_SUBMODULES == ("composer_input",)
