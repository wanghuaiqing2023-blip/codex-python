"""Semantic port slice for Rust ``codex-tui::custom_terminal``.

The Rust module is a custom ratatui terminal.  Python models the tested
behavior with lightweight buffer/backend objects rather than ratatui types.
"""

from __future__ import annotations

import os
import shutil
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generic, Iterable, Mapping, Protocol, TextIO, TypeVar

from ._porting import RustTuiModule
from .ratatui_bridge.backend import (
    FrameBufferState as _BridgeFrameBufferState,
    draw_buffer_to_ansi as _bridge_draw_buffer_to_ansi,
    requires_full_redraw as _bridge_requires_full_redraw,
)
from .ratatui_bridge.buffer import Buffer as _BridgeBuffer
from .ratatui_bridge.layout import Position as _BridgePosition
from .ratatui_bridge.layout import Rect as _BridgeRect
from .ratatui_bridge.text import Span as _BridgeSpan

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="custom_terminal",
    source="codex/codex-rs/tui/src/custom_terminal.rs",
    status="complete",
)

ESC = "\x1b"
BEL = "\x07"
_ExternalRepaintResult = TypeVar("_ExternalRepaintResult")
_ProjectionRequest = TypeVar("_ProjectionRequest")


def display_width(s: str) -> int:
    text = str(s)
    if ESC not in text:
        return _visible_width(text)
    visible: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == ESC and i + 1 < len(text) and text[i + 1] == "]":
            i += 2
            while i < len(text):
                ch = text[i]
                i += 1
                if ch == BEL:
                    break
            continue
        visible.append(text[i])
        i += 1
    return _visible_width("".join(visible))


def truncate_display_width(text: str, width: int) -> str:
    """Return the prefix that fits in the requested terminal display width."""

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


def live_viewport_buffer_area_for_rows(
    size: os.terminal_size,
    rows: Iterable[int],
    *,
    fallback_rows: Iterable[int] = (),
) -> _BridgeRect:
    """Return the ratatui buffer area that covers live viewport terminal rows."""

    selected_rows = tuple(int(row) for row in rows) or tuple(int(row) for row in fallback_rows)
    if not selected_rows:
        return _BridgeRect.new(0, 0, max(0, int(size.columns)), 0)
    top_row = min(selected_rows)
    bottom_row = max(selected_rows)
    return _BridgeRect.new(
        0,
        max(0, top_row - 1),
        max(0, int(size.columns)),
        max(0, bottom_row - top_row + 1),
    )


class LiveViewportWriteProtocol(Protocol):
    """Terminal-row write shape consumed by live-viewport metadata helpers."""

    row: int
    column: int
    text: str


def live_viewport_minimum_row_widths_for_writes(writes: Iterable[LiveViewportWriteProtocol]) -> dict[int, int]:
    """Return per-buffer-row widths that should stay visible on redraw."""

    row_widths: dict[int, int] = {}
    for write in writes:
        row = int(write.row)
        column = int(write.column)
        text = str(write.text)
        y = max(0, row - 1)
        row_widths[y] = max(row_widths.get(y, 0), max(0, column - 1) + display_width(text))
    return row_widths


def live_viewport_blank_rows(clear_rows: Iterable[int], writes: Iterable[LiveViewportWriteProtocol]) -> tuple[int, ...]:
    """Return one-based live viewport rows intentionally left blank."""

    written_rows = {int(write.row) for write in writes}
    return tuple(int(row) for row in clear_rows if int(row) not in written_rows)


def live_viewport_cursor_position(row: int, column: int) -> _BridgePosition:
    """Return the zero-based ratatui cursor position for terminal coordinates."""

    return _BridgePosition.new(max(0, int(column) - 1), max(0, int(row) - 1))


def move_cursor(writer: TextIO, row: int, column: int = 1) -> None:
    writer.write(f"{ESC}[{row};{column}H")


def hide_cursor_ansi(writer: TextIO) -> None:
    """Hide the visible terminal cursor through the ANSI backend primitive."""

    writer.write(f"{ESC}[?25l")


def show_cursor_ansi(writer: TextIO) -> None:
    """Show the visible terminal cursor through the ANSI backend primitive."""

    writer.write(f"{ESC}[?25h")


def set_cursor_style_ansi(writer: TextIO, style: str) -> None:
    """Set the visible terminal cursor style through the ANSI backend primitive."""

    writer.write(_cursor_style_sequence(style))


def reset_cursor_style_ansi(writer: TextIO) -> None:
    """Restore the user-configured terminal cursor style."""

    set_cursor_style_ansi(writer, "DefaultUserShape")


def write_at(writer: TextIO, row: int, column: int, text: str) -> None:
    move_cursor(writer, row, column)
    writer.write(text)


def clear_line_at(writer: TextIO, row: int) -> None:
    move_cursor(writer, row, 1)
    writer.write(f"{ESC}[2K")


def clear_lines_at(writer: TextIO, rows: Iterable[int], *, reset_region: bool = True) -> None:
    """Clear terminal rows after resetting the scroll region.

    Rust owner: ``codex-tui::custom_terminal`` owns viewport clearing and
    invalidation side effects.  Python's hybrid bottom pane passes the chosen
    live rows here instead of spelling out terminal row-clearing loops.
    """

    if reset_region:
        reset_scroll_region(writer)
    for row in rows:
        clear_line_at(writer, int(row))


