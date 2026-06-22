"""In-memory test backend for TUI parity tests.

Rust counterpart: ``codex-rs/tui/src/test_backend.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Iterator, Sequence


@dataclass(frozen=True)
class Position:
    x: int
    y: int


@dataclass(frozen=True)
class Size:
    width: int
    height: int


@dataclass(frozen=True)
class WindowSize:
    columns_rows: Size
    pixels: Size = Size(width=640, height=480)


class ClearType(str, Enum):
    ALL = "all"
    AFTER_CURSOR = "after_cursor"
    BEFORE_CURSOR = "before_cursor"
    CURRENT_LINE = "current_line"
    UNTIL_NEW_LINE = "until_new_line"


@dataclass(frozen=True)
class Cell:
    symbol: str = " "


def _coerce_cell_text(cell: Any) -> str:
    if isinstance(cell, Cell):
        return cell.symbol[:1] or " "
    if isinstance(cell, str):
        return cell[:1] or " "
    symbol = getattr(cell, "symbol", None)
    if isinstance(symbol, str):
        return symbol[:1] or " "
    text = getattr(cell, "text", None)
    if isinstance(text, str):
        return text[:1] or " "
    return str(cell)[:1] or " "


class VT100Backend:
    """Semantic mirror of Rust ``VT100Backend`` for Python tests.

    It models screen contents, cursor state, size, and scrolling without copying
    crossterm or vt100 internals. ANSI escape parsing is intentionally not
    implemented; callers should use ``draw`` for cell-level updates in parity
    tests.
    """

    def __init__(self, width: int, height: int) -> None:
        if width < 0 or height < 0:
            raise ValueError("width and height must be non-negative")
        self._width = int(width)
        self._height = int(height)
        self._rows: list[list[str]] = [[" " for _ in range(self._width)] for _ in range(self._height)]
        self._cursor = Position(0, 0)
        self.cursor_visible = True
        self._write_buffer = bytearray()
        self._pending_wrap = False

    @classmethod
    def new(cls, width: int, height: int) -> "VT100Backend":
        return cls(width, height)

    def vt100(self) -> "VT100Backend":
        return self

    def write(self, buf: bytes | bytearray | memoryview | str) -> int:
        if isinstance(buf, str):
            data = buf.encode("utf-8")
        else:
            data = bytes(buf)
        self._write_buffer.extend(data)
        self._write_text(data.decode("utf-8", errors="replace"))
        return len(data)

    def flush(self) -> None:
        return None

    def draw(self, content: Iterable[tuple[int, int, Any]]) -> None:
        for x, y, cell in content:
            self._put(int(x), int(y), _coerce_cell_text(cell))

    def hide_cursor(self) -> None:
        self.cursor_visible = False

    def show_cursor(self) -> None:
        self.cursor_visible = True

    def get_cursor_position(self) -> Position:
        return self._cursor

    def set_cursor_position(self, position: Position | Sequence[int] | tuple[int, int]) -> None:
        if isinstance(position, Position):
            x, y = position.x, position.y
        else:
            x, y = position[0], position[1]
        self._cursor = Position(max(0, min(int(x), max(self._width - 1, 0))), max(0, min(int(y), max(self._height - 1, 0))))
        self._pending_wrap = False

    def clear(self) -> None:
        self._rows = [[" " for _ in range(self._width)] for _ in range(self._height)]
        self._cursor = Position(0, 0)
        self._pending_wrap = False

    def clear_region(self, clear_type: ClearType | str) -> None:
        clear = ClearType(clear_type)
        x, y = self._cursor.x, self._cursor.y
        if clear == ClearType.ALL:
            self.clear()
        elif clear == ClearType.CURRENT_LINE:
            self._clear_line(y, 0, self._width)
        elif clear == ClearType.UNTIL_NEW_LINE:
            self._clear_line(y, x, self._width)
        elif clear == ClearType.AFTER_CURSOR:
            self._clear_line(y, x, self._width)
            for row in range(y + 1, self._height):
                self._clear_line(row, 0, self._width)
        elif clear == ClearType.BEFORE_CURSOR:
            for row in range(0, y):
                self._clear_line(row, 0, self._width)
            self._clear_line(y, 0, x + 1)

    def append_lines(self, line_count: int) -> None:
        for _ in range(max(0, int(line_count))):
            self._rows.append([" " for _ in range(self._width)])
            if len(self._rows) > self._height:
                self._rows.pop(0)

    def size(self) -> Size:
        return Size(width=self._width, height=self._height)

    def window_size(self) -> WindowSize:
        return WindowSize(columns_rows=self.size())

    def scroll_region_up(self, region: range | tuple[int, int], scroll_by: int) -> None:
        start, stop = self._region_bounds(region)
        count = min(max(0, int(scroll_by)), max(stop - start, 0))
        for _ in range(count):
            if start < stop:
                del self._rows[start]
                self._rows.insert(stop - 1, [" " for _ in range(self._width)])

    def scroll_region_down(self, region: range | tuple[int, int], scroll_by: int) -> None:
        start, stop = self._region_bounds(region)
        count = min(max(0, int(scroll_by)), max(stop - start, 0))
        for _ in range(count):
            if start < stop:
                del self._rows[stop - 1]
                self._rows.insert(start, [" " for _ in range(self._width)])

    def contents(self) -> str:
        return "\n".join("".join(row) for row in self._rows)

    def __str__(self) -> str:
        return self.contents()

    def _put(self, x: int, y: int, text: str) -> None:
        if 0 <= x < self._width and 0 <= y < self._height:
            self._rows[y][x] = text[:1] or " "

    def _write_text(self, text: str) -> None:
        x, y = self._cursor.x, self._cursor.y
        for char in text:
            if char == "\n":
                x = 0
                y += 1
                self._pending_wrap = False
            elif char == "\r":
                x = 0
                self._pending_wrap = False
            else:
                if self._pending_wrap:
                    x = 0
                    y += 1
                    self._pending_wrap = False
                    if y >= self._height and self._height > 0:
                        self._rows.pop(0)
                        self._rows.append([" " for _ in range(self._width)])
                        y = self._height - 1
                self._put(x, y, char)
                if x + 1 >= self._width:
                    self._pending_wrap = True
                else:
                    x += 1
            if y >= self._height and self._height > 0:
                self._rows.pop(0)
                self._rows.append([" " for _ in range(self._width)])
                y = self._height - 1
        self._cursor = Position(max(0, min(x, max(self._width - 1, 0))), max(0, min(y, max(self._height - 1, 0))))

    def _clear_line(self, y: int, start: int, stop: int) -> None:
        if not (0 <= y < self._height):
            return
        for x in range(max(0, start), min(stop, self._width)):
            self._rows[y][x] = " "

    def _region_bounds(self, region: range | tuple[int, int]) -> tuple[int, int]:
        if isinstance(region, range):
            start, stop = region.start, region.stop
        else:
            start, stop = region
        start = max(0, min(int(start), self._height))
        stop = max(start, min(int(stop), self._height))
        return start, stop


# Free-function adapters retain the scaffolded boundary names.
def write(backend: VT100Backend, buf: bytes | bytearray | memoryview | str) -> int:
    return backend.write(buf)


def flush(backend: VT100Backend) -> None:
    return backend.flush()


def fmt(backend: VT100Backend) -> str:
    return str(backend)


def draw(backend: VT100Backend, content: Iterable[tuple[int, int, Any]]) -> None:
    return backend.draw(content)


def hide_cursor(backend: VT100Backend) -> None:
    return backend.hide_cursor()


def show_cursor(backend: VT100Backend) -> None:
    return backend.show_cursor()


def get_cursor_position(backend: VT100Backend) -> Position:
    return backend.get_cursor_position()


def set_cursor_position(backend: VT100Backend, position: Position | Sequence[int] | tuple[int, int]) -> None:
    return backend.set_cursor_position(position)


def clear(backend: VT100Backend) -> None:
    return backend.clear()


def clear_region(backend: VT100Backend, clear_type: ClearType | str) -> None:
    return backend.clear_region(clear_type)


def append_lines(backend: VT100Backend, line_count: int) -> None:
    return backend.append_lines(line_count)


def size(backend: VT100Backend) -> Size:
    return backend.size()


def window_size(backend: VT100Backend) -> WindowSize:
    return backend.window_size()


def scroll_region_up(backend: VT100Backend, region: range | tuple[int, int], scroll_by: int) -> None:
    return backend.scroll_region_up(region, scroll_by)


def scroll_region_down(backend: VT100Backend, region: range | tuple[int, int], scroll_by: int) -> None:
    return backend.scroll_region_down(region, scroll_by)


__all__ = [
    "Cell",
    "ClearType",
    "Position",
    "Size",
    "VT100Backend",
    "WindowSize",
    "append_lines",
    "clear",
    "clear_region",
    "draw",
    "flush",
    "fmt",
    "get_cursor_position",
    "hide_cursor",
    "scroll_region_down",
    "scroll_region_up",
    "set_cursor_position",
    "show_cursor",
    "size",
    "window_size",
    "write",
]
