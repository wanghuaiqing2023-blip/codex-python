"""Portable backend/test-backend subset for ratatui bridge.

This module intentionally models backend state, not terminal side effects. Real
terminal integration stays in the Python terminal runtime/custom-terminal
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Protocol, TextIO, TypeVar

from .buffer import Buffer, Cell
from .layout import Position, Rect, Size
from .style import Color, Modifier, Style

T = TypeVar("T")


@dataclass(frozen=True)
class WindowSize:
    columns_rows: Size
    pixels: Optional[Size] = None


class Backend(Protocol):
    def size(self) -> Size:
        ...

    def window_size(self) -> WindowSize:
        ...

    def buffer(self) -> Buffer:
        ...

    def draw(self, content: tuple["DrawCommand", ...]) -> None:
        ...

    def set_cursor_position(self, position: Position) -> None:
        ...

    def flush(self) -> None:
        ...


@dataclass(frozen=True)
class DrawCommand:
    kind: str
    x: int
    y: int
    cell: Optional[Cell] = None

    @classmethod
    def put(cls, x: int, y: int, cell: Cell) -> "DrawCommand":
        return cls("put", x, y, cell)

    @classmethod
    def clear_to_end(cls, x: int, y: int) -> "DrawCommand":
        return cls("clear_to_end", x, y)

    def is_put(self) -> bool:
        return self.kind == "put"


@dataclass
class FrameBufferState:
    """Previous-buffer state for Rust-like frame diff redraws.

    Rust owner: ``codex-tui::custom_terminal::Terminal`` keeps current and
    previous frame buffers and invalidates the previous buffer after external
    terminal side effects.  Python's hybrid adapters use this small state holder
    when they render only a live viewport instead of owning a full Terminal.
    """

    previous: Buffer | None = None

    def reset(self) -> None:
        self.previous = None

    def update(self, buffer: Buffer) -> None:
        self.previous = buffer.clone()


def diff_buffers(previous: Buffer, current: Buffer) -> tuple[DrawCommand, ...]:
    if previous.area != current.area:
        return full_redraw_commands(current)
    if current.width <= 0 or current.height <= 0:
        return ()

    updates: list[DrawCommand] = []
    previous_cells = previous.cells()
    current_cells = current.cells()
    for y in range(current.area.y, current.area.bottom()):
        row_changed = False
        last_nonblank = current.area.x - 1
        for x in range(current.area.x, current.area.right()):
            current_cell = current.cell(x, y)
            previous_cell = previous.cell(x, y)
            if current_cell != previous_cell:
                row_changed = True
            if current_cell != Cell.blank():
                last_nonblank = x
        if not row_changed:
            continue

        for x in range(current.area.x, current.area.right()):
            index = current.index_of(x, y)
            if index is None:
                continue
            current_cell = current_cells[index]
            previous_cell = previous_cells[index]
            if current_cell != previous_cell and x <= last_nonblank and not current_cell.skip:
                updates.append(DrawCommand.put(x, y, current_cell))

        if last_nonblank < current.area.right() - 1:
            clear_x = max(last_nonblank + 1, current.area.x)
            updates.append(DrawCommand.clear_to_end(clear_x, y))

    return tuple(updates)


def full_redraw_commands(
    buffer: Buffer,
    *,
    minimum_row_widths: Mapping[int, int] | None = None,
) -> tuple[DrawCommand, ...]:
    """Return draw commands for a complete buffer repaint.

    Rust owner: ``codex-tui::custom_terminal`` owns turning a ratatui buffer
    into backend draw operations.  ``minimum_row_widths`` lets hybrid terminal
    adapters preserve intentionally visible trailing prompt space while keeping
    the repaint policy in the backend layer.
    """

    row_widths = minimum_row_widths or {}
    updates: list[DrawCommand] = []
    for y in range(buffer.area.y, buffer.area.bottom()):
        last_nonblank = buffer.area.x - 1
        for x in range(buffer.area.x, buffer.area.right()):
            if buffer.cell(x, y) != Cell.blank():
                last_nonblank = x
        minimum_width = row_widths.get(y, 0)
        desired_last = max(last_nonblank, buffer.area.x + max(0, minimum_width) - 1)
        for x in range(buffer.area.x, min(desired_last + 1, buffer.area.right())):
            cell = buffer.cell(x, y)
            if not cell.skip:
                updates.append(DrawCommand.put(x, y, cell))
        if desired_last < buffer.area.right() - 1:
            updates.append(DrawCommand.clear_to_end(max(desired_last + 1, buffer.area.x), y))
    return tuple(updates)


def requires_full_redraw(previous: Buffer | None, current: Buffer) -> bool:
    """Return whether drawing ``current`` must ignore previous-buffer diffs.

    Rust owner: ``codex-tui::custom_terminal`` owns previous/current buffer
    compatibility.  Hybrid terminal adapters should ask the bridge instead of
    duplicating area checks at the surface layer.
    """

    return previous is None or previous.area != current.area


def draw_buffer_to_ansi(
    writer: TextIO,
    current: Buffer,
    *,
    previous: Buffer | None = None,
    minimum_row_widths: Mapping[int, int] | None = None,
    cursor_position: Position | None = None,
) -> None:
    """Draw a current buffer to an ANSI writer using diff/full-redraw rules.

    Rust owner: ``codex-tui::custom_terminal`` computes current/previous
    buffer differences and delegates draw commands to the backend.  This helper
    keeps that choice in the bridge backend layer for Python hybrid adapters.
    """

    if not requires_full_redraw(previous, current):
        backend = AnsiBackend.new(
            writer,
            max(previous.area.right(), current.area.right()),
            max(previous.area.bottom(), current.area.bottom()),
        )
        backend.draw(diff_buffers(previous, current))
        if cursor_position is not None:
            backend.set_cursor_position(cursor_position)
        return

    backend = AnsiBackend.new(writer, current.area.right(), current.area.bottom())
    backend.draw(full_redraw_commands(current, minimum_row_widths=minimum_row_widths))
    if cursor_position is not None:
        backend.set_cursor_position(cursor_position)


class TestBackend:
    """Cell-buffer backend equivalent for parity tests and semantic rendering."""

    def __init__(self, width: int, height: int) -> None:
        self._size = Size.new(width, height)
        self._buffer = Buffer.empty(Rect.new(0, 0, self._size.width, self._size.height))
        self.flush_count = 0
        self.draw_count = 0
        self.drawn_commands: list[DrawCommand] = []
        self.cursor_position: Optional[Position] = None

    @classmethod
    def new(cls, width: int, height: int) -> "TestBackend":
        return cls(width, height)

    def size(self) -> Size:
        return self._size

    def window_size(self) -> WindowSize:
        return WindowSize(self._size)

    def buffer(self) -> Buffer:
        return self._buffer

    def resize(self, width: int, height: int) -> None:
        self._size = Size.new(width, height)
        self._buffer = Buffer.empty(Rect.new(0, 0, self._size.width, self._size.height))

    def draw(self, content: tuple[DrawCommand, ...]) -> None:
        self.draw_count += 1
        self.drawn_commands.extend(content)
        for command in content:
            if command.kind == "put" and command.cell is not None:
                self._buffer.set_cell(command.x, command.y, command.cell)
            elif command.kind == "clear_to_end":
                for x in range(command.x, self._buffer.area.right()):
                    self._buffer.set_cell(x, command.y, Cell.blank())

    def set_cursor_position(self, position: Position) -> None:
        self.cursor_position = position

    def flush(self) -> None:
        self.flush_count += 1


class AnsiBackend:
    """ANSI output backend primitive for Python's hybrid terminal path.

    Rust owner: ``codex-tui::custom_terminal`` owns the current/previous frame
    diff and backend draw lifecycle.  This backend is intentionally tiny: it
    translates bridge ``DrawCommand`` values into cursor/style/clear ANSI
    writes while keeping a semantic buffer for tests and future adapters.
    """

    def __init__(self, writer: TextIO, width: int, height: int) -> None:
        self.writer = writer
        self._size = Size.new(width, height)
        self._buffer = Buffer.empty(Rect.new(0, 0, self._size.width, self._size.height))
        self.flush_count = 0
        self.draw_count = 0
        self.drawn_commands: list[DrawCommand] = []
        self.cursor_position: Optional[Position] = None

    @classmethod
    def new(cls, writer: TextIO, width: int, height: int) -> "AnsiBackend":
        return cls(writer, width, height)

    def size(self) -> Size:
        return self._size

    def window_size(self) -> WindowSize:
        return WindowSize(self._size)

    def buffer(self) -> Buffer:
        return self._buffer

    def resize(self, width: int, height: int) -> None:
        self._size = Size.new(width, height)
        self._buffer = Buffer.empty(Rect.new(0, 0, self._size.width, self._size.height))

    def draw(self, content: tuple[DrawCommand, ...]) -> None:
        self.draw_count += 1
        self.drawn_commands.extend(content)
        index = 0
        while index < len(content):
            command = content[index]
            if command.kind == "put" and command.cell is not None:
                index = self._draw_contiguous_cells(content, index)
                continue
            elif command.kind == "clear_to_end":
                self._clear_to_end(command.x, command.y)
            index += 1

    def set_cursor_position(self, position: Position) -> None:
        self.cursor_position = position
        self.writer.write(f"\x1b[{position.y + 1};{position.x + 1}H")

    def flush(self) -> None:
        self.flush_count += 1
        flush = getattr(self.writer, "flush", None)
        if callable(flush):
            flush()

    def _draw_contiguous_cells(self, content: tuple[DrawCommand, ...], start: int) -> int:
        first = content[start]
        if first.cell is None:
            return start + 1
        cells = [first.cell]
        end = start + 1
        expected_x = first.x + 1
        while end < len(content):
            command = content[end]
            if (
                command.kind != "put"
                or command.cell is None
                or command.y != first.y
                or command.x != expected_x
                or command.cell.style != first.cell.style
            ):
                break
            cells.append(command.cell)
            expected_x += 1
            end += 1
        self._draw_cells(first.x, first.y, tuple(cells))
        return end

    def _draw_cells(self, x: int, y: int, cells: tuple[Cell, ...]) -> None:
        if not cells:
            return
        cells = tuple(cell for cell in cells if not cell.skip)
        if not cells:
            return
        for offset, cell in enumerate(cells):
            self._buffer.set_cell(x + offset, y, cell)
        style_prefix = ansi_style_sequence(cells[0].style)
        style_suffix = "\x1b[0m" if style_prefix else ""
        text = "".join(cell.symbol for cell in cells)
        self.writer.write(f"\x1b[{y + 1};{x + 1}H{style_prefix}{text}{style_suffix}")

    def _draw_cell(self, x: int, y: int, cell: Cell) -> None:
        self._buffer.set_cell(x, y, cell)
        style_prefix = ansi_style_sequence(cell.style)
        style_suffix = "\x1b[0m" if style_prefix else ""
        self.writer.write(f"\x1b[{y + 1};{x + 1}H{style_prefix}{cell.symbol}{style_suffix}")

    def _clear_to_end(self, x: int, y: int) -> None:
        for column in range(x, self._buffer.area.right()):
            self._buffer.set_cell(column, y, Cell.blank())
        self.writer.write(f"\x1b[{y + 1};{x + 1}H\x1b[0K")


class CrosstermBackend:
    """Compatibility placeholder for Rust type boundaries.

    Python should not perform crossterm side effects through this class. It is
    intentionally non-rendering and raises for buffer access.
    """

    def __init__(self, stream: object = None) -> None:
        self.stream = stream

    def size(self) -> Size:
        raise NotImplementedError("CrosstermBackend size is runtime-specific in Python")

    def window_size(self) -> WindowSize:
        raise NotImplementedError("CrosstermBackend window_size is runtime-specific in Python")

    def buffer(self) -> Buffer:
        raise NotImplementedError("CrosstermBackend does not expose a semantic buffer")

    def draw(self, content: tuple[DrawCommand, ...]) -> None:
        raise NotImplementedError("CrosstermBackend draw is runtime-specific in Python")

    def set_cursor_position(self, position: Position) -> None:
        raise NotImplementedError("CrosstermBackend cursor position is runtime-specific in Python")

    def flush(self) -> None:
        raise NotImplementedError("CrosstermBackend flush is runtime-specific in Python")


@dataclass
class Frame:
    area: Rect
    buffer: Buffer
    cursor_position: Optional[Position] = None

    def size(self) -> Rect:
        return self.area

    def render_widget(self, widget: object, area: Rect) -> None:
        render = getattr(widget, "render", None)
        if render is None:
            raise TypeError("widget must provide render(area, buffer)")
        render(area, self.buffer)

    def render_widget_ref(self, widget: object, area: Rect) -> None:
        render_ref = getattr(widget, "render_ref", None)
        if render_ref is None:
            self.render_widget(widget, area)
            return
        render_ref(area, self.buffer)

    def set_cursor_position(self, position: object) -> None:
        if isinstance(position, Position):
            self.cursor_position = position
            return
        x, y = position  # type: ignore[misc]
        self.cursor_position = Position.new(x, y)


class Terminal:
    """Small semantic wrapper around a bridge backend."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend
        area = Rect.from_size(backend.size())
        self.viewport_area = area
        self._previous_buffer = Buffer.empty(area)
        self._current_buffer = Buffer.empty(area)
        self.last_diff: tuple[DrawCommand, ...] = ()
        self.last_cursor_position: Optional[Position] = None

    @classmethod
    def new(cls, backend: Backend) -> "Terminal":
        return cls(backend)

    def size(self) -> Size:
        return self.backend.size()

    def window_size(self) -> WindowSize:
        return self.backend.window_size()

    def draw(self, callback: Callable[[Frame], T]) -> T:
        size = self.backend.size()
        area = Rect.new(0, 0, size.width, size.height)
        if area != self.viewport_area:
            self.viewport_area = area
            self._previous_buffer = Buffer.empty(area)
        self._current_buffer = Buffer.empty(area)
        frame = Frame(area, self._current_buffer)
        result = callback(frame)
        self.last_cursor_position = frame.cursor_position
        self.last_diff = diff_buffers(self._previous_buffer, self._current_buffer)
        self.backend.draw(self.last_diff)
        if frame.cursor_position is not None:
            self.backend.set_cursor_position(frame.cursor_position)
        self.backend.flush()
        self._previous_buffer = self._current_buffer.clone()
        return result

    def backend_mut(self) -> Backend:
        return self.backend

    def backend_ref(self) -> Backend:
        return self.backend