def prepare_live_viewport_redraw(writer: TextIO, rows: Iterable[int], *, full_redraw: bool) -> None:
    """Prepare a hybrid live viewport before drawing a ratatui-like buffer.

    Rust owner: ``codex-tui::custom_terminal`` owns scroll-region reset and
    live viewport clearing side effects.  Product-path adapters decide which
    rows belong to the live viewport, but they should not duplicate this
    reset/clear ordering.
    """

    reset_scroll_region(writer)
    if full_redraw:
        clear_lines_at(writer, rows, reset_region=False)


def clear_live_viewport(writer: TextIO, rows: Iterable[int]) -> None:
    """Clear live viewport rows through the custom-terminal boundary."""

    prepare_live_viewport_redraw(writer, rows, full_redraw=True)


@dataclass(frozen=True)
class LiveViewportClearRequest:
    """Generic clear request for the hybrid live viewport."""

    rows: tuple[int, ...]

    @classmethod
    def new(cls, rows: Iterable[int]) -> "LiveViewportClearRequest":
        return cls(tuple(int(row) for row in rows))


def clear_live_viewport_request(writer: TextIO, request: LiveViewportClearRequest) -> None:
    """Clear live viewport rows from a prepared request."""

    clear_live_viewport(writer, request.rows)


def live_viewport_requires_full_redraw(previous_buffer: _BridgeBuffer | None, buffer: _BridgeBuffer) -> bool:
    """Return whether the hybrid live viewport should ignore diff rendering.

    Rust's ratatui/crossterm backend owns wide-cell invalidation inside the
    terminal backend.  Python keeps ordinary terminal scrollback and writes ANSI
    directly, so ``custom_terminal`` must conservatively invalidate changed
    live-pane rows that contain wide cells.
    """

    if _bridge_requires_full_redraw(previous_buffer, buffer):
        return True
    if previous_buffer is None:
        return True
    return _live_viewport_changed_rows_contain_wide_cells(previous_buffer, buffer)


def _live_viewport_changed_rows_contain_wide_cells(previous_buffer: _BridgeBuffer, buffer: _BridgeBuffer) -> bool:
    if previous_buffer.area != buffer.area:
        return True

    for y in range(buffer.area.y, buffer.area.bottom()):
        row_changed = False
        row_contains_wide_cell = False
        for x in range(buffer.area.x, buffer.area.right()):
            previous_cell = previous_buffer.cell(x, y)
            current_cell = buffer.cell(x, y)
            row_changed = row_changed or previous_cell != current_cell
            row_contains_wide_cell = (
                row_contains_wide_cell
                or previous_cell.skip
                or current_cell.skip
                or display_width(previous_cell.symbol) > 1
                or display_width(current_cell.symbol) > 1
            )
        if row_changed and row_contains_wide_cell:
            return True
    return False


def render_live_viewport_buffer(
    writer: TextIO,
    *,
    clear_rows: Iterable[int],
    buffer: _BridgeBuffer,
    previous_buffer: _BridgeBuffer | None = None,
    minimum_row_widths: Mapping[int, int] | None = None,
    cursor_position: _BridgePosition | None = None,
    external_blank_rows: Iterable[int] = (),
) -> None:
    """Render a ratatui-like buffer into the hybrid live viewport.

    Rust owner: ``codex-tui::custom_terminal`` owns previous/current buffer
    compatibility, full redraw decisions, live viewport clearing, and backend
    draw handoff.  Python adapters may compute which rows belong to a frame,
    but they must not duplicate the redraw policy.
    """

    full_redraw = live_viewport_requires_full_redraw(previous_buffer, buffer)
    blank_rows = tuple(int(row) for row in external_blank_rows)
    if blank_rows and not full_redraw:
        clear_live_viewport(writer, blank_rows)
    prepare_live_viewport_redraw(writer, clear_rows, full_redraw=full_redraw)
    _bridge_draw_buffer_to_ansi(
        writer,
        buffer,
        previous=None if full_redraw else previous_buffer,
        minimum_row_widths=minimum_row_widths,
        cursor_position=cursor_position,
    )


