"""Small semantic equivalent of ratatui buffer values.

The bridge captures ratatui's cell-addressable render target without pulling in
terminal backend concepts. It is intentionally simple: coordinates outside the
buffer are ignored for writes and return a blank default cell for reads, which
keeps render-style code easy to exercise in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from .layout import Rect
from .style import Style
from .text import Line, Span, Text


@dataclass(frozen=True)
class Cell:
    symbol: str = " "
    style: Style = Style()

    @classmethod
    def blank(cls) -> "Cell":
        return cls()

    def with_symbol(self, symbol: object) -> "Cell":
        text = str(symbol)
        return Cell(text[:1] if text else " ", self.style)

    def with_style(self, style: Style) -> "Cell":
        return Cell(self.symbol, style)


class Buffer:
    """Cell-addressable semantic render target."""

    def __init__(self, area: Rect, cells: Optional[Iterable[Cell]] = None) -> None:
        self.area = area
        count = max(area.width, 0) * max(area.height, 0)
        initial = list(cells) if cells is not None else []
        if len(initial) > count:
            raise ValueError("too many cells for buffer area")
        self._cells: List[Cell] = initial + [Cell.blank() for _ in range(count - len(initial))]

    @classmethod
    def empty(cls, area: Rect) -> "Buffer":
        return cls(area)

    @property
    def width(self) -> int:
        return self.area.width

    @property
    def height(self) -> int:
        return self.area.height

    def index_of(self, x: int, y: int) -> Optional[int]:
        if x < self.area.x or y < self.area.y:
            return None
        local_x = x - self.area.x
        local_y = y - self.area.y
        if local_x >= self.area.width or local_y >= self.area.height:
            return None
        return local_y * self.area.width + local_x

    def cell(self, x: int, y: int) -> Cell:
        index = self.index_of(x, y)
        return Cell.blank() if index is None else self._cells[index]

    def __getitem__(self, position: Tuple[int, int]) -> Cell:
        x, y = position
        return self.cell(x, y)

    def __setitem__(self, position: Tuple[int, int], cell: Cell) -> None:
        x, y = position
        self.set_cell(x, y, cell)

    def set_cell(self, x: int, y: int, cell: Cell) -> None:
        index = self.index_of(x, y)
        if index is not None:
            self._cells[index] = cell

    def set_symbol(self, x: int, y: int, symbol: object, style: Optional[Style] = None) -> None:
        current = self.cell(x, y)
        self.set_cell(x, y, current.with_symbol(symbol).with_style(style or current.style))

    def set_style(self, area: Rect, style: Style) -> None:
        target = self.area.intersection(area)
        for y in range(target.y, target.bottom()):
            for x in range(target.x, target.right()):
                self.set_cell(x, y, self.cell(x, y).with_style(style))

    def fill(self, area: Rect, cell: Optional[Cell] = None) -> None:
        target = self.area.intersection(area)
        value = cell or Cell.blank()
        for y in range(target.y, target.bottom()):
            for x in range(target.x, target.right()):
                self.set_cell(x, y, value)

    def set_span(self, x: int, y: int, span: Span, max_width: Optional[int] = None) -> int:
        written = 0
        limit = len(span.content) if max_width is None else max(max_width, 0)
        for offset, char in enumerate(span.content[:limit]):
            self.set_cell(x + offset, y, Cell(char, span.style))
            written += 1
        return written

    def set_line(self, x: int, y: int, line: Line, max_width: Optional[int] = None) -> int:
        written = 0
        remaining = max_width
        cursor = x
        for span in line.spans:
            if remaining is not None and remaining <= 0:
                break
            count = self.set_span(cursor, y, span, remaining)
            cursor += count
            written += count
            if remaining is not None:
                remaining -= count
        return written

    def set_text(self, x: int, y: int, text: Text, max_width: Optional[int] = None) -> int:
        written = 0
        for offset, line in enumerate(text.lines):
            written += self.set_line(x, y + offset, line, max_width)
        return written

    def row_plain(self, y: int) -> str:
        return "".join(self.cell(self.area.x + x, y).symbol for x in range(self.area.width))

    def plain_lines(self) -> List[str]:
        return [self.row_plain(self.area.y + y) for y in range(self.area.height)]

    def plain(self) -> str:
        return "\n".join(self.plain_lines())

    def to_rich_text(self, area: Optional[Rect] = None, trim_end: bool = False):
        from .textual_adapter import buffer_to_rich_text

        return buffer_to_rich_text(self, area=area, trim_end=trim_end)

    def to_plain_text(self, area: Optional[Rect] = None, trim_end: bool = False) -> str:
        from .textual_adapter import buffer_to_plain_text

        return buffer_to_plain_text(self, area=area, trim_end=trim_end)


__all__ = ["Buffer", "Cell"]
