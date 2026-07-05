"""Terminal live-pane adapter for Rust ``codex-tui`` bottom-pane behavior.

The Rust TUI redraws a ratatui frame, while Python's real-terminal product path
keeps finalized transcript text in native scrollback.  This module is the thin
adapter between the prebuilt bottom-pane frame/buffer and that live viewport:
it clears live rows, delegates buffer drawing to ``ratatui_bridge``, places the
cursor through the bridge backend lifecycle, and leaves writer flushing to the
terminal controller or explicit clear-and-flush helper.  Bottom-pane behavior,
frame projection, buffer diffing, and terminal side-effect primitives stay in
their Rust-owned Python modules.
"""

from __future__ import annotations

import os
from typing import Callable, TextIO

from .terminal_frame import (
    TerminalBottomPaneFrame,
    bottom_pane_rows_for_size,
    terminal_bottom_pane_frame_blank_rows,
    terminal_bottom_pane_frame_cursor_position,
    terminal_bottom_pane_frame_minimum_row_widths,
)
from ..ratatui_bridge import Buffer as RatatuiBuffer
from ..ratatui_bridge import draw_buffer_to_ansi as ratatui_draw_buffer_to_ansi
from ..ratatui_bridge import requires_full_redraw as ratatui_requires_full_redraw
from ..custom_terminal import (
    flush_writer,
    prepare_live_viewport_redraw,
)


def clear_bottom_pane(writer: TextIO, size: os.terminal_size, *, live_status_active: bool) -> None:
    prepare_live_viewport_redraw(
        writer,
        bottom_pane_rows_for_size(size, live_status_active=live_status_active),
        full_redraw=True,
    )


def clear_bottom_pane_and_flush(writer: TextIO, size: os.terminal_size, *, live_status_active: bool) -> None:
    """Clear the real-terminal bottom pane and flush the terminal writer."""

    clear_bottom_pane(writer, size, live_status_active=live_status_active)
    flush_writer(writer)


def render_terminal_bottom_pane_frame(
    writer: TextIO,
    frame: TerminalBottomPaneFrame,
    *,
    buffer: RatatuiBuffer,
    previous_buffer: RatatuiBuffer | None = None,
    move_cursor: Callable[[int, int], None] | None = None,
    cursor_visible: bool = True,
    clear_external_blank_rows: bool = False,
) -> None:
    row_widths = terminal_bottom_pane_frame_minimum_row_widths(frame)
    cursor_position = (
        terminal_bottom_pane_frame_cursor_position(frame) if move_cursor is None and cursor_visible else None
    )
    full_redraw = ratatui_requires_full_redraw(previous_buffer, buffer)
    if clear_external_blank_rows and not full_redraw:
        blank_rows = terminal_bottom_pane_frame_blank_rows(frame)
        if blank_rows:
            prepare_live_viewport_redraw(writer, blank_rows, full_redraw=True)
    prepare_live_viewport_redraw(writer, frame.clear_rows, full_redraw=full_redraw)
    ratatui_draw_buffer_to_ansi(
        writer,
        buffer,
        previous=previous_buffer,
        minimum_row_widths=row_widths,
        cursor_position=cursor_position,
    )
    if move_cursor is not None and cursor_visible:
        move_cursor(frame.cursor_row, frame.cursor_column)


__all__ = [
    "clear_bottom_pane",
    "clear_bottom_pane_and_flush",
    "render_terminal_bottom_pane_frame",
]