@dataclass(frozen=True)
class LiveViewportRenderRequest:
    """Generic render request for the hybrid live viewport.

    Rust owner: ``codex-tui::custom_terminal`` consumes a frame buffer plus
    cursor/row metadata during draw.  Bottom-pane modules may create this
    request from their frame model, but the terminal surface should pass the
    request through instead of unpacking frame geometry itself.
    """

    clear_rows: tuple[int, ...]
    buffer: _BridgeBuffer
    minimum_row_widths: Mapping[int, int] | None = None
    cursor_position: _BridgePosition | None = None
    external_blank_rows: tuple[int, ...] = ()

    @classmethod
    def new(
        cls,
        *,
        clear_rows: Iterable[int],
        buffer: _BridgeBuffer,
        minimum_row_widths: Mapping[int, int] | None = None,
        cursor_position: _BridgePosition | None = None,
        external_blank_rows: Iterable[int] = (),
    ) -> "LiveViewportRenderRequest":
        return cls(
            clear_rows=tuple(int(row) for row in clear_rows),
            buffer=buffer,
            minimum_row_widths=minimum_row_widths,
            cursor_position=cursor_position,
            external_blank_rows=tuple(int(row) for row in external_blank_rows),
        )

    @classmethod
    def from_writes(
        cls,
        *,
        clear_rows: Iterable[int],
        buffer: _BridgeBuffer,
        writes: Iterable[LiveViewportWriteProtocol],
        cursor_row: int,
        cursor_column: int,
        include_cursor_position: bool = True,
        clear_external_blank_rows: bool = False,
    ) -> "LiveViewportRenderRequest":
        """Build a render request from terminal-row write metadata.

        Rust owner: ``codex-tui::custom_terminal`` owns the backend metadata
        consumed during live-viewport drawing. Bottom-pane projection adapters
        should pass their frame writes here instead of composing row widths,
        blank rows, and ratatui cursor positions locally.
        """

        clear_rows_tuple = tuple(int(row) for row in clear_rows)
        writes_tuple = tuple(writes)
        return cls.new(
            clear_rows=clear_rows_tuple,
            buffer=buffer,
            minimum_row_widths=live_viewport_minimum_row_widths_for_writes(writes_tuple),
            cursor_position=live_viewport_cursor_position(cursor_row, cursor_column)
            if include_cursor_position
            else None,
            external_blank_rows=live_viewport_blank_rows(clear_rows_tuple, writes_tuple)
            if clear_external_blank_rows
            else (),
        )


@dataclass(frozen=True)
class LiveViewportUpdate:
    """Generic update for the hybrid live viewport."""

    kind: str
    clear_request: LiveViewportClearRequest | None = None
    render_request: LiveViewportRenderRequest | None = None
    flush: bool = False

    @classmethod
    def clear(
        cls,
        request: LiveViewportClearRequest,
        *,
        flush: bool = False,
    ) -> "LiveViewportUpdate":
        return cls(kind="clear", clear_request=request, flush=bool(flush))

    @classmethod
    def render(
        cls,
        request: LiveViewportRenderRequest,
        *,
        flush: bool = False,
    ) -> "LiveViewportUpdate":
        return cls(kind="render", render_request=request, flush=bool(flush))


@dataclass(frozen=True)
class LiveViewportProjectionPolicy:
    """Custom-terminal policy inputs for a live-viewport projection factory."""

    cursor_visible: bool = True
    external_cursor_move: bool = False


@dataclass(frozen=True)
class LiveViewportProjection:
    """Generic live-viewport projection produced by product adapters.

    Rust owner: ``codex-tui::custom_terminal`` owns the backend-facing live
    update envelope. Bottom-pane adapters may provide cursor target metadata,
    but they should return this generic custom-terminal projection rather than
    inventing view-specific wrappers.
    """

    update: LiveViewportUpdate
    cursor_move: "LiveViewportCursorMove | None" = None


@dataclass(frozen=True)
class LiveViewportCursorMove:
    """One-based terminal cursor target consumed by custom-terminal callbacks."""

    row: int
    column: int


class LiveViewportCursorMoveCallback(Protocol):
    """Compatibility cursor movement callback consumed by custom_terminal."""

    def __call__(self, row: int, column: int) -> None: ...


@dataclass(frozen=True)
class LiveViewportProjectionCycle:
    """Prepared live-viewport projection lifecycle inputs.

    Rust owner: ``codex-tui::custom_terminal`` owns the live viewport draw
    lifecycle. Product adapters may supply a projection callback, but the
    lifecycle fields themselves are generic custom-terminal inputs.
    """

    project: Callable[[os.terminal_size, LiveViewportProjectionPolicy], LiveViewportProjection | None]
    should_run: bool
    check_resize: bool
    cursor_visible: bool | None = None


def render_live_viewport_request(
    writer: TextIO,
    request: LiveViewportRenderRequest,
    *,
    previous_buffer: _BridgeBuffer | None = None,
) -> None:
    """Render a prepared live-viewport request through the backend."""

    render_live_viewport_buffer(
        writer,
        clear_rows=request.clear_rows,
        buffer=request.buffer,
        previous_buffer=previous_buffer,
        minimum_row_widths=request.minimum_row_widths,
        cursor_position=request.cursor_position,
        external_blank_rows=request.external_blank_rows,
    )


def apply_live_viewport_update(
    writer: TextIO,
    update: LiveViewportUpdate,
    *,
    live_viewport: "LiveViewportRenderer | None" = None,
    previous_buffer: _BridgeBuffer | None = None,
) -> None:
    """Apply a generic live-viewport update and its flush policy."""

    if update.kind == "clear" and update.clear_request is not None:
        if live_viewport is not None:
            live_viewport.clear_request(update.clear_request)
        else:
            clear_live_viewport_request(writer, update.clear_request)
    elif update.kind == "render" and update.render_request is not None:
        if live_viewport is not None:
            live_viewport.render_request(update.render_request)
        else:
            render_live_viewport_request(
                writer,
                update.render_request,
                previous_buffer=previous_buffer,
            )
    if update.flush:
        flush_live_viewport(writer, live_viewport=live_viewport)


