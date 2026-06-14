"""Parity tests for Rust ``codex-tui::render``.

Rust source: ``codex/codex-rs/tui/src/render/mod.rs``.
"""

from pycodex.tui.render import Insets, Rect, RectExt, inset


def test_insets_constructors_match_rust_field_order() -> None:
    assert Insets.tlbr(1, 2, 3, 4) == Insets(top=1, left=2, bottom=3, right=4)
    assert Insets.vh(5, 6) == Insets(top=5, left=6, bottom=5, right=6)


def test_rect_inset_uses_saturating_dimensions() -> None:
    rect = Rect.new(10, 20, 30, 40)
    assert inset(rect, Insets.tlbr(1, 2, 3, 4)) == Rect.new(12, 21, 24, 36)
    assert inset(Rect.new(0, 0, 3, 2), Insets.tlbr(2, 2, 2, 2)) == Rect.new(2, 2, 0, 0)


def test_rect_ext_static_helper_matches_free_function() -> None:
    rect = Rect.new(3, 4, 5, 6)
    insets = Insets.vh(1, 2)
    assert RectExt.inset(rect, insets) == inset(rect, insets)
