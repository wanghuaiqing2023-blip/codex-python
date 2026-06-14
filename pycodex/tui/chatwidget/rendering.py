"""Render composition for the main chat widget surface.

Rust ``chatwidget::rendering`` composes ratatui ``Renderable`` objects.  This
Python port preserves the semantic layout and delegation contract with simple
DTOs and render logs instead of terminal buffers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule
from ..ratatui_bridge import Rect
from ..render.renderable import EmptyRenderable, FlexRenderable, InsetRenderable, Insets

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::rendering", source="codex/codex-rs/tui/src/chatwidget/rendering.rs")


@dataclass
class RenderLog:
    entries: list[tuple[str, Any]] = field(default_factory=list)

    def append(self, kind: str, payload: Any) -> None:
        self.entries.append((kind, payload))


@dataclass
class BottomPaneComposerReserveRenderable:
    bottom_pane: Any
    right_reserve: int

    def render(self, area: Rect, log: RenderLog) -> None:
        self.bottom_pane.render_with_composer_right_reserve(area, log, self.right_reserve)

    def desired_height(self, width: int) -> int:
        return self.bottom_pane.desired_height_with_composer_right_reserve(width, self.right_reserve)

    def cursor_pos(self, area: Rect) -> tuple[int, int] | None:
        return self.bottom_pane.cursor_pos_with_composer_right_reserve(area, self.right_reserve)

    def cursor_style(self, area: Rect) -> str:
        return self.bottom_pane.cursor_style_with_composer_right_reserve(area, self.right_reserve)


@dataclass
class TranscriptAreaRenderable:
    child: Any
    top: int
    right: int

    def child_area(self, area: Rect) -> Rect:
        y = _saturating_add(area.y, self.top)
        height = max(area.height - self.top, 0)
        width = max(area.width - self.right, 1)
        return Rect(area.x, y, width, height)

    def render(self, area: Rect, log: RenderLog) -> None:
        child_area = self.child_area(area)
        lines = list(self.child.display_lines(child_area.width))
        line_count = len(lines)
        if child_area.height == 0:
            scroll_y = 0
        else:
            scroll_y = min(max(line_count - child_area.height, 0), 65535)
        log.append("clear", child_area)
        log.append("transcript", {"area": child_area, "lines": lines, "scroll": (scroll_y, 0)})

    def desired_height(self, width: int) -> int:
        child_width = max(width - self.right, 1)
        return int(self.child.desired_height(child_width)) + self.top


def as_renderable(widget: Any) -> FlexRenderable:
    active_cell_right_reserve = widget.ambient_pet_wrap_reserved_cols()
    active_cell = getattr(widget.transcript, "active_cell", None)
    if active_cell is not None:
        active_cell_renderable = TranscriptAreaRenderable(active_cell, top=1, right=active_cell_right_reserve)
    else:
        active_cell_renderable = EmptyRenderable()

    active_hook_cell = getattr(widget, "active_hook_cell", None)
    if active_hook_cell is not None and active_hook_cell.should_render():
        active_hook_renderable = TranscriptAreaRenderable(active_hook_cell, top=1, right=active_cell_right_reserve)
    else:
        active_hook_renderable = EmptyRenderable()

    flex = FlexRenderable()
    flex.push(1, active_cell_renderable)
    flex.push(0, active_hook_renderable)
    flex.push(
        0,
        InsetRenderable.new(
            BottomPaneComposerReserveRenderable(widget.bottom_pane, active_cell_right_reserve),
            Insets(top=1),
        ),
    )
    return flex


def render(widget: Any, area: Rect, log: RenderLog | None = None) -> RenderLog:
    log = log or RenderLog()
    as_renderable(widget).render(area, log)
    widget.last_rendered_width = area.width
    return log


def desired_height(widget: Any, width: int) -> int:
    return as_renderable(widget).desired_height(width)


def cursor_pos(widget: Any, area: Rect) -> tuple[int, int] | None:
    return as_renderable(widget).cursor_pos(area)


def cursor_style(widget: Any, area: Rect) -> str:
    return as_renderable(widget).cursor_style(area)


def _saturating_add(left: int, right: int) -> int:
    return min(left + right, 65535)


__all__ = [
    "BottomPaneComposerReserveRenderable",
    "EmptyRenderable",
    "FlexRenderable",
    "InsetRenderable",
    "RUST_MODULE",
    "Rect",
    "RenderLog",
    "TranscriptAreaRenderable",
    "as_renderable",
    "cursor_pos",
    "cursor_style",
    "desired_height",
    "render",
]