def apply_live_viewport_cursor_move(
    move_cursor: LiveViewportCursorMoveCallback | None,
    cursor_move: LiveViewportCursorMove | None,
    *,
    cursor_visible: bool = True,
) -> bool:
    """Apply an optional one-based terminal cursor move.

    Rust owner: ``codex-tui::custom_terminal`` owns terminal cursor movement
    side effects after a frame draw.  Bottom-pane frame owners may project the
    target row/column, but terminal adapters should not inspect that projection
    or branch on cursor visibility themselves.
    """

    if move_cursor is None or not cursor_visible or cursor_move is None:
        return False
    move_cursor(int(cursor_move.row), int(cursor_move.column))
    return True


def live_viewport_backend_cursor_position_enabled(
    *,
    external_cursor_move: bool = False,
    cursor_visible: bool = True,
) -> bool:
    """Return whether backend rendering should carry a frame cursor.

    Rust owner: ``codex-tui::custom_terminal`` consumes the frame cursor during
    backend draw, while Python's hybrid path may also receive a compatibility
    cursor callback.  Product adapters should pass the policy inputs through
    this custom-terminal boundary rather than duplicating the expression.
    """

    return bool(cursor_visible and not external_cursor_move)


def apply_live_viewport_update_with_cursor_move(
    writer: TextIO,
    update: LiveViewportUpdate,
    *,
    live_viewport: "LiveViewportRenderer | None" = None,
    previous_buffer: _BridgeBuffer | None = None,
    move_cursor: LiveViewportCursorMoveCallback | None = None,
    cursor_move: LiveViewportCursorMove | None = None,
    cursor_visible: bool = True,
) -> bool:
    """Apply a live-viewport update plus its optional cursor callback."""

    apply_live_viewport_update(
        writer,
        update,
        live_viewport=live_viewport,
        previous_buffer=previous_buffer,
    )
    return apply_live_viewport_cursor_move(
        move_cursor,
        cursor_move,
        cursor_visible=cursor_visible,
    )


def apply_live_viewport_projection(
    writer: TextIO,
    projection: LiveViewportProjection | None,
    *,
    live_viewport: "LiveViewportRenderer | None" = None,
    previous_buffer: _BridgeBuffer | None = None,
    move_cursor: LiveViewportCursorMoveCallback | None = None,
    cursor_visible: bool = True,
) -> bool:
    """Apply a generic live-viewport projection.

    Rust owner: ``codex-tui::custom_terminal`` owns applying prepared live
    viewport updates and cursor side effects. Bottom-pane frame owners may
    return a projection object with update/cursor data, but terminal adapters
    should not unpack that projection themselves.
    """

    if projection is None:
        return False
    apply_live_viewport_update_with_cursor_move(
        writer,
        projection.update,
        live_viewport=live_viewport,
        previous_buffer=previous_buffer,
        move_cursor=move_cursor,
        cursor_move=projection.cursor_move,
        cursor_visible=cursor_visible,
    )
    return True


def sync_live_viewport_cursor_visibility(
    live_viewport: "LiveViewportRenderer | None",
    *,
    visible: bool,
    active: bool = True,
) -> bool:
    """Synchronize live-viewport cursor visibility through its owner boundary.

    Rust owner: ``codex-tui::custom_terminal`` owns terminal cursor visibility
    side effects. Controllers may compute the desired policy, but the actual
    hide/show synchronization should run through this boundary.
    """

    if live_viewport is None:
        return False
    return live_viewport.sync_cursor_visibility(visible, active=active)


def flush_writer(writer: TextIO) -> None:
    """Flush a terminal writer when it exposes a flush method."""

    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


def flush_live_viewport(writer: TextIO, *, live_viewport: "LiveViewportRenderer | None" = None) -> None:
    """Flush output through the custom-terminal live-viewport boundary.

    Rust owner: ``codex-tui::custom_terminal`` owns backend flush timing after
    frame redraw side effects.  Product-path adapters can pass a
    ``LiveViewportRenderer`` when one owns the writer; fallback callers still
    use the same owner API instead of reaching for raw writer details.
    """

    if live_viewport is not None:
        live_viewport.flush()
        return
    flush_writer(writer)


def check_live_viewport_resize(
    *,
    check_resize: bool,
    resize: Callable[[], None],
    live_viewport: "LiveViewportRenderer | None" = None,
) -> bool:
    """Run resize lifecycle through the live viewport when requested.

    Rust owner: ``codex-tui::custom_terminal`` owns frame-buffer invalidation
    when terminal geometry or viewport state changes. Terminal adapters should
    call this boundary instead of duplicating resize/reset branching.
    """

    if not check_resize:
        return False
    if live_viewport is not None:
        live_viewport.check_resize(resize)
    else:
        resize()
    return True


