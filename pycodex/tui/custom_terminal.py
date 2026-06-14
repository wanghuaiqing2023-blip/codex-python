"""Semantic port slice for Rust ``codex-tui::custom_terminal``.

The Rust module is a custom ratatui terminal.  Python models the tested
behavior with lightweight buffer/backend objects rather than ratatui types.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="custom_terminal", source="codex/codex-rs/tui/src/custom_terminal.rs")

ESC = "\x1b"
BEL = "\x07"


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


@dataclass(frozen=True)
class Position:
    x: int = 0
    y: int = 0


@dataclass(frozen=True)
class Size:
    width: int
    height: int


@dataclass(frozen=True)
class Rect:
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @classmethod
    def new(cls, x: int, y: int, width: int, height: int) -> "Rect":
        return cls(x, y, width, height)

    def top(self) -> int:
        return self.y

    def is_empty(self) -> bool:
        return self.width == 0 or self.height == 0

    def as_position(self) -> Position:
        return Position(self.x, self.y)


@dataclass
class Cell:
    symbol: str = " "
    fg: str = "Reset"
    bg: str = "Reset"
    modifier: frozenset[str] = field(default_factory=frozenset)
    skip: bool = False

    def set_symbol(self, symbol: str) -> "Cell":
        self.symbol = str(symbol)
        return self


@dataclass
class Buffer:
    area: Rect
    content: list[Cell]

    @classmethod
    def empty(cls, area: Rect) -> "Buffer":
        return cls(area, [Cell() for _ in range(area.width * area.height)])

    def resize(self, area: Rect) -> None:
        self.area = area
        self.content = [Cell() for _ in range(area.width * area.height)]

    def reset(self) -> None:
        self.content = [Cell() for _ in range(self.area.width * self.area.height)]

    def cell_mut(self, pos: tuple[int, int]) -> Cell | None:
        x, y = pos
        if x < 0 or y < 0 or x >= self.area.width or y >= self.area.height:
            return None
        return self.content[y * self.area.width + x]

    def set_string(self, x: int, y: int, text: str, style: Any = None) -> None:
        col = x
        for ch in str(text):
            cell = self.cell_mut((col, y))
            if cell is None:
                break
            cell.symbol = ch
            width = max(display_width(ch), 1)
            for skip_x in range(col + 1, min(col + width, self.area.width)):
                skip_cell = self.cell_mut((skip_x, y))
                if skip_cell is not None:
                    skip_cell.skip = True
            col += width

    def pos_of(self, index: int) -> tuple[int, int]:
        return index % self.area.width, index // self.area.width


@dataclass(frozen=True)
class DrawCommand:
    kind: str
    x: int
    y: int
    cell: Cell | None = None
    bg: str = "Reset"

    @classmethod
    def put(cls, x: int, y: int, cell: Cell) -> "DrawCommand":
        return cls("Put", x, y, cell=cell)

    @classmethod
    def clear_to_end(cls, x: int, y: int, bg: str) -> "DrawCommand":
        return cls("ClearToEnd", x, y, bg=bg)

    def is_put(self) -> bool:
        return self.kind == "Put"


@dataclass
class Frame:
    cursor_position: Position | None
    cursor_style: str
    viewport_area: Rect
    buffer: Buffer

    def area(self) -> Rect:
        return self.viewport_area

    def render_widget_ref(self, widget: Any, area: Rect) -> None:
        render = getattr(widget, "render_ref", None)
        if callable(render):
            render(area, self.buffer)

    def set_cursor_position(self, position: Any) -> None:
        self.cursor_position = _coerce_position(position)

    def set_cursor_style(self, style: str) -> None:
        self.cursor_style = str(style)

    def buffer_mut(self) -> Buffer:
        return self.buffer


@dataclass
class CaptureBackend:
    output_bytes: bytearray
    size_value: Size
    cursor: Position
    hidden: bool = False

    @classmethod
    def new(cls, width: int, height: int) -> "CaptureBackend":
        return cls(bytearray(), Size(width, height), Position(0, 0))

    def write(self, data: str | bytes) -> None:
        if isinstance(data, str):
            data = data.encode()
        self.output_bytes.extend(data)

    def flush(self) -> None:
        pass

    def output(self) -> str:
        return self.output_bytes.decode(errors="replace")

    def size(self) -> Size:
        return self.size_value

    def get_cursor_position(self) -> Position:
        return self.cursor

    def set_cursor_position(self, position: Any) -> None:
        self.cursor = _coerce_position(position)

    def hide_cursor(self) -> None:
        self.hidden = True

    def show_cursor(self) -> None:
        self.hidden = False

    def clear_region(self, clear_type: str) -> None:
        self.write(f"<clear:{clear_type}>")


@dataclass
class Terminal:
    backend_value: CaptureBackend
    buffers: list[Buffer]
    current: int
    hidden_cursor: bool
    viewport_area: Rect
    last_known_screen_size: Size
    last_known_cursor_pos: Position
    _visible_history_rows: int = 0

    @classmethod
    def with_options(cls, backend: CaptureBackend) -> "Terminal":
        try:
            cursor_pos = backend.get_cursor_position()
        except Exception:
            cursor_pos = Position(0, 0)
        return cls.with_screen_size_and_cursor_position(backend, backend.size(), cursor_pos)

    @classmethod
    def with_options_and_cursor_position(cls, backend: CaptureBackend, cursor_pos: Any) -> "Terminal":
        return cls.with_screen_size_and_cursor_position(backend, backend.size(), _coerce_position(cursor_pos))

    @classmethod
    def with_screen_size_and_cursor_position(cls, backend: CaptureBackend, screen_size: Size, cursor_pos: Position) -> "Terminal":
        return cls(
            backend,
            [Buffer.empty(Rect()), Buffer.empty(Rect())],
            0,
            False,
            Rect(0, cursor_pos.y, 0, 0),
            screen_size,
            cursor_pos,
        )

    def get_frame(self) -> Frame:
        return Frame(None, "DefaultUserShape", self.viewport_area, self.current_buffer_mut())

    def current_buffer(self) -> Buffer:
        return self.buffers[self.current]

    def current_buffer_mut(self) -> Buffer:
        return self.buffers[self.current]

    def previous_buffer(self) -> Buffer:
        return self.buffers[1 - self.current]

    def previous_buffer_mut(self) -> Buffer:
        return self.buffers[1 - self.current]

    def backend(self) -> CaptureBackend:
        return self.backend_value

    def backend_mut(self) -> CaptureBackend:
        return self.backend_value

    def flush(self) -> None:
        updates = diff_buffers(self.previous_buffer(), self.current_buffer())
        last_put = next((command for command in reversed(updates) if command.is_put()), None)
        if last_put is not None:
            self.last_known_cursor_pos = Position(last_put.x, last_put.y)
        draw(self.backend_value, updates)

    def resize(self, screen_size: Size) -> None:
        self.last_known_screen_size = screen_size

    def set_viewport_area(self, area: Rect) -> None:
        self.current_buffer_mut().resize(area)
        self.previous_buffer_mut().resize(area)
        self.viewport_area = area
        self._visible_history_rows = min(self._visible_history_rows, area.top())

    def autoresize(self) -> None:
        screen_size = self.size()
        if screen_size != self.last_known_screen_size:
            self.resize(screen_size)

    def draw(self, render_callback: Callable[[Frame], None]) -> None:
        self.try_draw(lambda frame: render_callback(frame))

    def try_draw(self, render_callback: Callable[[Frame], Any]) -> None:
        self.autoresize()
        frame = self.get_frame()
        render_callback(frame)
        cursor_position = frame.cursor_position
        cursor_style = frame.cursor_style
        self.flush()
        if cursor_position is None:
            self.hide_cursor()
        else:
            self.set_cursor_style(cursor_style)
            self.show_cursor()
            self.set_cursor_position(cursor_position)
        self.swap_buffers()
        self.backend_value.flush()

    def hide_cursor(self) -> None:
        self.backend_value.hide_cursor()
        self.hidden_cursor = True

    def show_cursor(self) -> None:
        self.backend_value.show_cursor()
        self.hidden_cursor = False

    def set_cursor_style(self, style: str) -> None:
        self.backend_value.write(_cursor_style_sequence(style))

    def reset_cursor_style(self) -> None:
        self.set_cursor_style("DefaultUserShape")

    def get_cursor_position(self) -> Position:
        return self.backend_value.get_cursor_position()

    def set_cursor_position(self, position: Any) -> None:
        pos = _coerce_position(position)
        self.backend_value.set_cursor_position(pos)
        self.last_known_cursor_pos = pos

    def clear(self) -> None:
        if not self.viewport_area.is_empty():
            self.clear_after_position(self.viewport_area.as_position())

    def clear_after_position(self, position: Any) -> None:
        self.backend_value.set_cursor_position(position)
        self.backend_value.clear_region("AfterCursor")
        self.previous_buffer_mut().reset()

    def invalidate_viewport(self) -> None:
        self.previous_buffer_mut().reset()

    def clear_scrollback(self) -> None:
        if self.viewport_area.is_empty():
            return
        home = Position(0, 0)
        self.set_cursor_position(home)
        self.backend_value.write("<purge>")
        self.set_cursor_position(home)
        self.previous_buffer_mut().reset()

    def clear_visible_screen(self) -> None:
        home = Position(0, 0)
        self.set_cursor_position(home)
        self.backend_value.clear_region("All")
        self.set_cursor_position(home)
        self._visible_history_rows = 0
        self.previous_buffer_mut().reset()

    def clear_scrollback_and_visible_screen_ansi(self) -> None:
        if self.viewport_area.is_empty():
            return
        self.backend_value.write("\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H")
        self.last_known_cursor_pos = Position(0, 0)
        self._visible_history_rows = 0
        self.previous_buffer_mut().reset()

    def visible_history_rows(self) -> int:
        return self._visible_history_rows

    def note_history_rows_inserted(self, inserted_rows: int) -> None:
        self._visible_history_rows = min(self._visible_history_rows + inserted_rows, self.viewport_area.top())

    def swap_buffers(self) -> None:
        self.previous_buffer_mut().reset()
        self.current = 1 - self.current

    def size(self) -> Size:
        return self.backend_value.size()


@dataclass(frozen=True)
class ModifierDiff:
    from_modifiers: frozenset[str]
    to_modifiers: frozenset[str]

    def queue(self, writer: CaptureBackend) -> None:
        for removed in sorted(self.from_modifiers - self.to_modifiers):
            writer.write(f"<no-{removed}>")
        for added in sorted(self.to_modifiers - self.from_modifiers):
            writer.write(f"<{added}>")


def diff_buffers(a: Buffer, b: Buffer) -> list[DrawCommand]:
    previous_buffer = a.content
    next_buffer = b.content
    updates: list[DrawCommand] = []
    if a.area.width == 0 or a.area.height == 0:
        return updates

    last_nonblank_columns = [0 for _ in range(a.area.height)]
    for y in range(a.area.height):
        row_start = y * a.area.width
        row_end = row_start + a.area.width
        row = next_buffer[row_start:row_end]
        bg = row[-1].bg if row else "Reset"
        last_nonblank_column = 0
        column = 0
        while column < len(row):
            cell = row[column]
            width = display_width(cell.symbol)
            if cell.symbol != " " or cell.bg != bg or cell.modifier:
                last_nonblank_column = column + max(width - 1, 0)
            column += max(width, 1)
        if last_nonblank_column + 1 < len(row):
            x, clear_y = a.pos_of(row_start + last_nonblank_column + 1)
            updates.append(DrawCommand.clear_to_end(x, clear_y, bg))
        last_nonblank_columns[y] = last_nonblank_column

    invalidated = 0
    to_skip = 0
    for i, (current, previous) in enumerate(zip(next_buffer, previous_buffer)):
        if not current.skip and (current != previous or invalidated > 0) and to_skip == 0:
            x, y = a.pos_of(i)
            if x <= last_nonblank_columns[y]:
                updates.append(DrawCommand.put(x, y, current))
        to_skip = max(display_width(current.symbol) - 1, 0)
        affected_width = max(display_width(current.symbol), display_width(previous.symbol))
        invalidated = max(affected_width, invalidated) - 1
        if invalidated < 0:
            invalidated = 0
    return updates


def draw(writer: CaptureBackend, commands: Iterable[DrawCommand]) -> None:
    last_pos: Position | None = None
    for command in commands:
        if last_pos is None or not (command.x == last_pos.x + 1 and command.y == last_pos.y):
            writer.write(f"\x1b[{command.y + 1};{command.x + 1}H")
        last_pos = Position(command.x, command.y)
        if command.kind == "Put" and command.cell is not None:
            writer.write(command.cell.symbol)
        elif command.kind == "ClearToEnd":
            writer.write("\x1b[K")
    writer.write("\x1b[39m\x1b[49m\x1b[0m")


def with_options(backend: CaptureBackend) -> Terminal:
    return Terminal.with_options(backend)


def with_options_and_cursor_position(backend: CaptureBackend, cursor_pos: Any) -> Terminal:
    return Terminal.with_options_and_cursor_position(backend, cursor_pos)


def with_screen_size_and_cursor_position(backend: CaptureBackend, screen_size: Size, cursor_pos: Position) -> Terminal:
    return Terminal.with_screen_size_and_cursor_position(backend, screen_size, cursor_pos)


def diff_buffers_does_not_emit_clear_to_end_for_full_width_row() -> None:
    area = Rect.new(0, 0, 3, 2)
    previous = Buffer.empty(area)
    next_buffer = Buffer.empty(area)
    next_buffer.cell_mut((2, 0)).set_symbol("X")  # type: ignore[union-attr]
    commands = diff_buffers(previous, next_buffer)
    assert not [command for command in commands if command.kind == "ClearToEnd" and command.y == 0]
    assert any(command.kind == "Put" and command.x == 2 and command.y == 0 for command in commands)


def diff_buffers_clear_to_end_starts_after_wide_char() -> None:
    area = Rect.new(0, 0, 10, 1)
    previous = Buffer.empty(area)
    next_buffer = Buffer.empty(area)
    previous.set_string(0, 0, "中文")
    next_buffer.set_string(0, 0, "中")
    commands = diff_buffers(previous, next_buffer)
    assert any(command.kind == "ClearToEnd" and command.x == 2 and command.y == 0 for command in commands)


def terminal_draw_applies_requested_cursor_style() -> None:
    terminal = Terminal.with_options(CaptureBackend.new(2, 1))
    terminal.set_viewport_area(Rect.new(0, 0, 2, 1))
    terminal.try_draw(lambda frame: (frame.set_cursor_style("SteadyBar"), frame.set_cursor_position((0, 0))))
    assert _cursor_style_sequence("SteadyBar") in terminal.backend().output()


def reset_cursor_style_emits_default_user_shape() -> None:
    terminal = Terminal.with_options(CaptureBackend.new(2, 1))
    terminal.reset_cursor_style()
    assert _cursor_style_sequence("DefaultUserShape") in terminal.backend().output()


def _visible_width(text: str) -> int:
    total = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return total


def _coerce_position(value: Any) -> Position:
    if isinstance(value, Position):
        return value
    if isinstance(value, dict):
        return Position(int(value.get("x", 0)), int(value.get("y", 0)))
    x, y = value
    return Position(int(x), int(y))


def _cursor_style_sequence(style: str) -> str:
    mapping = {
        "DefaultUserShape": "\x1b[0 q",
        "SteadyBar": "\x1b[6 q",
    }
    return mapping.get(str(style), f"<cursor-style:{style}>")


__all__ = [
    "BEL",
    "Buffer",
    "CaptureBackend",
    "Cell",
    "DrawCommand",
    "ESC",
    "Frame",
    "ModifierDiff",
    "Position",
    "RUST_MODULE",
    "Rect",
    "Size",
    "Terminal",
    "diff_buffers",
    "diff_buffers_clear_to_end_starts_after_wide_char",
    "diff_buffers_does_not_emit_clear_to_end_for_full_width_row",
    "display_width",
    "draw",
    "reset_cursor_style_emits_default_user_shape",
    "terminal_draw_applies_requested_cursor_style",
    "with_options",
    "with_options_and_cursor_position",
    "with_screen_size_and_cursor_position",
]