def ansi_style_sequence(style: Style) -> str:
    """Return an ANSI SGR sequence for a bridge style, or ``""`` for default."""

    codes: list[str] = []
    if style.fg is not None:
        codes.append(_ansi_color_code(style.fg, foreground=True))
    if style.bg is not None:
        codes.append(_ansi_color_code(style.bg, foreground=False))
    for modifier in sorted(style.modifiers, key=lambda item: item.value):
        code = _ANSI_MODIFIERS.get(modifier)
        if code is not None:
            codes.append(code)
    return f"\x1b[{';'.join(codes)}m" if codes else ""


def _ansi_color_code(color: Color, *, foreground: bool) -> str:
    if color.kind == "reset":
        return "39" if foreground else "49"
    if color.kind == "indexed":
        return f"{38 if foreground else 48};5;{color.value}"
    if color.kind == "rgb":
        red, green, blue = color.value  # type: ignore[misc]
        return f"{38 if foreground else 48};2;{red};{green};{blue}"
    base = _ANSI_NAMED_COLORS.get(str(color.value))
    if base is None:
        return "39" if foreground else "49"
    return str(base if foreground else base + 10)


_ANSI_NAMED_COLORS = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "gray": 37,
    "white": 97,
    "dark_gray": 90,
    "light_red": 91,
    "light_green": 92,
    "light_yellow": 93,
    "light_blue": 94,
    "light_magenta": 95,
    "light_cyan": 96,
}


_ANSI_MODIFIERS = {
    Modifier.BOLD: "1",
    Modifier.DIM: "2",
    Modifier.ITALIC: "3",
    Modifier.UNDERLINED: "4",
    Modifier.REVERSED: "7",
    Modifier.CROSSED_OUT: "9",
}


__all__ = [
    "AnsiBackend",
    "Backend",
    "CrosstermBackend",
    "DrawCommand",
    "FrameBufferState",
    "Frame",
    "Terminal",
    "TestBackend",
    "WindowSize",
    "ansi_style_sequence",
    "draw_buffer_to_ansi",
    "diff_buffers",
    "full_redraw_commands",
]