def run_live_viewport_update_cycle(
    *,
    check_resize: bool,
    resize: Callable[[], None],
    terminal_size: Callable[[], os.terminal_size],
    apply_update: Callable[[os.terminal_size], bool],
    live_viewport: "LiveViewportRenderer | None" = None,
    cursor_visible: bool | None = None,
) -> bool:
    """Run the live-viewport resize, sizing, and update lifecycle.

    Rust owner: ``codex-tui::custom_terminal`` owns resize-triggered frame
    invalidation and cursor visibility before drawing a new frame. Terminal
    adapters should provide the prepared draw callback and desired cursor
    policy, but they should not duplicate the ordering of cursor sync, resize,
    terminal-size lookup, and live-viewport update application.
    """

    if cursor_visible is not None:
        sync_live_viewport_cursor_visibility(
            live_viewport,
            visible=cursor_visible,
            active=True,
        )
    check_live_viewport_resize(
        check_resize=check_resize,
        resize=resize,
        live_viewport=live_viewport,
    )
    return bool(apply_update(terminal_size()))


def run_live_viewport_projection_cycle(
    writer: TextIO,
    *,
    should_run: bool,
    check_resize: bool,
    resize: Callable[[], None],
    terminal_size: Callable[[], os.terminal_size],
    projection: Callable[[os.terminal_size, LiveViewportProjectionPolicy], LiveViewportProjection | None],
    live_viewport: "LiveViewportRenderer | None" = None,
    cursor_visible: bool | None = None,
    move_cursor: LiveViewportCursorMoveCallback | None = None,
) -> bool:
    """Run a prepared live-viewport projection lifecycle.

    Rust owner: ``codex-tui::custom_terminal`` owns the lifecycle around live
    viewport drawing: cursor visibility, resize invalidation, terminal sizing,
    projection application, optional cursor movement, and flush policy. Product
    adapters should supply only the owner-specific projection factory and the
    gating values computed by their module owner.
    """

    if not should_run:
        return False
    policy = LiveViewportProjectionPolicy(
        cursor_visible=True if cursor_visible is None else cursor_visible,
        external_cursor_move=move_cursor is not None,
    )
    return bool(
        run_live_viewport_update_cycle(
            check_resize=check_resize,
            resize=resize,
            terminal_size=terminal_size,
            live_viewport=live_viewport,
            cursor_visible=cursor_visible,
            apply_update=lambda size: apply_live_viewport_projection(
                writer,
                projection(size, policy),
                live_viewport=live_viewport,
                move_cursor=move_cursor,
                cursor_visible=policy.cursor_visible,
            ),
        )
    )


def run_prepared_live_viewport_projection_cycle(
    writer: TextIO,
    cycle: LiveViewportProjectionCycle,
    *,
    resize: Callable[[], None],
    terminal_size: Callable[[], os.terminal_size],
    live_viewport: "LiveViewportRenderer | None" = None,
    move_cursor: LiveViewportCursorMoveCallback | None = None,
) -> bool:
    """Run a prepared projection-cycle object through the live viewport.

    Rust owner: ``codex-tui::custom_terminal`` owns the draw lifecycle and
    cursor/resize sequencing. Python-only product adapters may prepare a small
    typed cycle object with owner-specific gating and projection behavior, but
    they should not unpack that object into lifecycle arguments themselves.
    """

    return run_live_viewport_projection_cycle(
        writer,
        should_run=cycle.should_run,
        check_resize=cycle.check_resize,
        resize=resize,
        terminal_size=terminal_size,
        live_viewport=live_viewport,
        cursor_visible=cycle.cursor_visible,
        move_cursor=move_cursor,
        projection=cycle.project,
    )


@dataclass
class LiveViewportProjectionCycleRunner:
    """Stateful runner for prepared live-viewport projection cycles.

    Rust owner: ``codex-tui::custom_terminal`` owns the terminal writer,
    previous/current frame buffers, resize invalidation, cursor restoration,
    and external repaint lifecycle. Product adapters should hand prepared
    projection cycles to this owner boundary rather than storing
    ``LiveViewportRenderer`` or terminal callbacks themselves.
    """

    writer: TextIO
    terminal_size: Callable[[], os.terminal_size]
    resize: Callable[[], None]
    live_viewport: "LiveViewportRenderer"

    def run(
        self,
        cycle: LiveViewportProjectionCycle,
        *,
        move_cursor: LiveViewportCursorMoveCallback | None = None,
    ) -> bool:
        return run_prepared_live_viewport_projection_cycle(
            self.writer,
            cycle,
            resize=self.resize,
            terminal_size=self.terminal_size,
            live_viewport=self.live_viewport,
            move_cursor=move_cursor,
        )

    def restore_cursor(self) -> bool:
        return self.live_viewport.restore_cursor()

    def run_external_repaint(
        self,
        repaint: Callable[[], _ExternalRepaintResult],
    ) -> _ExternalRepaintResult:
        return self.live_viewport.run_external_repaint(repaint)


