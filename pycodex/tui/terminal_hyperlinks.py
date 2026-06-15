"""Semantic terminal hyperlinks carried separately from visible TUI text.

Upstream source: ``codex/codex-rs/tui/src/terminal_hyperlinks.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse

from ._porting import RustTuiModule
from .line_truncation import Line
from .line_truncation import Span
from .line_truncation import _display_width

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="terminal_hyperlinks",
    source="codex/codex-rs/tui/src/terminal_hyperlinks.rs",
    status="complete",
)



@dataclass(eq=True)
class TerminalHyperlink:
    columns: range
    destination: str


@dataclass
class HyperlinkLine:
    line: Line
    hyperlinks: List[TerminalHyperlink] = field(default_factory=list)

    @classmethod
    def new(cls, line: Any) -> "HyperlinkLine":
        return cls(_coerce_line(line))

    def width(self) -> int:
        return _display_width(line_text(self.line))

    def push_span(self, span: Any, destination: Optional[str] = None) -> None:
        span = span if isinstance(span, Span) else Span(str(span))
        start = self.width()
        end = start + _display_width(span.content)
        self.line = Line((*self.line.spans, span), style=self.line.style, alignment=self.line.alignment)
        if end > start and destination is not None:
            safe = web_destination(destination)
            if safe is not None:
                self.hyperlinks.append(TerminalHyperlink(range(start, end), safe))

    def style(self, style: Any) -> "HyperlinkLine":
        self.line = Line(self.line.spans, style=style, alignment=self.line.alignment)
        return self


@dataclass
class SemanticCell:
    symbol: str = " "
    fg: Any = None
    modifiers: Set[str] = field(default_factory=set)
    skip: bool = False

    def set_symbol(self, symbol: str) -> None:
        self.symbol = symbol


@dataclass(frozen=True)
class SemanticRect:
    x: int
    y: int
    width: int
    height: int

    def positions(self) -> Iterable[Tuple[int, int]]:
        for row in range(self.y, self.y + self.height):
            for column in range(self.x, self.x + self.width):
                yield (column, row)


class SemanticBuffer:
    def __init__(self, area: SemanticRect) -> None:
        self.area = area
        self.cells = {
            (column, row): SemanticCell()
            for row in range(area.y, area.y + area.height)
            for column in range(area.x, area.x + area.width)
        }

    @classmethod
    def from_lines(cls, lines: Iterable[str]) -> "SemanticBuffer":
        line_list = list(lines)
        width = max((len(line) for line in line_list), default=0)
        area = SemanticRect(0, 0, width, len(line_list))
        buf = cls(area)
        for row, text in enumerate(line_list):
            for column, ch in enumerate(text):
                buf.cells[(column, row)].symbol = ch
        return buf

    def cell(self, column: int, row: int) -> SemanticCell:
        return self.cells[(column, row)]


def _coerce_line(line: Any) -> Line:
    if isinstance(line, Line):
        return line
    if isinstance(line, str):
        return Line.from_text(line)
    spans = getattr(line, "spans", None)
    if spans is not None:
        return Line.from_spans(
            spans,
            style=getattr(line, "style", None),
            alignment=getattr(line, "alignment", None),
        )
    return Line.from_spans(line)


def _coerce_hyperlink_line(line: Union[HyperlinkLine, Line, str, Iterable[Any]]) -> HyperlinkLine:
    if isinstance(line, HyperlinkLine):
        return line
    return HyperlinkLine.new(line)


def visible_lines(lines: Iterable[HyperlinkLine]) -> List[Line]:
    return [line.line for line in lines]


def plain_hyperlink_lines(lines: Iterable[Any]) -> List[HyperlinkLine]:
    return [HyperlinkLine.new(line) for line in lines]


def prefix_hyperlink_lines(
    lines: Iterable[HyperlinkLine],
    initial_prefix: Any,
    subsequent_prefix: Any,
) -> List[HyperlinkLine]:
    initial = initial_prefix if isinstance(initial_prefix, Span) else Span(str(initial_prefix))
    subsequent = subsequent_prefix if isinstance(subsequent_prefix, Span) else Span(str(subsequent_prefix))
    out: List[HyperlinkLine] = []
    for index, source in enumerate(lines):
        line = _coerce_hyperlink_line(source)
        prefix = initial if index == 0 else subsequent
        shift = _display_width(prefix.content)
        prefixed = HyperlinkLine(
            Line((prefix, *line.line.spans), style=line.line.style, alignment=line.line.alignment),
            [
                TerminalHyperlink(
                    range(link.columns.start + shift, link.columns.stop + shift),
                    link.destination,
                )
                for link in line.hyperlinks
            ],
        )
        out.append(prefixed)
    return out


def annotate_web_urls(lines: Iterable[Any]) -> List[HyperlinkLine]:
    return [annotate_web_urls_in_line(_coerce_line(line)) for line in lines]


def annotate_web_urls_in_line(line: Any) -> HyperlinkLine:
    coerced = _coerce_line(line)
    out = HyperlinkLine.new(coerced)
    out.hyperlinks = web_links_in_text(line_text(coerced))
    return out


def remap_wrapped_line(
    source: HyperlinkLine,
    wrapped: Iterable[Any],
) -> List[HyperlinkLine]:
    out = plain_hyperlink_lines(wrapped)
    source_text = line_text(source.line)
    source_byte = 0
    source_column = 0

    for index, line in enumerate(out):
        if index > 0:
            remaining = source_text[source_byte:]
            trimmed = remaining.lstrip()
            skipped = len(remaining) - len(trimmed)
            source_column += _display_width(remaining[:skipped])
            source_byte += skipped

        rendered = line_text(line.line)
        remaining = source_text[source_byte:]
        rendered_start = longest_suffix_matching_prefix(rendered, remaining)
        if rendered_start is None:
            continue
        mapped = rendered[rendered_start:]
        output_column = _display_width(rendered[:rendered_start])
        for ch in mapped:
            width = _display_width(ch)
            link = next((link for link in source.hyperlinks if source_column in link.columns), None)
            if link is not None:
                push_link_range(line, range(output_column, output_column + width), link.destination)
            source_column += width
            output_column += width
        source_byte += len(mapped)
    return out


def line_text(line: Union[Line, HyperlinkLine]) -> str:
    line = line.line if isinstance(line, HyperlinkLine) else line
    return "".join(span.content for span in line.spans)


def longest_suffix_matching_prefix(rendered: str, source: str) -> Optional[int]:
    for index in range(len(rendered) + 1):
        if index < len(rendered) and source.startswith(rendered[index:]):
            return index
    return None


def push_link_range(line: HyperlinkLine, columns: range, destination: str) -> None:
    if columns.start == columns.stop:
        return
    if (
        line.hyperlinks
        and line.hyperlinks[-1].destination == destination
        and line.hyperlinks[-1].columns.stop == columns.start
    ):
        previous = line.hyperlinks[-1]
        previous.columns = range(previous.columns.start, columns.stop)
        return
    line.hyperlinks.append(TerminalHyperlink(columns, destination))


def web_links_in_text(text: str) -> List[TerminalHyperlink]:
    links: List[TerminalHyperlink] = []
    search_from = 0
    for raw_token in re.split(r"[ \t\r\n\f\v]+", text):
        if not raw_token:
            continue
        relative_start = text[search_from:].find(raw_token)
        if relative_start < 0:
            continue
        raw_start = search_from + relative_start
        search_from = raw_start + len(raw_token)
        trimmed_start = next(
            (idx for idx, ch in enumerate(raw_token) if not is_leading_punctuation(ch)),
            len(raw_token),
        )
        trimmed_end = trailing_url_end(raw_token[trimmed_start:]) + trimmed_start
        if trimmed_start >= trimmed_end:
            continue
        candidate = raw_token[trimmed_start:trimmed_end]
        destination = web_destination(candidate)
        if destination is None:
            continue
        start = _display_width(text[: raw_start + trimmed_start])
        end = start + _display_width(candidate)
        links.append(TerminalHyperlink(range(start, end), destination))
    return links


def is_leading_punctuation(ch: str) -> bool:
    return ch in "()[]{}<>,.;!'\""


def trailing_url_end(candidate: str) -> int:
    end = len(candidate)
    while end > 0:
        remaining = candidate[:end]
        ch = remaining[-1]
        trim = ch in ",.;!'\"" or (
            ch in ")]}>" and has_unmatched_closing_delimiter(remaining, ch)
        )
        if not trim:
            break
        end -= len(ch)
    return end


def has_unmatched_closing_delimiter(candidate: str, closing: str) -> bool:
    opening_by_closing = {")": "(", "]": "[", "}": "{", ">": "<"}
    opening = opening_by_closing.get(closing)
    if opening is None:
        return False
    return candidate.count(closing) > candidate.count(opening)


def web_destination(destination: str) -> Optional[str]:
    safe_destination = "".join(ch for ch in destination if not unicontrol(ch))
    parsed = urlparse(safe_destination)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.hostname:
        return None
    return safe_destination


def unicontrol(ch: str) -> bool:
    return ord(ch) < 32 or ord(ch) == 127


def osc8_hyperlink(destination: str, text: str) -> str:
    safe_destination = web_destination(destination)
    if safe_destination is None:
        return text
    return f"\x1b]8;;{safe_destination}\x07{text}\x1b]8;;\x07"


def strip_osc8(text: str) -> str:
    stripped: List[str] = []
    index = 0
    while index < len(text):
        if text.startswith("\x1b]8;;", index):
            index += 5
            while index < len(text):
                if text[index] == "\x07":
                    index += 1
                    break
                if text.startswith("\x1b\\", index):
                    index += 2
                    break
                index += 1
            continue
        stripped.append(text[index])
        index += 1
    return "".join(stripped)


def decorate_spans(line: HyperlinkLine) -> List[Span]:
    if not line.hyperlinks:
        return list(line.line.spans)

    out: List[Span] = []
    column = 0
    link_index = 0
    active_link_index: Optional[int] = None
    active_destination: Optional[str] = None
    for span in line.line.spans:
        for ch in span.content:
            width = _display_width(ch)
            while link_index < len(line.hyperlinks) and line.hyperlinks[link_index].columns.stop <= column:
                link_index += 1
            selected = link_index if link_index < len(line.hyperlinks) and column in line.hyperlinks[link_index].columns else None
            if active_link_index != selected:
                if active_destination is not None:
                    append_to_last_span(out, "\x1b]8;;\x07")
                active_destination = (
                    web_destination(line.hyperlinks[selected].destination)
                    if selected is not None
                    else None
                )
                if active_destination is not None:
                    push_styled_content(out, f"\x1b]8;;{active_destination}\x07", span.style)
                active_link_index = selected
            push_styled_content(out, ch, span.style)
            column += width
    if active_destination is not None:
        append_to_last_span(out, "\x1b]8;;\x07")
    return out


def push_styled_content(out: List[Span], content: str, style: Any) -> None:
    if out and out[-1].style == style:
        out[-1] = Span(out[-1].content + content, style)
        return
    out.append(Span(content, style))


def append_to_last_span(out: List[Span], content: str) -> None:
    if out:
        out[-1] = Span(out[-1].content + content, out[-1].style)


def adaptive_wrap_hyperlink_lines(lines: Iterable[HyperlinkLine], options: Any) -> List[HyperlinkLine]:
    from .wrapping import adaptive_wrap_line

    out: List[HyperlinkLine] = []
    for index, line in enumerate(lines):
        line = _coerce_hyperlink_line(line)
        opts = options.clone() if hasattr(options, "clone") else options
        if index > 0 and hasattr(opts, "initial_indent") and hasattr(opts, "subsequent_indent_line"):
            opts = opts.initial_indent(opts.subsequent_indent_line)
        out.extend(remap_wrapped_line(line, adaptive_wrap_line(line.line, opts)))
    return out


def _coerce_rect(area: Any) -> SemanticRect:
    if isinstance(area, SemanticRect):
        return area
    if isinstance(area, tuple):
        return SemanticRect(*area)
    return SemanticRect(
        int(getattr(area, "x")),
        int(getattr(area, "y")),
        int(getattr(area, "width")),
        int(getattr(area, "height")),
    )


def _cell_symbol(cell: Any) -> str:
    symbol = getattr(cell, "symbol", "")
    return symbol() if callable(symbol) else str(symbol)


def _set_cell_symbol(cell: Any, symbol: str) -> None:
    setter = getattr(cell, "set_symbol", None)
    if callable(setter):
        setter(symbol)
    else:
        setattr(cell, "symbol", symbol)


def _buffer_cell(buf: Any, column: int, row: int) -> Any:
    cell_method = getattr(buf, "cell", None)
    if callable(cell_method):
        return cell_method(column, row)
    if hasattr(buf, "cells"):
        return buf.cells[(column, row)]
    return buf[(column, row)]


def mark_buffer_hyperlinks(
    buf: Any,
    area: Any,
    lines: Iterable[HyperlinkLine],
    scroll_rows: int = 0,
) -> None:
    rect = _coerce_rect(area)
    if rect.width == 0:
        return
    logical_row = 0
    for line in lines:
        rendered_lines = _semantic_wrapped_lines(line_text(line), rect.width)
        rendered_height = max(1, len(rendered_lines))
        if not line.hyperlinks:
            logical_row += rendered_height
            continue
        for row_offset, rendered in enumerate(remap_wrapped_line(line, rendered_lines)):
            for link in rendered.hyperlinks:
                for column in link.columns:
                    row = logical_row + row_offset
                    if row < scroll_rows or row - scroll_rows >= rect.height:
                        continue
                    x = rect.x + column
                    y = rect.y + (row - scroll_rows)
                    if x < rect.x or x >= rect.x + rect.width:
                        continue
                    cell = _buffer_cell(buf, x, y)
                    symbol = _cell_symbol(cell)
                    if getattr(cell, "skip", False) or not symbol.strip():
                        continue
                    _set_cell_symbol(cell, osc8_hyperlink(link.destination, symbol))
        logical_row += rendered_height


def _semantic_wrapped_lines(text: str, width: int) -> List[Line]:
    if width <= 0:
        return [Line.from_text("")]
    lines: List[str] = []
    remaining = text
    while _display_width(remaining) > width:
        split = _find_semantic_wrap_split(remaining, width)
        lines.append(remaining[:split])
        remaining = remaining[split:]
    lines.append(remaining)
    return [Line.from_text(line) for line in lines]


def _find_semantic_wrap_split(text: str, width: int) -> int:
    used = 0
    last_space_end: Optional[int] = None
    token_started_after_last_space = False
    for index, ch in enumerate(text):
        next_used = used + _display_width(ch)
        if next_used > width:
            if last_space_end is not None and not token_started_after_last_space:
                return last_space_end
            return index
        used = next_used
        if ch.isspace() and used > 0:
            last_space_end = index + len(ch)
            token_started_after_last_space = False
        else:
            token_started_after_last_space = True
    return len(text)


def mark_url_hyperlink(
    buf: Any,
    area: Any,
    destination: str,
) -> None:
    mark_matching_cells(
        buf,
        area,
        destination,
        lambda cell: getattr(cell, "fg", None) == "cyan"
        and "underlined" in {str(m).lower() for m in getattr(cell, "modifiers", set())},
    )


def mark_underlined_hyperlink(
    buf: Any,
    area: Any,
    destination: str,
) -> None:
    mark_matching_cells(
        buf,
        area,
        destination,
        lambda cell: "underlined" in {str(m).lower() for m in getattr(cell, "modifiers", set())},
    )


def mark_matching_cells(
    buf: Any,
    area: Any,
    destination: str,
    matches: Any,
) -> None:
    if web_destination(destination) is None:
        return
    rect = _coerce_rect(area)
    for column, row in rect.positions():
        cell = _buffer_cell(buf, column, row)
        symbol = _cell_symbol(cell)
        if getattr(cell, "skip", False) or not symbol.strip() or not matches(cell):
            continue
        _set_cell_symbol(cell, osc8_hyperlink(destination, symbol))


__all__ = [
    "HyperlinkLine",
    "RUST_MODULE",
    "SemanticBuffer",
    "SemanticCell",
    "SemanticRect",
    "TerminalHyperlink",
    "adaptive_wrap_hyperlink_lines",
    "annotate_web_urls",
    "annotate_web_urls_in_line",
    "append_to_last_span",
    "decorate_spans",
    "has_unmatched_closing_delimiter",
    "is_leading_punctuation",
    "line_text",
    "longest_suffix_matching_prefix",
    "mark_buffer_hyperlinks",
    "mark_matching_cells",
    "mark_underlined_hyperlink",
    "mark_url_hyperlink",
    "osc8_hyperlink",
    "plain_hyperlink_lines",
    "prefix_hyperlink_lines",
    "push_link_range",
    "push_styled_content",
    "remap_wrapped_line",
    "strip_osc8",
    "trailing_url_end",
    "visible_lines",
    "web_destination",
    "web_links_in_text",
]


