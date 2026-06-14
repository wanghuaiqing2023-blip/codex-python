"""Small semantic equivalents of ratatui widgets used by codex-tui."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntFlag
from typing import Iterable, List, Optional, Protocol, Tuple, Union

from .buffer import Buffer, Cell
from .layout import Alignment, Rect
from .style import Style
from .text import Line, Span, Text


class Widget(Protocol):
    def render(self, area: Rect, buffer: Buffer) -> None:
        ...


class WidgetRef(Protocol):
    def render_ref(self, area: Rect, buffer: Buffer) -> None:
        ...


class StatefulWidgetRef(Protocol):
    def render_ref(self, area: Rect, buffer: Buffer, state: object) -> None:
        ...


def render_ref(widget: object, area: Rect, buffer: Buffer) -> None:
    method = getattr(widget, "render_ref", None)
    if method is not None:
        method(area, buffer)
        return
    render = getattr(widget, "render", None)
    if render is None:
        raise TypeError("widget must provide render_ref(area, buffer) or render(area, buffer)")
    render(area, buffer)


def render_stateful_ref(widget: object, area: Rect, buffer: Buffer, state: object) -> None:
    method = getattr(widget, "render_ref", None)
    if method is None:
        raise TypeError("stateful widget must provide render_ref(area, buffer, state)")
    method(area, buffer, state)


@dataclass(frozen=True)
class Wrap:
    trim: bool = False


@dataclass(frozen=True)
class Clear:
    style: Style = Style()

    def render(self, area: Rect, buffer: Buffer) -> None:
        buffer.fill(area, Cell(" ", self.style))


class Borders(IntFlag):
    NONE = 0
    LEFT = 1
    RIGHT = 2
    TOP = 4
    BOTTOM = 8
    ALL = LEFT | RIGHT | TOP | BOTTOM


Borders.None_ = Borders.NONE
Borders.Left = Borders.LEFT
Borders.Right = Borders.RIGHT
Borders.Top = Borders.TOP
Borders.Bottom = Borders.BOTTOM
Borders.All = Borders.ALL


class BorderType(str, Enum):
    PLAIN = "plain"
    Plain = "plain"
    ROUNDED = "rounded"
    Rounded = "rounded"
    DOUBLE = "double"
    Double = "double"
    THICK = "thick"
    Thick = "thick"


@dataclass(frozen=True)
class Block:
    title: str = ""
    borders: Borders = Borders.NONE
    border_type: BorderType = BorderType.PLAIN
    style: Style = Style()

    @classmethod
    def default(cls) -> "Block":
        return cls()

    def bordered(self) -> "Block":
        return Block(self.title, Borders.ALL, self.border_type, self.style)

    def borders_(self, borders: Borders) -> "Block":
        return Block(self.title, borders, self.border_type, self.style)

    def border_type_(self, border_type: BorderType) -> "Block":
        return Block(self.title, self.borders, border_type, self.style)

    def title_(self, title: object) -> "Block":
        return Block(str(title), self.borders, self.border_type, self.style)

    def style_(self, style: Style) -> "Block":
        return Block(self.title, self.borders, self.border_type, style)

    def inner(self, area: Rect) -> Rect:
        left = 1 if self.borders & Borders.LEFT else 0
        right = 1 if self.borders & Borders.RIGHT else 0
        top = 1 if self.borders & Borders.TOP else 0
        bottom = 1 if self.borders & Borders.BOTTOM else 0
        return Rect.new(area.x + left, area.y + top, max(0, area.width - left - right), max(0, area.height - top - bottom))

    def render(self, area: Rect, buffer: Buffer) -> None:
        if self.borders == Borders.NONE or area.is_empty():
            return
        right = area.right() - 1
        bottom = area.bottom() - 1
        horizontal, vertical, corners = _border_symbols(self.border_type)
        top_left, top_right, bottom_left, bottom_right = corners

        if self.borders & Borders.TOP:
            for x in range(area.x, area.right()):
                buffer.set_symbol(x, area.y, horizontal, self.style)
        if self.borders & Borders.BOTTOM:
            for x in range(area.x, area.right()):
                buffer.set_symbol(x, bottom, horizontal, self.style)
        if self.borders & Borders.LEFT:
            for y in range(area.y, area.bottom()):
                buffer.set_symbol(area.x, y, vertical, self.style)
        if self.borders & Borders.RIGHT:
            for y in range(area.y, area.bottom()):
                buffer.set_symbol(right, y, vertical, self.style)

        if self.borders & Borders.TOP and self.borders & Borders.LEFT:
            buffer.set_symbol(area.x, area.y, top_left, self.style)
        if self.borders & Borders.TOP and self.borders & Borders.RIGHT:
            buffer.set_symbol(right, area.y, top_right, self.style)
        if self.borders & Borders.BOTTOM and self.borders & Borders.LEFT:
            buffer.set_symbol(area.x, bottom, bottom_left, self.style)
        if self.borders & Borders.BOTTOM and self.borders & Borders.RIGHT:
            buffer.set_symbol(right, bottom, bottom_right, self.style)

        if self.title and self.borders & Borders.TOP and area.width > 2:
            title = self.title[: max(0, area.width - 2)]
            buffer.set_span(area.x + 1, area.y, Span.styled(title, self.style), area.width - 2)


@dataclass(frozen=True)
class Paragraph:
    text: Text = field(default_factory=Text)
    style: Style = Style()
    alignment: Alignment = Alignment.LEFT
    wrap: Optional[Wrap] = None
    block: Optional[Block] = None
    scroll: Tuple[int, int] = (0, 0)

    @classmethod
    def raw(cls, content: object) -> "Paragraph":
        return cls(Text.raw(content))

    @classmethod
    def from_lines(cls, lines: Iterable[Union[Line, str]]) -> "Paragraph":
        return cls(Text.from_lines(lines))

    def style_(self, style: Style) -> "Paragraph":
        return Paragraph(self.text, style, self.alignment, self.wrap, self.block, self.scroll)

    def alignment_(self, alignment: Alignment) -> "Paragraph":
        return Paragraph(self.text, self.style, alignment, self.wrap, self.block, self.scroll)

    def wrap_(self, wrap: Wrap) -> "Paragraph":
        return Paragraph(self.text, self.style, self.alignment, wrap, self.block, self.scroll)

    def block_(self, block: Block) -> "Paragraph":
        return Paragraph(self.text, self.style, self.alignment, self.wrap, block, self.scroll)

    def scroll_(self, vertical: int, horizontal: int = 0) -> "Paragraph":
        return Paragraph(self.text, self.style, self.alignment, self.wrap, self.block, (max(0, int(vertical)), max(0, int(horizontal))))

    def render(self, area: Rect, buffer: Buffer) -> None:
        text_area = area
        if self.block is not None:
            self.block.render(area, buffer)
            text_area = self.block.inner(area)
        if text_area.is_empty():
            return

        rows = _wrapped_lines(self.text.lines, text_area.width + self.scroll[1], self.wrap)
        vertical_scroll, horizontal_scroll = self.scroll
        visible = rows[vertical_scroll : vertical_scroll + text_area.height]
        for offset, line in enumerate(visible):
            line = _drop_columns(line, horizontal_scroll)
            x = _aligned_x(text_area, line.width, self.alignment)
            styled = _line_with_base_style(line, self.style)
            buffer.set_line(x, text_area.y + offset, styled, text_area.width)


def _line_with_base_style(line: Line, style: Style) -> Line:
    if style == Style.default():
        return line
    return Line.from_spans(Span(span.content, style.patch(span.style)) for span in line.spans)


def _wrapped_lines(lines: Iterable[Line], width: int, wrap: Optional[Wrap]) -> List[Line]:
    if width <= 0:
        return []
    if wrap is None:
        return [Line.from_spans(_slice_spans(line.spans, width, trim=False)) for line in lines]

    result = []
    for line in lines:
        spans = tuple(_trim_spans(line.spans) if wrap.trim else line.spans)
        current = []
        current_width = 0
        for span in spans:
            for char in span.content:
                if current_width >= width:
                    result.append(Line.from_spans(current))
                    current = []
                    current_width = 0
                current.append(Span(char, span.style))
                current_width += 1
        result.append(Line.from_spans(current))
    return result or [Line.raw("")]


def _slice_spans(spans: Iterable[Span], width: int, trim: bool) -> List[Span]:
    remaining = max(0, width)
    result = []
    source = _trim_spans(spans) if trim else spans
    for span in source:
        if remaining <= 0:
            break
        part = span.content[:remaining]
        if part:
            result.append(Span(part, span.style))
            remaining -= len(part)
    return result


def _trim_spans(spans: Iterable[Span]) -> List[Span]:
    plain = "".join(span.content for span in spans)
    trim_left = len(plain) - len(plain.lstrip())
    trim_right = len(plain.rstrip())
    cursor = 0
    result = []
    for span in spans:
        start = cursor
        end = cursor + len(span.content)
        cursor = end
        keep_start = max(start, trim_left)
        keep_end = min(end, trim_right)
        if keep_start < keep_end:
            result.append(Span(span.content[keep_start - start : keep_end - start], span.style))
    return result


def _drop_columns(line: Line, columns: int) -> Line:
    if columns <= 0:
        return line
    remaining = columns
    result = []
    for span in line.spans:
        if remaining >= len(span.content):
            remaining -= len(span.content)
            continue
        result.append(Span(span.content[remaining:], span.style))
        remaining = 0
    return Line.from_spans(result)


def _aligned_x(area: Rect, width: int, alignment: Alignment) -> int:
    clipped = min(width, area.width)
    if alignment in (Alignment.RIGHT, Alignment.Right):
        return area.x + max(0, area.width - clipped)
    if alignment in (Alignment.CENTER, Alignment.Center):
        return area.x + max(0, (area.width - clipped) // 2)
    return area.x


def _border_symbols(border_type: BorderType) -> Tuple[str, str, Tuple[str, str, str, str]]:
    if border_type in (BorderType.ROUNDED, BorderType.Rounded):
        return ("─", "│", ("╭", "╮", "╰", "╯"))
    if border_type in (BorderType.DOUBLE, BorderType.Double):
        return ("═", "║", ("╔", "╗", "╚", "╝"))
    if border_type in (BorderType.THICK, BorderType.Thick):
        return ("━", "┃", ("┏", "┓", "┗", "┛"))
    return ("─", "│", ("┌", "┐", "└", "┘"))


__all__ = [
    "Block",
    "BorderType",
    "Borders",
    "Clear",
    "Paragraph",
    "StatefulWidgetRef",
    "Widget",
    "WidgetRef",
    "Wrap",
    "render_ref",
    "render_stateful_ref",
]