@dataclass
class LiveViewportProjectionRequestRunner(Generic[_ProjectionRequest]):
    """Stateful runner for request objects that project into viewport cycles.

    Rust owner: ``codex-tui::custom_terminal`` owns live-viewport lifecycle
    execution. Product adapters may define their own request and projection
    types, but they should hand the lifecycle work to this owner boundary
    instead of reimplementing run/restore/external-repaint plumbing.
    """

    cycle_runner: LiveViewportProjectionCycleRunner
    project: Callable[[_ProjectionRequest], LiveViewportProjectionCycle]

    def terminal_size(self) -> os.terminal_size:
        return self.cycle_runner.terminal_size()

    def run(
        self,
        request: _ProjectionRequest,
        *,
        move_cursor: LiveViewportCursorMoveCallback | None = None,
    ) -> bool:
        return self.cycle_runner.run(self.project(request), move_cursor=move_cursor)

    def restore_cursor(self) -> bool:
        return self.cycle_runner.restore_cursor()

    def run_external_repaint(
        self,
        repaint: Callable[[], _ExternalRepaintResult],
    ) -> _ExternalRepaintResult:
        return self.cycle_runner.run_external_repaint(repaint)


def create_live_viewport_projection_cycle_runner(
    writer: TextIO,
    *,
    terminal_size: Callable[[], os.terminal_size],
    resize: Callable[[], None],
) -> LiveViewportProjectionCycleRunner:
    """Create the owner-managed projection cycle runner for a writer."""

    return LiveViewportProjectionCycleRunner(
        writer=writer,
        terminal_size=terminal_size,
        resize=resize,
        live_viewport=create_live_viewport_renderer(writer),
    )


def create_live_viewport_projection_request_runner(
    writer: TextIO,
    *,
    terminal_size: Callable[[], os.terminal_size],
    resize: Callable[[], None],
    project: Callable[[_ProjectionRequest], LiveViewportProjectionCycle],
) -> LiveViewportProjectionRequestRunner[_ProjectionRequest]:
    """Create an owner-managed request runner for projected viewport cycles."""

    return LiveViewportProjectionRequestRunner(
        cycle_runner=create_live_viewport_projection_cycle_runner(
            writer,
            terminal_size=terminal_size,
            resize=resize,
        ),
        project=project,
    )


def write_inline_status_line(writer: TextIO, text: str) -> None:
    """Overwrite the current terminal line with transient status text."""

    writer.write(f"\r{ESC}[2K{text}")


def clear_inline_status_line(writer: TextIO) -> None:
    """Clear the current transient status line without touching scrollback."""

    writer.write(f"\r{ESC}[2K")


def set_scroll_region(writer: TextIO, top: int, bottom: int) -> None:
    writer.write(f"{ESC}[{top};{bottom}r")


def reset_scroll_region(writer: TextIO) -> None:
    writer.write(f"{ESC}[r")


def enable_bracketed_paste(writer: TextIO) -> None:
    """Enable Rust/crossterm-style bracketed paste reporting."""

    writer.write(f"{ESC}[?2004h")
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


def disable_bracketed_paste(writer: TextIO) -> None:
    """Restore host-terminal paste handling on TUI shutdown."""

    writer.write(f"{ESC}[?2004l")
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


def enter_alternate_screen(writer: TextIO) -> None:
    """Enter Rust's transcript-overlay terminal mode."""

    reset_scroll_region(writer)
    writer.write(f"{ESC}[?1049h{ESC}[?1007h{ESC}[2J{ESC}[H{ESC}[?25l")
    flush_writer(writer)


def leave_alternate_screen(writer: TextIO) -> None:
    """Leave Rust's transcript-overlay terminal mode and restore the cursor."""

    writer.write(f"{ESC}[?1007l{ESC}[?1049l{ESC}[?25h")
    flush_writer(writer)


@dataclass
class AlternateScreenRenderer:
    """Full-viewport Frame/Buffer renderer used by pager overlays.

    Rust owner: ``codex-tui::custom_terminal``. The overlay owns content and
    navigation; this backend owns alternate-screen entry, previous/current
    buffers, ANSI diff flushing, and terminal restoration.
    """

    writer: TextIO
    _buffer_state: _BridgeFrameBufferState = field(default_factory=_BridgeFrameBufferState)
    active: bool = False

    def enter(self) -> None:
        if self.active:
            return
        enter_alternate_screen(self.writer)
        self._buffer_state.reset()
        self.active = True

    def render_lines(self, lines: Iterable[str], size: os.terminal_size) -> None:
        width = max(0, int(size.columns))
        height = max(0, int(size.lines))
        area = _BridgeRect.new(0, 0, width, height)
        buffer = _BridgeBuffer.empty(area)
        for y, line in enumerate(tuple(lines)[:height]):
            buffer.set_span(0, y, _BridgeSpan(str(line)), width)
        previous = self._buffer_state.previous
        full_redraw = live_viewport_requires_full_redraw(previous, buffer)
        if previous is not None and full_redraw:
            previous = None
            self.writer.write(f"{ESC}[H{ESC}[2J")
        _bridge_draw_buffer_to_ansi(self.writer, buffer, previous=previous)
        self._buffer_state.update(buffer)
        flush_writer(self.writer)

    def leave(self) -> None:
        if not self.active:
            return
        try:
            leave_alternate_screen(self.writer)
        finally:
            self._buffer_state.reset()
            self.active = False


@dataclass(frozen=True)
class TerminalScrollRegionResetter:
    """Runtime-bound scroll-region reset callback for terminal lifecycle owners."""

    writer: TextIO

    def reset(self) -> None:
        reset_scroll_region(self.writer)


