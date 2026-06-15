"""Scroll/selection state for vertical list menus.

Port of Rust ``codex-tui::bottom_pane::scroll_state``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::scroll_state",
    source="codex/codex-rs/tui/src/bottom_pane/scroll_state.rs",
    status="complete",
)


@dataclass
class ScrollState:
    """Generic scroll/selection state for a vertical list menu."""

    selected_idx: Optional[int] = None
    scroll_top: int = 0

    @classmethod
    def new(cls) -> "ScrollState":
        return cls(selected_idx=None, scroll_top=0)

    def reset(self) -> None:
        self.selected_idx = None
        self.scroll_top = 0

    def clamp_selection(self, length: int) -> None:
        if self._clear_if_empty(length):
            return
        current = 0 if self.selected_idx is None else self.selected_idx
        self.selected_idx = min(current, length - 1)

    def move_up_wrap(self, length: int) -> None:
        if self._clear_if_empty(length):
            return
        if self.selected_idx is not None and self.selected_idx > 0:
            self.selected_idx -= 1
        elif self.selected_idx is not None:
            self.selected_idx = length - 1
        else:
            self.selected_idx = 0

    def move_down_wrap(self, length: int) -> None:
        if self._clear_if_empty(length):
            return
        if self.selected_idx is not None and self.selected_idx + 1 < length:
            self.selected_idx += 1
        else:
            self.selected_idx = 0

    def page_up_clamped(self, length: int, visible_rows: int) -> None:
        if self._clear_if_empty(length):
            return
        step = max(visible_rows, 1)
        current = min(0 if self.selected_idx is None else self.selected_idx, length - 1)
        self.selected_idx = max(current - step, 0)
        self.ensure_visible(length, visible_rows)

    def page_down_clamped(self, length: int, visible_rows: int) -> None:
        if self._clear_if_empty(length):
            return
        step = max(visible_rows, 1)
        current = min(0 if self.selected_idx is None else self.selected_idx, length - 1)
        self.selected_idx = min(current + step, length - 1)
        self.ensure_visible(length, visible_rows)

    def jump_top(self, length: int, visible_rows: int) -> None:
        if self._clear_if_empty(length):
            return
        self.selected_idx = 0
        self.ensure_visible(length, visible_rows)

    def jump_bottom(self, length: int, visible_rows: int) -> None:
        if self._clear_if_empty(length):
            return
        self.selected_idx = length - 1
        self.ensure_visible(length, visible_rows)

    def ensure_visible(self, length: int, visible_rows: int) -> None:
        if length == 0 or visible_rows == 0:
            self.scroll_top = 0
            return
        if self.selected_idx is None:
            self.scroll_top = 0
            return
        if self.selected_idx < self.scroll_top:
            self.scroll_top = self.selected_idx
            return
        bottom = self.scroll_top + visible_rows - 1
        if self.selected_idx > bottom:
            self.scroll_top = self.selected_idx + 1 - visible_rows

    def _clear_if_empty(self, length: int) -> bool:
        if length != 0:
            return False
        self.selected_idx = None
        self.scroll_top = 0
        return True

    # Compatibility alias for the scaffolded Rust private method name.
    clear_if_empty = _clear_if_empty


__all__ = [
    "RUST_MODULE",
    "ScrollState",
]

