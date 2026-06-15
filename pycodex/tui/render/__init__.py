"""Shared render geometry primitives for ``codex-tui::render``.

Rust source: ``codex/codex-rs/tui/src/render/mod.rs``.
The Rust module defines ``Insets`` plus ``RectExt::inset`` for ratatui Rects;
Python uses the semantic ``Rect`` model from ``render.renderable`` so render
submodules share one geometry contract.
"""

from __future__ import annotations

from .renderable import Rect
from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="render",
    source="codex/codex-rs/tui/src/render/mod.rs",
    status="complete",
)


class Insets:
    """Inset distances in top/left/bottom/right order, matching Rust fields."""

    __slots__ = ("top", "left", "bottom", "right")

    def __init__(self, top: int = 0, left: int = 0, bottom: int = 0, right: int = 0) -> None:
        self.top = max(0, int(top))
        self.left = max(0, int(left))
        self.bottom = max(0, int(bottom))
        self.right = max(0, int(right))

    @classmethod
    def tlbr(cls, top: int, left: int, bottom: int, right: int) -> "Insets":
        return cls(top=top, left=left, bottom=bottom, right=right)

    @classmethod
    def vh(cls, v: int, h: int) -> "Insets":
        return cls(top=v, left=h, bottom=v, right=h)

    def __iter__(self):
        yield self.top
        yield self.left
        yield self.bottom
        yield self.right

    def __eq__(self, other: object) -> bool:
        if not hasattr(other, "top"):
            return False
        return (
            self.top == getattr(other, "top")
            and self.left == getattr(other, "left")
            and self.bottom == getattr(other, "bottom")
            and self.right == getattr(other, "right")
        )

    def __repr__(self) -> str:
        return (
            f"Insets(top={self.top!r}, left={self.left!r}, "
            f"bottom={self.bottom!r}, right={self.right!r})"
        )


class RectExt:
    """Protocol-shaped helper mirroring Rust's extension trait name."""

    @staticmethod
    def inset(rect: Rect, insets: Insets) -> Rect:
        return inset(rect, insets)


def inset(rect: Rect, insets: Insets) -> Rect:
    """Return ``rect`` shrunk by ``insets`` using Rust saturating arithmetic."""
    horizontal = insets.left + insets.right
    vertical = insets.top + insets.bottom
    return Rect.new(
        rect.x + insets.left,
        rect.y + insets.top,
        max(0, rect.width - horizontal),
        max(0, rect.height - vertical),
    )


__all__ = [
    "Insets",
    "RUST_MODULE",
    "Rect",
    "RectExt",
    "inset",
]