def clear_scrollback_and_visible_screen_ansi(writer: TextIO) -> None:
    """Clear scrollback and visible screen like Rust ``custom_terminal``."""

    reset_scroll_region(writer)
    writer.write(f"{ESC}[0m{ESC}[H{ESC}[2J{ESC}[3J{ESC}[H")


def terminal_viewport_clear_should_run(*, width: int, height: int) -> bool:
    """Return whether Rust ``Terminal::clear`` should touch the viewport.

    Rust owner: ``codex-tui::custom_terminal::Terminal::clear`` returns early
    when the viewport area is empty. Python adapters should ask this helper
    for the state transition instead of retaining a local fake ``Terminal``.
    """

    return int(width) > 0 and int(height) > 0


def terminal_visible_history_rows_after_viewport_change(
    visible_history_rows: int,
    *,
    viewport_top: int,
) -> int:
    """Apply Rust ``set_viewport_area`` visible-history row capping."""

    return min(max(0, int(visible_history_rows)), max(0, int(viewport_top)))


def terminal_visible_history_rows_after_insert(
    visible_history_rows: int,
    inserted_rows: int,
    *,
    viewport_top: int,
) -> int:
    """Apply Rust ``note_history_rows_inserted`` saturating row accounting."""

    return min(
        max(0, int(visible_history_rows)) + max(0, int(inserted_rows)),
        max(0, int(viewport_top)),
    )


def terminal_visible_history_rows_after_clear() -> int:
    """Return Rust ``clear_visible_screen`` / hard-clear history state."""

    return 0


def terminal_clear_scrollback_cursor_position() -> _BridgePosition:
    """Return the cursor position after Rust hard clear completes."""

    return _BridgePosition.new(0, 0)


def terminal_size(default: tuple[int, int] = (80, 24)) -> os.terminal_size:
    """Return the current terminal size using the product-path fallback."""

    return shutil.get_terminal_size(default)


@dataclass(frozen=True)
class TerminalColumnProvider:
    """Runtime-bound terminal column provider for width-sensitive owners.

    Rust owner: ``codex-tui::custom_terminal`` exposes terminal sizing through
    the backend. Runtime glue should pass this bound callback to history and
    resize owners instead of rebuilding ``terminal_size().columns`` lambdas.
    """

    current_size: Callable[[], os.terminal_size] = terminal_size

    def columns(self) -> int:
        return int(self.current_size().columns)


@dataclass
class LiveViewportBufferState:
    """Previous-buffer state for hybrid live-viewport redraws.

    Rust owner: ``codex-tui::custom_terminal`` owns current/previous frame
    buffers and invalidates the previous buffer after external terminal side
    effects.  Python's bottom-pane controller should depend on this
    custom-terminal boundary instead of reaching into the ratatui bridge for
    product-path state ownership.
    """

    _state: _BridgeFrameBufferState = field(default_factory=_BridgeFrameBufferState)

    @property
    def previous(self) -> _BridgeBuffer | None:
        return self._state.previous

    def reset(self) -> None:
        self._state.reset()

    def update(self, buffer: _BridgeBuffer) -> None:
        self._state.update(buffer)


@dataclass
class LiveViewportRenderer:
    """Stateful renderer for the hybrid live viewport.

    Rust owner: ``codex-tui::custom_terminal`` owns current/previous frame
    buffers, invalidation, and backend flush boundaries.  Python bottom-pane
    adapters may provide frame geometry, but they should not directly manage
    previous-buffer state.
    """

    writer: TextIO
    _buffer_state: LiveViewportBufferState = field(default_factory=LiveViewportBufferState)
    _cursor_visible: bool = True

    def _reset_buffer_state(self) -> None:
        self._buffer_state.reset()

    def check_resize(self, resize: Callable[[], None]) -> None:
        """Run a resize check and invalidate previous frame state.

        Rust owner: ``codex-tui::custom_terminal`` owns frame-buffer
        invalidation when terminal geometry or external viewport state changes.
        Bottom-pane adapters should ask the live viewport to perform this
        lifecycle step instead of calling raw buffer resets around resize
        callbacks themselves.
        """

        resize()
        self._reset_buffer_state()

    def run_external_repaint(self, repaint: Callable[[], _ExternalRepaintResult]) -> _ExternalRepaintResult:
        """Run an external repaint while invalidating live-viewport buffers.

        Rust owner: ``codex-tui::custom_terminal`` owns frame-buffer
        invalidation around terminal side effects that may dirty the live
        viewport. Bottom-pane controllers should not bracket repaint callbacks
        with raw buffer reset calls.
        """

        self._reset_buffer_state()
        try:
            return repaint()
        finally:
            self._reset_buffer_state()

    def clear_rows(self, rows: Iterable[int]) -> None:
        clear_live_viewport(self.writer, rows)
        self._reset_buffer_state()

    def clear_request(self, request: LiveViewportClearRequest) -> None:
        clear_live_viewport_request(self.writer, request)
        self._reset_buffer_state()

    def render_buffer(
        self,
        *,
        clear_rows: Iterable[int],
        buffer: _BridgeBuffer,
        minimum_row_widths: Mapping[int, int] | None = None,
        cursor_position: _BridgePosition | None = None,
        external_blank_rows: Iterable[int] = (),
    ) -> None:
        render_live_viewport_buffer(
            self.writer,
            clear_rows=clear_rows,
            buffer=buffer,
            previous_buffer=self._buffer_state.previous,
            minimum_row_widths=minimum_row_widths,
            cursor_position=cursor_position,
            external_blank_rows=external_blank_rows,
        )
        self._buffer_state.update(buffer)

    def render_request(self, request: LiveViewportRenderRequest) -> None:
        render_live_viewport_request(
            self.writer,
            request,
            previous_buffer=self._buffer_state.previous,
        )
        self._buffer_state.update(request.buffer)

    def apply_update(self, update: LiveViewportUpdate) -> None:
        apply_live_viewport_update(
            self.writer,
            update,
            live_viewport=self,
        )

    def flush(self) -> None:
        """Flush pending live-viewport output through the backend writer."""

        flush_writer(self.writer)

    def sync_cursor_visibility(self, visible: bool, *, active: bool = True) -> bool:
        """Apply cursor visibility only when it differs from backend state."""

        if not active:
            return False
        target = bool(visible)
        if target == self._cursor_visible:
            return False
        if target:
            self.show_cursor()
        else:
            self.hide_cursor()
        return True

    def restore_cursor(self) -> bool:
        """Ensure the host terminal cursor is visible after live-pane use."""

        changed = self.sync_cursor_visibility(True)
        if changed:
            self.flush()
        return changed

    def hide_cursor(self) -> None:
        """Hide the terminal cursor through the live-viewport backend."""

        hide_cursor_ansi(self.writer)
        self._cursor_visible = False

    def show_cursor(self) -> None:
        """Show the terminal cursor through the live-viewport backend."""

        show_cursor_ansi(self.writer)
        self._cursor_visible = True


