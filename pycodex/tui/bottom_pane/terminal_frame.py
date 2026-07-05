"""Terminal bottom-pane frame model for the hybrid terminal backend.

Rust renders the bottom pane through ratatui frame/layout state.  Python keeps
ordinary terminal scrollback for history, so this module owns only the
Rust-like bottom-pane frame model consumed by the terminal repaint adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from .chat_composer import terminal_composer_line_text, terminal_composer_projection
from .footer import terminal_footer_projection
from .selection_popup_common import TerminalPopupLine as TerminalBottomPanePopupLine
from ..chatwidget.status_surfaces import TerminalLiveStatusSurface, terminal_live_status_projection
from ..custom_terminal import display_width
from ..ratatui_bridge import Buffer as RatatuiBuffer
from ..ratatui_bridge import Color as RatatuiColor
from ..ratatui_bridge import Line as RatatuiLine
from ..ratatui_bridge import Position as RatatuiPosition
from ..ratatui_bridge import Rect as RatatuiRect
from ..ratatui_bridge import Span as RatatuiSpan
from ..ratatui_bridge import Style as RatatuiStyle


IDLE_BOTTOM_PANE_ROWS = 4
STATUS_BOTTOM_PANE_ROWS = 6
SELECTED_ROW_STYLE = RatatuiStyle.default().with_fg(RatatuiColor.LightBlue)


@dataclass(frozen=True)
class TerminalBottomPaneState:
    draft: str = ""
    footer_text: str = ""
    live_status_text: str | None = None
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = ()

    @property
    def live_status_active(self) -> bool:
        return bool(self.live_status_text)

    @property
    def popup_height(self) -> int:
        return len(self.popup_lines)


@dataclass(frozen=True)
class TerminalBottomPaneFrameWrite:
    row: int
    column: int
    text: str
    selected: bool = False


@dataclass(frozen=True)
class TerminalBottomPaneFrame:
    clear_rows: tuple[int, ...]
    writes: tuple[TerminalBottomPaneFrameWrite, ...]
    cursor_row: int
    cursor_column: int


@dataclass(frozen=True)
class TerminalBottomPaneActionPlan:
    """Terminal side-effect plan for clear/render bottom-pane actions."""

    action: str
    check_resize: bool = False
    state: TerminalBottomPaneState | None = None
    live_status_active: bool = False

    @property
    def should_run(self) -> bool:
        return self.action != "skip"


@dataclass(frozen=True)
class TerminalBottomPaneFootprint:
    """Rows reserved by the live bottom pane.

    Rust ``bottom_pane`` computes desired heights from the active view and
    composer/footer state.  The real-terminal adapter keeps the same boundary
    by reporting a compact footprint value to ``app::resize_reflow``.
    """

    live_status_active: bool = False
    popup_height: int = 0

    @classmethod
    def from_surface(
        cls,
        live_status: TerminalLiveStatusSurface,
        popup_height: int = 0,
    ) -> "TerminalBottomPaneFootprint":
        return cls(
            live_status_active=live_status.footprint_active,
            popup_height=max(0, int(popup_height)),
        )

    def rows_for_size(self, size: os.terminal_size) -> list[int]:
        return bottom_pane_rows_for_size(
            size,
            live_status_active=self.live_status_active,
            popup_height=self.popup_height,
        )

    def height_for_size(self, size: os.terminal_size) -> int:
        return len(self.rows_for_size(size))


@dataclass(frozen=True)
class TerminalBottomPaneFootprintTransition:
    old_rows: tuple[int, ...]
    new_rows: tuple[int, ...]

    @property
    def changed(self) -> bool:
        return self.old_rows != self.new_rows


def bottom_pane_footprint_transition(
    size: os.terminal_size,
    previous: TerminalLiveStatusSurface,
    current: TerminalLiveStatusSurface,
    *,
    previous_popup_height: int = 0,
    current_popup_height: int = 0,
) -> TerminalBottomPaneFootprintTransition:
    previous_footprint = TerminalBottomPaneFootprint.from_surface(previous, previous_popup_height)
    current_footprint = TerminalBottomPaneFootprint.from_surface(current, current_popup_height)
    return bottom_pane_footprint_transition_for_footprints(
        size,
        previous_footprint,
        current_footprint,
    )


def bottom_pane_footprint_transition_for_footprints(
    size: os.terminal_size,
    previous: TerminalBottomPaneFootprint,
    current: TerminalBottomPaneFootprint,
) -> TerminalBottomPaneFootprintTransition:
    return TerminalBottomPaneFootprintTransition(
        old_rows=tuple(previous.rows_for_size(size)),
        new_rows=tuple(current.rows_for_size(size)),
    )


def bottom_pane_rows_for_size(
    size: os.terminal_size,
    *,
    live_status_active: bool,
    popup_height: int = 0,
) -> list[int]:
    rows = size.lines
    height = bottom_pane_height(live_status_active=live_status_active, popup_height=popup_height)
    if height != IDLE_BOTTOM_PANE_ROWS:
        return [max(1, rows - offset) for offset in range(height - 1, -1, -1)]
    return [
        max(1, rows - 3),
        max(1, rows - 2),
        max(1, rows - 1),
        max(1, rows),
    ]


def bottom_pane_height(*, live_status_active: bool, popup_height: int = 0) -> int:
    if popup_height:
        return max(
            STATUS_BOTTOM_PANE_ROWS if live_status_active else IDLE_BOTTOM_PANE_ROWS,
            (1 if live_status_active else 0) + 1 + int(popup_height) + 1,
        )
    return STATUS_BOTTOM_PANE_ROWS if live_status_active else IDLE_BOTTOM_PANE_ROWS


def history_bottom_row(
    size: os.terminal_size,
    *,
    live_status_active: bool,
    popup_height: int = 0,
    reserve_active_bottom_pane: bool = False,
) -> int:
    reserved = (
        STATUS_BOTTOM_PANE_ROWS
        if reserve_active_bottom_pane
        else bottom_pane_height(live_status_active=live_status_active, popup_height=popup_height)
    )
    return max(1, size.lines - reserved)


def terminal_bottom_pane_clear_plan(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool,
    live_status: TerminalLiveStatusSurface,
) -> TerminalBottomPaneActionPlan:
    """Plan clearing the real-terminal bottom pane."""

    if not (stdin_is_terminal and layout_active):
        return TerminalBottomPaneActionPlan(action="skip")
    return TerminalBottomPaneActionPlan(
        action="clear",
        check_resize=check_resize,
        live_status_active=live_status.footprint_active,
    )


def terminal_bottom_pane_render_plan(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool,
    draft: str,
    footer_text: str,
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = (),
    live_status: TerminalLiveStatusSurface,
) -> TerminalBottomPaneActionPlan:
    """Plan rendering the real-terminal bottom pane."""

    if not (stdin_is_terminal and layout_active):
        return TerminalBottomPaneActionPlan(action="skip")
    return TerminalBottomPaneActionPlan(
        action="render",
        check_resize=check_resize,
        state=TerminalBottomPaneState(
            draft=draft,
            footer_text=footer_text,
            live_status_text=live_status.render_text,
            popup_lines=tuple(popup_lines),
        ),
    )


def status_row(size: os.terminal_size, *, live_status_active: bool) -> int | None:
    if not live_status_active:
        return None
    return max(1, size.lines - 5)


def composer_row(size: os.terminal_size) -> int:
    return max(1, size.lines - 2)


def footer_row(size: os.terminal_size) -> int:
    return max(1, size.lines)


def composer_line_text(draft: str) -> str:
    return terminal_composer_line_text(draft)


def truncate_display_width(text: str, width: int) -> str:
    budget = max(1, int(width))
    current = 0
    out: list[str] = []
    for char in str(text):
        char_width = display_width(char)
        if current + char_width > budget:
            break
        out.append(char)
        current += char_width
    return "".join(out)


def composer_cursor_column(size: os.terminal_size, draft: str) -> int:
    return terminal_composer_projection(draft, size.columns).cursor_column


def terminal_bottom_pane_frame(
    size: os.terminal_size,
    state: TerminalBottomPaneState,
    *,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
) -> TerminalBottomPaneFrame:
    """Build the Rust-like bottom-pane frame for the terminal adapter."""

    clear_rows = tuple(
        bottom_pane_rows_for_size(
            size,
            live_status_active=state.live_status_active or clear_live_status_active,
            popup_height=max(state.popup_height, int(clear_popup_height)),
        )
    )

    columns = size.columns
    writes: list[TerminalBottomPaneFrameWrite] = []
    composer_projection = terminal_composer_projection(state.draft, columns)
    if state.popup_lines:
        rows = bottom_pane_rows_for_size(
            size,
            live_status_active=state.live_status_active,
            popup_height=state.popup_height,
        )
        cursor = 0
        live_status_projection = terminal_live_status_projection(state.live_status_text, columns)
        if state.live_status_active and live_status_projection.line:
            writes.append(TerminalBottomPaneFrameWrite(rows[cursor], 1, live_status_projection.line))
            cursor += 1
        composer = rows[cursor]
        writes.append(
            TerminalBottomPaneFrameWrite(
                composer,
                1,
                composer_projection.line,
            )
        )
        cursor += 1
        for popup_line in state.popup_lines:
            if cursor >= len(rows) - 1:
                break
            line = truncate_display_width(popup_line.text, max(1, columns - 1))
            writes.append(TerminalBottomPaneFrameWrite(rows[cursor], 1, line, popup_line.selected))
            cursor += 1
        if state.footer_text:
            writes.append(
                TerminalBottomPaneFrameWrite(
                    rows[-1],
                    1,
                    terminal_footer_projection(state.footer_text, columns).line,
                )
            )
        return TerminalBottomPaneFrame(
            clear_rows=clear_rows,
            writes=tuple(writes),
            cursor_row=composer,
            cursor_column=composer_projection.cursor_column,
        )

    status = status_row(size, live_status_active=state.live_status_active)
    live_status_projection = terminal_live_status_projection(state.live_status_text, columns)
    if status is not None and live_status_projection.line:
        writes.append(TerminalBottomPaneFrameWrite(status, 1, live_status_projection.line))

    writes.append(
        TerminalBottomPaneFrameWrite(
            composer_row(size),
            1,
            composer_projection.line,
        )
    )
    if state.footer_text:
        writes.append(
            TerminalBottomPaneFrameWrite(
                footer_row(size),
                1,
                terminal_footer_projection(state.footer_text, columns).line,
            )
        )

    return TerminalBottomPaneFrame(
        clear_rows=clear_rows,
        writes=tuple(writes),
        cursor_row=composer_row(size),
        cursor_column=composer_projection.cursor_column,
    )


def terminal_bottom_pane_frame_buffer(size: os.terminal_size, frame: TerminalBottomPaneFrame) -> RatatuiBuffer:
    """Project a bottom-pane frame into a ratatui-like buffer.

    Rust owner: ``codex-tui::chatwidget::rendering`` builds the bottom-pane
    frame, while ``codex-tui::custom_terminal`` consumes the cell buffer for
    redraw.  This projection is intentionally side-effect free.
    """

    if frame.clear_rows:
        top_row = min(frame.clear_rows)
        bottom_row = max(frame.clear_rows)
    elif frame.writes:
        top_row = min(write.row for write in frame.writes)
        bottom_row = max(write.row for write in frame.writes)
    else:
        top_row = 1
        bottom_row = 0

    height = max(0, bottom_row - top_row + 1)
    area = RatatuiRect.new(0, max(0, top_row - 1), max(0, size.columns), height)
    buffer = RatatuiBuffer.empty(area)
    for write in frame.writes:
        x = max(0, write.column - 1)
        y = max(0, write.row - 1)
        style = SELECTED_ROW_STYLE if write.selected else RatatuiStyle.default()
        line = RatatuiLine.from_spans((RatatuiSpan.styled(write.text, style),))
        buffer.set_line(x, y, line, max_width=max(0, size.columns - x))
    return buffer


def terminal_bottom_pane_frame_minimum_row_widths(frame: TerminalBottomPaneFrame) -> dict[int, int]:
    """Return per-buffer-row widths that must remain visible on full redraw.

    Rust owner: ``codex-tui::chatwidget::rendering`` owns the frame writes. The
    terminal backend needs this projection so visible trailing prompt spaces are
    preserved without making the live surface inspect frame internals.
    """

    row_widths: dict[int, int] = {}
    for write in frame.writes:
        y = max(0, write.row - 1)
        row_widths[y] = max(row_widths.get(y, 0), max(0, write.column - 1) + display_width(write.text))
    return row_widths


def terminal_bottom_pane_frame_blank_rows(frame: TerminalBottomPaneFrame) -> tuple[int, ...]:
    """Return frame rows intentionally left blank by the bottom-pane projection."""

    written_rows = {write.row for write in frame.writes}
    return tuple(row for row in frame.clear_rows if row not in written_rows)


def terminal_bottom_pane_frame_cursor_position(frame: TerminalBottomPaneFrame) -> RatatuiPosition:
    """Return the ratatui buffer cursor position for a bottom-pane frame.

    Rust owner: ``codex-tui::chatwidget::rendering`` owns composer cursor
    placement in terminal rows/columns, while ``codex-tui::custom_terminal``
    consumes a ratatui zero-based cursor position during frame draw.
    """

    return RatatuiPosition.new(max(0, frame.cursor_column - 1), max(0, frame.cursor_row - 1))


__all__ = [
    "IDLE_BOTTOM_PANE_ROWS",
    "STATUS_BOTTOM_PANE_ROWS",
    "TerminalBottomPaneActionPlan",
    "TerminalBottomPaneFootprint",
    "TerminalBottomPaneFootprintTransition",
    "TerminalBottomPaneFrame",
    "TerminalBottomPaneFrameWrite",
    "TerminalBottomPaneState",
    "SELECTED_ROW_STYLE",
    "bottom_pane_footprint_transition",
    "bottom_pane_footprint_transition_for_footprints",
    "bottom_pane_height",
    "bottom_pane_rows_for_size",
    "composer_cursor_column",
    "composer_line_text",
    "composer_row",
    "footer_row",
    "history_bottom_row",
    "status_row",
    "terminal_bottom_pane_clear_plan",
    "terminal_bottom_pane_frame",
    "terminal_bottom_pane_frame_blank_rows",
    "terminal_bottom_pane_frame_buffer",
    "terminal_bottom_pane_frame_cursor_position",
    "terminal_bottom_pane_frame_minimum_row_widths",
    "terminal_bottom_pane_render_plan",
    "truncate_display_width",
]
