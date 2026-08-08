"""Render composition for the main chat widget surface.

Rust ``chatwidget::rendering`` composes ratatui ``Renderable`` objects.  This
Python port preserves the semantic layout and delegation contract with simple
DTOs and render logs instead of terminal buffers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any, List, Optional, Tuple

from .._porting import RustTuiModule
from ..bottom_pane.chat_composer import terminal_composer_projection
from ..bottom_pane.footer import terminal_footer_projection
from ..bottom_pane.selection_popup_common import terminal_popup_line_style, terminal_popup_lines_for_width
from ..bottom_pane.terminal_action import TerminalBottomPaneState, TerminalStyledText
from ..bottom_pane.terminal_footprint import terminal_bottom_pane_layout_rows
from ..custom_terminal import live_viewport_buffer_area_for_rows
from ..ratatui_bridge import Buffer as RatatuiBuffer
from ..ratatui_bridge import Line as RatatuiLine
from ..ratatui_bridge import Rect
from ..ratatui_bridge import Color as RatatuiColor
from ..ratatui_bridge import Modifier as RatatuiModifier
from ..ratatui_bridge import Span as RatatuiSpan
from ..ratatui_bridge import Style as RatatuiStyle
from ..terminal_hyperlinks import HyperlinkLine, line_text
from ..render.renderable import EmptyRenderable, FlexRenderable, InsetRenderable, Insets
from .status_surfaces import terminal_live_status_projection

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::rendering",
    source="codex/codex-rs/tui/src/chatwidget/rendering.rs",
    status="complete",
)


@dataclass
class RenderLog:
    entries: List[Tuple[str, Any]] = field(default_factory=list)

    def append(self, kind: str, payload: Any) -> None:
        self.entries.append((kind, payload))


@dataclass(frozen=True)
class TerminalBottomPaneFrameWrite:
    row: int
    column: int
    text: str
    selected: bool = False
    spans: tuple[RatatuiSpan, ...] = ()


@dataclass(frozen=True)
class TerminalBottomPaneFrame:
    clear_rows: tuple[int, ...]
    writes: tuple[TerminalBottomPaneFrameWrite, ...]
    cursor_row: int
    cursor_column: int


@dataclass(frozen=True)
class TerminalBottomPaneFrameProjection:
    """Rendered bottom-pane frame plus its ratatui-like buffer projection."""

    frame: TerminalBottomPaneFrame
    buffer: RatatuiBuffer


def active_history_cell_lines(cell: object | None, width: int) -> tuple[object, ...]:
    """Project a Rust ``ChatWidget::active_cell`` into live-frame rows."""

    if cell is None:
        return ()
    display = getattr(cell, "display_hyperlink_lines", None)
    if callable(display):
        return tuple(display(max(1, int(width))))
    display = getattr(cell, "display_lines", None)
    if not callable(display):
        return ()
    rows: list[str] = []
    for line in display(max(1, int(width))):
        spans = getattr(line, "spans", None)
        if spans is None:
            rows.append(str(line))
            continue
        rows.append(
            "".join(
                str(getattr(span, "content", getattr(span, "text", span)))
                for span in spans
            )
        )
    return tuple(rows)


def _ratatui_style_from_semantic(value: object) -> RatatuiStyle:
    if isinstance(value, RatatuiStyle):
        return value
    if value is None:
        return RatatuiStyle()
    if isinstance(value, str):
        tokens = {token.lower().replace("-", "_") for token in value.split()}
        named = next(
            (
                color
                for color in (
                    "black", "red", "green", "yellow", "blue", "magenta",
                    "cyan", "white", "gray", "dark_gray", "light_red",
                    "light_green", "light_yellow", "light_blue",
                    "light_magenta", "light_cyan",
                )
                if color in tokens
            ),
            None,
        )
        modifiers = {
            RatatuiModifier(token)
            for token in tokens
            if token in {item.value for item in RatatuiModifier}
        }
        return RatatuiStyle(
            fg=None if named is None else RatatuiColor.named(named),
            modifiers=frozenset(modifiers),
        )

    raw_fg = getattr(value, "fg", None)
    fg = None
    if raw_fg is not None:
        kind = getattr(raw_fg, "kind", None)
        payload = getattr(raw_fg, "value", raw_fg)
        if kind == "rgb" and payload is not None:
            fg = RatatuiColor.rgb(*payload)
        elif kind == "indexed":
            fg = RatatuiColor.indexed(int(payload))
        elif kind == "named":
            fg = RatatuiColor.named(str(payload))

    names = {
        str(getattr(item, "value", item)).lower().replace("-", "_")
        for item in (getattr(value, "modifiers", ()) or ())
    }
    for name in ("bold", "dim", "italic", "underlined", "reversed", "crossed_out"):
        attribute = getattr(value, name, False)
        if not callable(attribute) and bool(attribute):
            names.add(name)
    modifiers = frozenset(
        RatatuiModifier(name)
        for name in names
        if name in {item.value for item in RatatuiModifier}
    )
    return RatatuiStyle(fg=fg, modifiers=modifiers)


def _active_tail_frame_write(row: int, value: object) -> TerminalBottomPaneFrameWrite:
    if not isinstance(value, HyperlinkLine) and getattr(value, "line", None) is None:
        return TerminalBottomPaneFrameWrite(row, 1, str(value))
    source = value if isinstance(value, HyperlinkLine) else HyperlinkLine.new(value)
    line_style = _ratatui_style_from_semantic(source.line.style)
    spans = tuple(
        RatatuiSpan.styled(
            span.content,
            line_style.patch(_ratatui_style_from_semantic(span.style)),
        )
        for span in source.line.spans
    )
    return TerminalBottomPaneFrameWrite(
        row,
        1,
        line_text(source.line),
        spans=spans,
    )


def _footer_frame_write(
    row: int,
    line: str,
    right_text: str,
) -> TerminalBottomPaneFrameWrite:
    if not isinstance(right_text, TerminalStyledText) or not right_text.semantic_spans:
        return TerminalBottomPaneFrameWrite(row, 1, line)
    right_start = line.rfind(str(right_text))
    if right_start < 0:
        return TerminalBottomPaneFrameWrite(row, 1, line)
    spans: list[RatatuiSpan] = []
    if right_start:
        spans.append(RatatuiSpan.raw(line[:right_start]))
    spans.extend(
        RatatuiSpan.styled(content, _ratatui_style_from_semantic(style))
        for content, style in right_text.semantic_spans
    )
    return TerminalBottomPaneFrameWrite(row, 1, line, spans=tuple(spans))


def _semantic_frame_write(
    row: int,
    line: str,
    semantic_spans: tuple[tuple[str, str | None], ...],
) -> TerminalBottomPaneFrameWrite:
    if not semantic_spans:
        return TerminalBottomPaneFrameWrite(row, 1, line)
    return TerminalBottomPaneFrameWrite(
        row,
        1,
        line,
        spans=tuple(
            RatatuiSpan.styled(content, _ratatui_style_from_semantic(style))
            for content, style in semantic_spans
        ),
    )


def terminal_bottom_pane_frame(
    size: os.terminal_size,
    state: TerminalBottomPaneState,
    *,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    clear_live_status_height: int = 0,
    clear_active_tail_height: int = 0,
    clear_composer_height: int = 1,
    clear_footer_height: int = 1,
    viewport_area: object | None = None,
) -> TerminalBottomPaneFrame:
    """Build the Rust-like bottom-pane frame for the terminal adapter.

    Rust owner: ``codex-tui::chatwidget::rendering`` composes the bottom-pane
    renderable content before ``custom_terminal`` turns the frame into terminal
    side effects. This function is side-effect free; Python-only terminal
    adapters may consume the frame, but they must not own the UI semantics.
    """

    columns = size.columns
    composer_projection = state.composer_projection or terminal_composer_projection(state.draft, columns)
    layout = terminal_bottom_pane_layout_rows(
        size,
        live_status_active=state.live_status_active,
        live_status_height=state.live_status_height,
        popup_height=state.popup_height,
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
        clear_live_status_height=clear_live_status_height,
        active_tail_height=len(state.active_tail_lines),
        clear_active_tail_height=clear_active_tail_height,
        composer_height=composer_projection.height,
        clear_composer_height=clear_composer_height,
        footer_height=state.footer_height,
        supplemental_footer_height=len(state.supplemental_footer_lines),
        clear_footer_height=clear_footer_height,
        viewport_area=viewport_area,
    )

    writes: list[TerminalBottomPaneFrameWrite] = []
    live_status_projection = terminal_live_status_projection(state.live_status_text, columns)
    visible_tail = state.active_tail_lines[-len(layout.active_tail_rows) :]
    for row, line in zip(layout.active_tail_rows, visible_tail):
        writes.append(_active_tail_frame_write(row, line))
    for row, line in zip(layout.live_status_rows, live_status_projection.lines):
        writes.append(TerminalBottomPaneFrameWrite(row, 1, line))

    if not state.popup_lines:
        for row, line in zip(
            layout.supplemental_footer_rows,
            state.supplemental_footer_lines,
        ):
            semantic_spans = (
                line.semantic_spans
                if isinstance(line, TerminalStyledText)
                else ()
            )
            writes.append(_semantic_frame_write(row, str(line), semantic_spans))

    composer_semantic_spans = tuple(
        getattr(composer_projection, "line_semantic_spans", ())
    )
    for index, (row, line) in enumerate(zip(layout.composer_rows, composer_projection.lines)):
        semantic_spans = (
            composer_semantic_spans[index]
            if index < len(composer_semantic_spans)
            else ()
        )
        writes.append(_semantic_frame_write(row, line, semantic_spans))
    if state.popup_lines:
        popup_lines = terminal_popup_lines_for_width(state.popup_lines, max(1, columns - 1))
        for row, line in zip(layout.popup_rows, popup_lines):
            writes.append(
                TerminalBottomPaneFrameWrite(
                    row,
                    1,
                    line.text,
                    line.selected,
                    line.spans,
                )
            )
    footer_rows = iter(layout.footer_rows)
    if state.footer_lines and not state.popup_lines:
        for row, line in zip(footer_rows, state.footer_lines):
            semantic_spans = (
                line.semantic_spans
                if isinstance(line, TerminalStyledText)
                else ()
            )
            writes.append(_semantic_frame_write(row, str(line), semantic_spans))
    elif state.footer_text and not state.popup_lines:
        footer_line = terminal_footer_projection(
            state.footer_text,
            columns,
            state.footer_right_text,
        ).line
        writes.append(
            _footer_frame_write(
                next(footer_rows, layout.footer_row),
                footer_line,
                state.footer_right_text,
            )
        )

    cursor_row = layout.composer_rows[composer_projection.cursor_row_offset]
    cursor_column = composer_projection.cursor_column
    if state.popup_cursor is not None:
        popup_x, popup_y = state.popup_cursor
        if 0 <= popup_y < len(layout.popup_rows):
            cursor_row = layout.popup_rows[popup_y]
            cursor_column = max(1, popup_x + 1)

    return TerminalBottomPaneFrame(
        clear_rows=layout.clear_rows,
        writes=tuple(writes),
        cursor_row=cursor_row,
        cursor_column=cursor_column,
    )


def terminal_bottom_pane_frame_buffer(size: os.terminal_size, frame: TerminalBottomPaneFrame) -> RatatuiBuffer:
    """Project a bottom-pane frame into a ratatui-like buffer.

    Rust owner: ``codex-tui::chatwidget::rendering`` builds the bottom-pane
    renderable frame, while ``codex-tui::custom_terminal`` consumes the cell
    buffer for redraw. This projection is intentionally side-effect free.
    """

    area = live_viewport_buffer_area_for_rows(
        size,
        frame.clear_rows,
        fallback_rows=(write.row for write in frame.writes),
    )
    buffer = RatatuiBuffer.empty(area)
    for write in frame.writes:
        x = max(0, write.column - 1)
        y = max(0, write.row - 1)
        style = terminal_popup_line_style(selected=write.selected)
        if write.spans:
            spans = tuple(
                RatatuiSpan.styled(
                    span.content,
                    style.patch(span.style) if write.selected else span.style,
                )
                for span in write.spans
            )
            line = RatatuiLine.from_spans(spans)
        else:
            line = RatatuiLine.from_spans((RatatuiSpan.styled(write.text, style),))
        buffer.set_line(x, y, line, max_width=max(0, size.columns - x))
    return buffer


@dataclass
class BottomPaneComposerReserveRenderable:
    bottom_pane: Any
    right_reserve: int

    def render(self, area: Rect, log: RenderLog) -> None:
        self.bottom_pane.render_with_composer_right_reserve(area, log, self.right_reserve)

    def desired_height(self, width: int) -> int:
        return self.bottom_pane.desired_height_with_composer_right_reserve(width, self.right_reserve)

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return self.bottom_pane.cursor_pos_with_composer_right_reserve(area, self.right_reserve)

    def cursor_style(self, area: Rect) -> str:
        return self.bottom_pane.cursor_style_with_composer_right_reserve(area, self.right_reserve)


@dataclass
class BottomPaneTopInsetRenderable:
    child: BottomPaneComposerReserveRenderable
    top: int = 1

    def _child_area(self, area: Rect) -> Rect:
        return area.inset(Insets(top=self.top))

    def render(self, area: Rect, log: RenderLog) -> None:
        self.child.render(self._child_area(area), log)

    def desired_height(self, width: int) -> int:
        return self.child.desired_height(width)

    def cursor_pos(self, area: Rect) -> Optional[Tuple[int, int]]:
        return self.child.cursor_pos(self._child_area(area))

    def cursor_style(self, area: Rect) -> str:
        return self.child.cursor_style(self._child_area(area))


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
        BottomPaneTopInsetRenderable(
            BottomPaneComposerReserveRenderable(widget.bottom_pane, active_cell_right_reserve),
        ),
    )
    return flex


def render(widget: Any, area: Rect, log: Optional[RenderLog] = None) -> RenderLog:
    log = log or RenderLog()
    as_renderable(widget).render(area, log)
    widget.last_rendered_width = area.width
    return log


def desired_height(widget: Any, width: int) -> int:
    return as_renderable(widget).desired_height(width)


def cursor_pos(widget: Any, area: Rect) -> Optional[Tuple[int, int]]:
    reserve = widget.ambient_pet_wrap_reserved_cols()
    renderable = BottomPaneComposerReserveRenderable(widget.bottom_pane, reserve)
    return renderable.cursor_pos(area.inset(Insets(top=1)))


def cursor_style(widget: Any, area: Rect) -> str:
    reserve = widget.ambient_pet_wrap_reserved_cols()
    renderable = BottomPaneComposerReserveRenderable(widget.bottom_pane, reserve)
    return renderable.cursor_style(area.inset(Insets(top=1)))


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
    "TerminalBottomPaneFrame",
    "TerminalBottomPaneFrameProjection",
    "TerminalBottomPaneFrameWrite",
    "TranscriptAreaRenderable",
    "as_renderable",
    "cursor_pos",
    "cursor_style",
    "desired_height",
    "render",
    "terminal_bottom_pane_frame",
    "terminal_bottom_pane_frame_buffer",
]