def create_live_viewport_renderer(writer: TextIO) -> LiveViewportRenderer:
    """Create the owner-managed live viewport renderer for a writer.

    Rust owner: ``codex-tui::custom_terminal`` owns the current/previous
    buffer state and cursor visibility lifecycle. Terminal controllers should
    request this owner state here instead of instantiating renderer internals.
    """

    return LiveViewportRenderer(writer)


def _visible_width(text: str) -> int:
    total = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return total


def _cursor_style_sequence(style: str) -> str:
    mapping = {
        "DefaultUserShape": "\x1b[0 q",
        "SteadyBar": "\x1b[6 q",
    }
    return mapping.get(str(style), f"<cursor-style:{style}>")


__all__ = [
    "AlternateScreenRenderer",
    "BEL",
    "ESC",
    "LiveViewportBufferState",
    "LiveViewportClearRequest",
    "LiveViewportProjection",
    "LiveViewportCursorMove",
    "LiveViewportCursorMoveCallback",
    "LiveViewportProjectionCycle",
    "LiveViewportProjectionCycleRunner",
    "LiveViewportProjectionRequestRunner",
    "LiveViewportProjectionPolicy",
    "LiveViewportRenderRequest",
    "LiveViewportRenderer",
    "LiveViewportUpdate",
    "LiveViewportWriteProtocol",
    "TerminalColumnProvider",
    "TerminalScrollRegionResetter",
    "prepare_live_viewport_redraw",
    "RUST_MODULE",
    "apply_live_viewport_cursor_move",
    "apply_live_viewport_projection",
    "apply_live_viewport_update",
    "apply_live_viewport_update_with_cursor_move",
    "check_live_viewport_resize",
    "clear_inline_status_line",
    "clear_live_viewport",
    "clear_live_viewport_request",
    "clear_lines_at",
    "clear_scrollback_and_visible_screen_ansi",
    "create_live_viewport_renderer",
    "create_live_viewport_projection_cycle_runner",
    "create_live_viewport_projection_request_runner",
    "display_width",
    "disable_bracketed_paste",
    "enable_bracketed_paste",
    "enter_alternate_screen",
    "flush_live_viewport",
    "flush_writer",
    "hide_cursor_ansi",
    "live_viewport_blank_rows",
    "live_viewport_buffer_area_for_rows",
    "live_viewport_backend_cursor_position_enabled",
    "live_viewport_cursor_position",
    "live_viewport_minimum_row_widths_for_writes",
    "live_viewport_requires_full_redraw",
    "leave_alternate_screen",
    "render_live_viewport_buffer",
    "render_live_viewport_request",
    "reset_cursor_style_ansi",
    "run_live_viewport_projection_cycle",
    "run_prepared_live_viewport_projection_cycle",
    "run_live_viewport_update_cycle",
    "set_cursor_style_ansi",
    "terminal_clear_scrollback_cursor_position",
    "terminal_viewport_clear_should_run",
    "terminal_visible_history_rows_after_clear",
    "terminal_visible_history_rows_after_insert",
    "terminal_visible_history_rows_after_viewport_change",
    "terminal_size",
    "truncate_display_width",
    "show_cursor_ansi",
    "sync_live_viewport_cursor_visibility",
    "write_inline_status_line",
]
