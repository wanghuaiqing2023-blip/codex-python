"""Adapters from ratatui_bridge semantic render output to vendored Rich."""

from __future__ import annotations

from typing import Iterable, List, Optional

from .buffer import Buffer, Cell
from .layout import Rect
from .text import Line, Span, Text


def span_to_rich_text(span: Span):
    """Convert a bridge `Span` to a vendored Rich `Text` fragment."""
    from pycodex.tui.rich_compat import Text as RichText

    return RichText(span.content, style=span.style.to_rich_style())


def line_to_rich_text(line: Line):
    """Convert a bridge `Line` to vendored Rich `Text`."""
    from pycodex.tui.rich_compat import Text as RichText

    rich = RichText()
    for span in line.spans:
        rich.append(span.content, style=span.style.to_rich_style())
    return rich


def text_to_rich_text(text: Text):
    """Convert bridge `Text` to vendored Rich `Text`."""
    from pycodex.tui.rich_compat import Text as RichText

    rich = RichText()
    for index, line in enumerate(text.lines):
        if index:
            rich.append("\n")
        for span in line.spans:
            rich.append(span.content, style=span.style.to_rich_style())
    return rich


def cell_to_rich_text(cell: Cell):
    """Convert one bridge `Cell` to a vendored Rich `Text` fragment."""
    from pycodex.tui.rich_compat import Text as RichText

    return RichText(cell.symbol, style=cell.style.to_rich_style())


def buffer_to_rich_text(buffer: Buffer, area: Optional[Rect] = None, trim_end: bool = False):
    """Convert a semantic `Buffer` region into vendored Rich `Text`."""
    from pycodex.tui.rich_compat import Text as RichText

    target = buffer.area if area is None else buffer.area.intersection(area)
    rich = RichText()
    for row_index, y in enumerate(range(target.y, target.bottom())):
        if row_index:
            rich.append("\n")
        cells = [buffer.cell(x, y) for x in range(target.x, target.right())]
        if trim_end:
            cells = _trim_cells_right(cells)
        _append_cells(rich, cells)
    return rich


def buffer_to_plain_text(buffer: Buffer, area: Optional[Rect] = None, trim_end: bool = False) -> str:
    """Return a plain string snapshot of a semantic `Buffer` region."""
    target = buffer.area if area is None else buffer.area.intersection(area)
    lines = []
    for y in range(target.y, target.bottom()):
        text = "".join(
            cell.symbol
            for x in range(target.x, target.right())
            for cell in (buffer.cell(x, y),)
            if not cell.skip
        )
        lines.append(text.rstrip() if trim_end else text)
    return "\n".join(lines)


def render_to_buffer(renderable: object, area: Rect) -> Buffer:
    """Render any bridge-style object into a fresh semantic buffer."""
    render = getattr(renderable, "render", None)
    if render is None:
        raise TypeError("renderable must provide render(area, buffer)")
    buffer = Buffer.empty(area)
    render(area, buffer)
    return buffer


def render_to_rich_text(renderable: object, area: Rect, trim_end: bool = False):
    """Render a bridge object and convert the result to Rich `Text`."""
    return buffer_to_rich_text(render_to_buffer(renderable, area), trim_end=trim_end)


def _append_cells(rich: object, cells: Iterable[Cell]) -> None:
    for cell in cells:
        if cell.skip:
            continue
        rich.append(cell.symbol, style=cell.style.to_rich_style())


def _trim_cells_right(cells: List[Cell]) -> List[Cell]:
    end = len(cells)
    while end > 0 and (cells[end - 1].symbol == " " or cells[end - 1].skip):
        end -= 1
    return cells[:end]


__all__ = [
    "buffer_to_plain_text",
    "buffer_to_rich_text",
    "cell_to_rich_text",
    "line_to_rich_text",
    "render_to_buffer",
    "render_to_rich_text",
    "span_to_rich_text",
    "text_to_rich_text",
]
