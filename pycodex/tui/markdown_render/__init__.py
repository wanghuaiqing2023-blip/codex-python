"""Dependency-light markdown renderer for ``codex-tui::markdown_render``.

Upstream source: ``codex/codex-rs/tui/src/markdown_render.rs``.

Rust uses ``pulldown-cmark`` plus ratatui/syntect primitives.  The Python port
keeps the same public renderer boundary with semantic ``Line``/``Span`` and
``HyperlinkLine`` values, preserving the Codex-owned text flow: width-aware
wrapping, list and blockquote indentation, fenced code preservation, table
fallbacks, web-link annotations, and local-file link display.
"""

from __future__ import annotations

import os
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import unquote, urlparse

from .._porting import RustTuiModule
from ..line_truncation import Line, Span, _display_width
from ..terminal_hyperlinks import (
    HyperlinkLine,
    TerminalHyperlink,
    annotate_web_urls_in_line,
    line_text,
    visible_lines,
)
from ..wrapping import RtOptions, adaptive_wrap_line
from .table_key_value import render_records, should_render_records, wrap_cell

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="markdown_render",
    source="codex/codex-rs/tui/src/markdown_render.rs",
    status="complete",
)

TABLE_COLUMN_GAP = 2
TABLE_CELL_PADDING = 1
TABLE_HEADER_SEPARATOR_CHAR = "─"
TABLE_BODY_SEPARATOR_CHAR = "─"

COLON_LOCATION_SUFFIX_RE = re.compile(r":\d+(?::\d+)?(?:[-–]\d+(?::\d+)?)?$")
HASH_LOCATION_SUFFIX_RE = re.compile(r"^L\d+(?:C\d+)?(?:-L\d+(?:C\d+)?)?$")


@dataclass(frozen=True)
class Text:
    lines: tuple[Line, ...] = ()

    @classmethod
    def from_lines(cls, lines: Iterable[Any]) -> "Text":
        return cls(tuple(_coerce_line(line) for line in lines))


@dataclass(frozen=True)
class MarkdownStyles:
    h1: Any = "bold underlined"
    h2: Any = "bold"
    h3: Any = "bold italic"
    h4: Any = "italic"
    h5: Any = "italic"
    h6: Any = "italic"
    code: Any = "cyan"
    emphasis: Any = "italic"
    strong: Any = "bold"
    strikethrough: Any = "crossed_out"
    ordered_list_marker: Any = "light_blue"
    unordered_list_marker: Any = None
    link: Any = "cyan underlined"
    blockquote: Any = "green"


def default() -> MarkdownStyles:
    return MarkdownStyles()


@dataclass(frozen=True)
class IndentContext:
    prefix: tuple[Span, ...] = ()
    marker: Optional[tuple[Span, ...]] = None
    is_list: bool = False

    @classmethod
    def new(
        cls,
        prefix: Iterable[Any],
        marker: Optional[Iterable[Any]],
        is_list: bool,
    ) -> "IndentContext":
        return cls(tuple(_coerce_span(span) for span in prefix), None if marker is None else tuple(_coerce_span(span) for span in marker), bool(is_list))


@dataclass
class TableCell:
    lines: list[HyperlinkLine] = field(default_factory=list)

    def ensure_line(self) -> None:
        if not self.lines:
            self.lines.append(HyperlinkLine.new(""))

    def push_span(self, span: Any) -> None:
        self.ensure_line()
        self.lines[-1].push_span(_coerce_span(span))

    def push_annotated(self, appended: HyperlinkLine) -> None:
        self.ensure_line()
        shift = self.lines[-1].width()
        self.lines[-1].line = Line((*self.lines[-1].line.spans, *appended.line.spans))
        self.lines[-1].hyperlinks.extend(
            TerminalHyperlink(range(link.columns.start + shift, link.columns.stop + shift), link.destination)
            for link in appended.hyperlinks
        )

    def hard_break(self) -> None:
        self.lines.append(HyperlinkLine.new(""))

    def plain_text(self) -> str:
        return " ".join(line_text(line.line) for line in self.lines)


@dataclass(frozen=True)
class TableBodyRow:
    cells: tuple[TableCell, ...]
    has_table_pipe_syntax: bool = False


@dataclass
class TableState:
    alignments: list[str] = field(default_factory=list)
    header: Optional[list[TableCell]] = None
    rows: list[TableBodyRow] = field(default_factory=list)

    @classmethod
    def new(cls, alignments: Iterable[Any]) -> "TableState":
        return cls([str(alignment).lower() for alignment in alignments])


@dataclass(frozen=True)
class RenderedTableLines:
    table_lines: tuple[HyperlinkLine, ...] = ()
    table_lines_prewrapped: bool = False
    spillover_lines: tuple[HyperlinkLine, ...] = ()


class TableColumnKind(Enum):
    NARRATIVE = "narrative"
    TOKEN_HEAVY = "token_heavy"
    COMPACT = "compact"


@dataclass(frozen=True)
class TableColumnMetrics:
    max_width: int
    header_token_width: int
    body_token_width: int
    kind: TableColumnKind


@dataclass(frozen=True)
class LinkState:
    destination: str
    show_destination: bool
    local_target_display: Optional[str] = None


def render_markdown_text(input: str) -> Text:
    return render_markdown_text_with_width(input, None)


def render_markdown_text_with_width(input: str, width: Optional[int] = None) -> Text:
    return render_markdown_text_with_width_and_cwd(input, width, Path.cwd())


def render_markdown_text_with_width_and_cwd(
    input: str,
    width: Optional[int] = None,
    cwd: Any = None,
) -> Text:
    return Text.from_lines(visible_lines(render_markdown_lines_with_width_and_cwd(input, width, cwd)))


def render_markdown_lines_with_width_and_cwd(
    input: str,
    width: Optional[int] = None,
    cwd: Any = None,
) -> list[HyperlinkLine]:
    return Writer.new(str(input), width, cwd).run()


def should_render_link_destination(dest_url: str) -> bool:
    return not is_local_path_like_link(dest_url)


@dataclass
class Writer:
    input: str
    wrap_width: Optional[int] = None
    cwd: Optional[Path] = None
    text: list[HyperlinkLine] = field(default_factory=list)
    styles: MarkdownStyles = field(default_factory=MarkdownStyles)

    @classmethod
    def new(cls, input: str, width: Optional[int] = None, cwd: Any = None) -> "Writer":
        return cls(str(input), None if width is None else max(1, int(width)), None if cwd is None else Path(cwd))

    def run(self) -> list[HyperlinkLine]:
        self.text = _render_blocks(self.input, self.wrap_width, self.cwd)
        return self.text

    def handle_event(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def prepare_for_event(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def start_tag(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def end_tag(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def start_paragraph(self) -> None:
        return None

    def end_paragraph(self) -> None:
        return None

    def start_heading(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def end_heading(self) -> None:
        return None

    def start_blockquote(self) -> None:
        return None

    def end_blockquote(self) -> None:
        return None

    def text_event(self, text: str) -> None:
        self.push_line(text)

    def text(self, text: str) -> None:  # type: ignore[no-redef]
        self.push_line(text)

    def code(self, text: str) -> None:
        self.push_span(Span(str(text), self.styles.code))

    def html(self, text: str) -> None:
        self.push_line(text)

    def hard_break(self) -> None:
        self.push_blank_line()

    def soft_break(self) -> None:
        self.push_blank_line()

    def start_list(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def end_list(self) -> None:
        return None

    def start_item(self) -> None:
        return None

    def start_codeblock(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def end_codeblock(self) -> None:
        return None

    def start_table(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def end_table(self) -> None:
        return None

    def start_table_head(self) -> None:
        return None

    def end_table_head(self) -> None:
        return None

    def start_table_row(self) -> None:
        return None

    def has_table_row_boundary_pipe(self, row_source: str) -> bool:
        return str(row_source).strip().startswith("|") and str(row_source).strip().endswith("|")

    def end_table_row(self) -> None:
        return None

    def start_table_cell(self) -> None:
        return None

    def end_table_cell(self) -> None:
        return None

    def in_table_cell(self) -> bool:
        return False

    def push_span_to_table_cell(self, span: Any) -> None:
        self.push_span(span)

    def push_table_cell_hard_break(self) -> None:
        self.hard_break()

    def push_text_to_table_cell(self, text: str) -> None:
        self.push_line(text)

    def push_text_spans_to_table_cell(self, spans: Iterable[Any]) -> None:
        self.push_line(Line.from_spans(spans))

    def render_table_lines(self, table_state: TableState) -> RenderedTableLines:
        lines = _render_table(
            [_cell_text(cell) for cell in (table_state.header or [])],
            [[_cell_text(cell) for cell in row.cells] for row in table_state.rows],
            self.wrap_width,
        )
        return RenderedTableLines(tuple(lines), True, ())

    def normalize_row(self, row: Sequence[Any], column_count: int) -> list[Any]:
        values = list(row[:column_count])
        values.extend("" for _ in range(max(0, column_count - len(values))))
        return values

    def available_table_width(self) -> Optional[int]:
        return self.wrap_width

    def available_record_width(self) -> Optional[int]:
        return self.wrap_width

    def compute_column_widths(
        self,
        header: Sequence[Any],
        rows: Sequence[Sequence[Any]],
        _alignments: Sequence[Any] = (),
        available_width: Optional[int] = None,
    ) -> Optional[list[int]]:
        metrics = self.collect_table_column_metrics(header, rows)
        column_count = len(header)
        if column_count == 0:
            return []
        natural = [max(3, metric.max_width) for metric in metrics]
        total = sum(natural) + TABLE_COLUMN_GAP * max(0, column_count - 1)
        limit = self.wrap_width if available_width is None else available_width
        if limit is None or total <= limit:
            return natural
        if limit < column_count * 3 + TABLE_COLUMN_GAP * max(0, column_count - 1):
            return None
        widths = natural[:]
        while sum(widths) + TABLE_COLUMN_GAP * max(0, column_count - 1) > limit:
            index = self.next_column_to_shrink(metrics, widths)
            if widths[index] <= 3:
                return None
            widths[index] -= 1
        return widths

    def collect_table_column_metrics(self, header: Sequence[Any], rows: Sequence[Sequence[Any]]) -> list[TableColumnMetrics]:
        metrics: list[TableColumnMetrics] = []
        for column, heading in enumerate(header):
            body = [str(row[column]) for row in rows if column < len(row)]
            all_values = [str(heading), *body]
            max_width = max((_display_width(value) for value in all_values), default=0)
            header_token = longest_token_width(str(heading))
            body_token = max((longest_token_width(value) for value in body), default=0)
            avg_words = (sum(len(value.split()) for value in body) / len(body)) if body else 0
            avg_width = (sum(_display_width(value) for value in body) / len(body)) if body else 0
            if body_token >= 24 or any(_looks_token_heavy(value) for value in body):
                kind = TableColumnKind.TOKEN_HEAVY
            elif avg_words >= 4 or avg_width >= 28:
                kind = TableColumnKind.NARRATIVE
            else:
                kind = TableColumnKind.COMPACT
            metrics.append(TableColumnMetrics(max_width, header_token, body_token, kind))
        return metrics

    def preferred_column_floor(self, metrics: TableColumnMetrics) -> int:
        if metrics.kind is TableColumnKind.COMPACT:
            return max(3, min(metrics.max_width, max(metrics.header_token_width, metrics.body_token_width)))
        return 16

    def next_column_to_shrink(self, metrics: Sequence[TableColumnMetrics], widths: Sequence[int]) -> int:
        return max(
            range(len(widths)),
            key=lambda i: (widths[i] - self.preferred_column_floor(metrics[i]), -self.column_shrink_priority(metrics[i].kind)),
        )

    def column_shrink_priority(self, kind: TableColumnKind) -> int:
        return {TableColumnKind.TOKEN_HEAVY: 0, TableColumnKind.NARRATIVE: 1, TableColumnKind.COMPACT: 2}[kind]

    def render_table_separator(self, widths: Sequence[int]) -> HyperlinkLine:
        return HyperlinkLine.new((" " * TABLE_COLUMN_GAP).join(TABLE_HEADER_SEPARATOR_CHAR * width for width in widths))

    def render_table_row(self, cells: Sequence[Any], widths: Sequence[int]) -> list[HyperlinkLine]:
        wrapped = [wrap_cell(cell, width) for cell, width in zip(cells, widths)]
        height = max((len(lines) for lines in wrapped), default=1)
        rows: list[HyperlinkLine] = []
        for row_index in range(height):
            parts = []
            for cell_lines, width in zip(wrapped, widths):
                text = line_text(cell_lines[row_index].line) if row_index < len(cell_lines) else ""
                parts.append(text + " " * max(0, width - _display_width(text)))
            rows.append(HyperlinkLine.new((" " * TABLE_COLUMN_GAP).join(parts).rstrip()))
        return rows

    def render_table_pipe_fallback(self, rows: Sequence[Sequence[str]]) -> list[HyperlinkLine]:
        return [HyperlinkLine.new("| " + " | ".join(row) + " |") for row in rows]

    def wrap_cell(self, cell: Any, width: int) -> list[HyperlinkLine]:
        return wrap_cell(cell, width)

    def is_spillover_row(self, row: Sequence[str]) -> bool:
        return len(row) == 1 and bool(row and str(row[0]).strip())

    def first_non_empty_only_text(self, row: Sequence[str]) -> Optional[str]:
        non_empty = [cell for cell in row if str(cell).strip()]
        return non_empty[0] if len(non_empty) == 1 else None

    def looks_like_html_content(self, text: str) -> bool:
        return looks_like_html_content(text)

    def looks_like_html_label_line(self, text: str) -> bool:
        return looks_like_html_label_line(text)

    def spans_display_width(self, spans: Iterable[Any]) -> int:
        return sum(_display_width(_coerce_span(span).content) for span in spans)

    def line_display_width(self, line: Any) -> int:
        return _display_width(line_text(_coerce_line(line)))

    def cell_display_width(self, cell: Any) -> int:
        return _display_width(_cell_text(cell))

    def longest_token_width(self, text: str) -> int:
        return longest_token_width(text)

    def push_inline_style(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def pop_inline_style(self) -> None:
        return None

    def push_link(self, destination: str) -> LinkState:
        return LinkState(destination, should_render_link_destination(destination), render_local_link_target(destination, self.cwd))

    def pop_link(self) -> None:
        return None

    def suppressing_local_link_label(self) -> bool:
        return False

    def flush_current_line(self) -> None:
        return None

    def is_blockquote_active(self) -> bool:
        return False

    def push_prewrapped_line(self, line: Any) -> None:
        self.text.append(_coerce_hyperlink_line(line))

    def push_line(self, line: Any) -> None:
        self.text.extend(_wrap_hyperlink_line(_coerce_hyperlink_line(line), self.wrap_width))

    def push_hyperlink_line(self, line: HyperlinkLine) -> None:
        self.push_line(line)

    def push_span(self, span: Any) -> None:
        self.push_line(Line.from_spans([span]))

    def push_annotated(self, line: HyperlinkLine) -> None:
        self.push_line(line)

    def push_text_spans(self, spans: Iterable[Any]) -> None:
        self.push_line(Line.from_spans(spans))

    def push_blank_line(self) -> None:
        self.text.append(HyperlinkLine.new(""))

    def push_output_line(self, line: Any) -> None:
        self.push_line(line)

    def prefix_spans(self) -> tuple[Span, ...]:
        return ()


def new(input: str, width: Optional[int] = None, cwd: Any = None) -> Writer:
    return Writer.new(input, width, cwd)


def run(writer: Writer) -> list[HyperlinkLine]:
    return writer.run()


def handle_event(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.handle_event(*args, **kwargs)


def prepare_for_event(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.prepare_for_event(*args, **kwargs)


def start_tag(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.start_tag(*args, **kwargs)


def end_tag(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.end_tag(*args, **kwargs)


def start_paragraph(writer: Writer) -> None:
    return writer.start_paragraph()


def end_paragraph(writer: Writer) -> None:
    return writer.end_paragraph()


def start_heading(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.start_heading(*args, **kwargs)


def end_heading(writer: Writer) -> None:
    return writer.end_heading()


def start_blockquote(writer: Writer) -> None:
    return writer.start_blockquote()


def end_blockquote(writer: Writer) -> None:
    return writer.end_blockquote()


def text(writer: Writer, value: str) -> None:
    return writer.text(value)


def code(writer: Writer, value: str) -> None:
    return writer.code(value)


def html(writer: Writer, value: str) -> None:
    return writer.html(value)


def hard_break(writer: Writer) -> None:
    return writer.hard_break()


def soft_break(writer: Writer) -> None:
    return writer.soft_break()


def start_list(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.start_list(*args, **kwargs)


def end_list(writer: Writer) -> None:
    return writer.end_list()


def start_item(writer: Writer) -> None:
    return writer.start_item()


def start_codeblock(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.start_codeblock(*args, **kwargs)


def end_codeblock(writer: Writer) -> None:
    return writer.end_codeblock()


def start_table(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.start_table(*args, **kwargs)


def end_table(writer: Writer) -> None:
    return writer.end_table()


def start_table_head(writer: Writer) -> None:
    return writer.start_table_head()


def end_table_head(writer: Writer) -> None:
    return writer.end_table_head()


def start_table_row(writer: Writer) -> None:
    return writer.start_table_row()


def has_table_row_boundary_pipe(writer: Writer, row_source: str) -> bool:
    return writer.has_table_row_boundary_pipe(row_source)


def end_table_row(writer: Writer) -> None:
    return writer.end_table_row()


def start_table_cell(writer: Writer) -> None:
    return writer.start_table_cell()


def end_table_cell(writer: Writer) -> None:
    return writer.end_table_cell()


def in_table_cell(writer: Writer) -> bool:
    return writer.in_table_cell()


def push_span_to_table_cell(writer: Writer, span: Any) -> None:
    return writer.push_span_to_table_cell(span)


def push_table_cell_hard_break(writer: Writer) -> None:
    return writer.push_table_cell_hard_break()


def push_text_to_table_cell(writer: Writer, value: str) -> None:
    return writer.push_text_to_table_cell(value)


def push_text_spans_to_table_cell(writer: Writer, spans: Iterable[Any]) -> None:
    return writer.push_text_spans_to_table_cell(spans)


def render_table_lines(writer: Writer, table_state: TableState) -> RenderedTableLines:
    return writer.render_table_lines(table_state)


def normalize_row(row: Sequence[Any], column_count: int) -> list[Any]:
    return Writer("").normalize_row(row, column_count)


def available_table_width(writer: Writer) -> Optional[int]:
    return writer.available_table_width()


def available_record_width(writer: Writer) -> Optional[int]:
    return writer.available_record_width()


def compute_column_widths(header: Sequence[Any], rows: Sequence[Sequence[Any]], width: Optional[int] = None) -> Optional[list[int]]:
    return Writer("", width).compute_column_widths(header, rows)


def collect_table_column_metrics(header: Sequence[Any], rows: Sequence[Sequence[Any]]) -> list[TableColumnMetrics]:
    return Writer("").collect_table_column_metrics(header, rows)


def preferred_column_floor(metrics: TableColumnMetrics) -> int:
    return Writer("").preferred_column_floor(metrics)


def next_column_to_shrink(metrics: Sequence[TableColumnMetrics], widths: Sequence[int]) -> int:
    return Writer("").next_column_to_shrink(metrics, widths)


def column_shrink_priority(kind: TableColumnKind) -> int:
    return Writer("").column_shrink_priority(kind)


def render_table_separator(widths: Sequence[int]) -> HyperlinkLine:
    return Writer("").render_table_separator(widths)


def render_table_row(cells: Sequence[Any], widths: Sequence[int]) -> list[HyperlinkLine]:
    return Writer("").render_table_row(cells, widths)


def render_table_pipe_fallback(rows: Sequence[Sequence[str]]) -> list[HyperlinkLine]:
    return Writer("").render_table_pipe_fallback(rows)


def row_to_pipe_line(row: Sequence[str]) -> str:
    return "| " + " | ".join(row) + " |"


def alignments_to_pipe_delimiter(alignments: Sequence[str]) -> str:
    parts = []
    for alignment in alignments:
        value = str(alignment).lower()
        if value == "left":
            parts.append(":---")
        elif value == "right":
            parts.append("---:")
        elif value == "center":
            parts.append(":---:")
        else:
            parts.append("---")
    return "| " + " | ".join(parts) + " |"


def is_spillover_row(row: Sequence[str]) -> bool:
    return Writer("").is_spillover_row(row)


def first_non_empty_only_text(row: Sequence[str]) -> Optional[str]:
    return Writer("").first_non_empty_only_text(row)


def looks_like_html_content(value: str) -> bool:
    text_value = str(value).strip()
    return bool(re.search(r"<[A-Za-z][^>]*>", text_value))


def looks_like_html_label_line(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9 _-]{0,40}:$", str(value).strip()))


def spans_display_width(spans: Iterable[Any]) -> int:
    return Writer("").spans_display_width(spans)


def line_display_width(line: Any) -> int:
    return Writer("").line_display_width(line)


def cell_display_width(cell: Any) -> int:
    return Writer("").cell_display_width(cell)


def longest_token_width(text: str) -> int:
    return max((_display_width(token) for token in str(text).split()), default=0)


def push_inline_style(writer: Writer, *args: Any, **kwargs: Any) -> None:
    return writer.push_inline_style(*args, **kwargs)


def pop_inline_style(writer: Writer) -> None:
    return writer.pop_inline_style()


def push_link(writer: Writer, destination: str) -> LinkState:
    return writer.push_link(destination)


def pop_link(writer: Writer) -> None:
    return writer.pop_link()


def suppressing_local_link_label(writer: Writer) -> bool:
    return writer.suppressing_local_link_label()


def flush_current_line(writer: Writer) -> None:
    return writer.flush_current_line()


def is_blockquote_active(writer: Writer) -> bool:
    return writer.is_blockquote_active()


def push_prewrapped_line(writer: Writer, line: Any) -> None:
    return writer.push_prewrapped_line(line)


def push_line(writer: Writer, line: Any) -> None:
    return writer.push_line(line)


def push_hyperlink_line(writer: Writer, line: HyperlinkLine) -> None:
    return writer.push_hyperlink_line(line)


def push_span(writer: Writer, span: Any) -> None:
    return writer.push_span(span)


def push_annotated(writer: Writer, line: HyperlinkLine) -> None:
    return writer.push_annotated(line)


def push_text_spans(writer: Writer, spans: Iterable[Any]) -> None:
    return writer.push_text_spans(spans)


def push_blank_line(writer: Writer) -> None:
    return writer.push_blank_line()


def push_output_line(writer: Writer, line: Any) -> None:
    return writer.push_output_line(line)


def prefix_spans(writer: Writer) -> tuple[Span, ...]:
    return writer.prefix_spans()


def is_local_path_like_link(dest_url: str) -> bool:
    value = str(dest_url)
    return (
        value.startswith("file://")
        or value.startswith("/")
        or value.startswith("~/")
        or value.startswith("./")
        or value.startswith("../")
        or value.startswith("\\\\")
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    )


def render_local_link_target(dest_url: str, cwd: Any = None) -> Optional[str]:
    parsed = parse_local_link_target(dest_url)
    if parsed is None:
        return None
    path_text, location_suffix = parsed
    rendered = display_local_link_path(path_text, None if cwd is None else Path(cwd))
    return rendered + (location_suffix or "")


def parse_local_link_target(dest_url: str) -> Optional[tuple[str, Optional[str]]]:
    value = str(dest_url)
    if value.startswith("file://"):
        parsed = urlparse(value)
        path_text = file_url_to_local_path_text(value)
        if path_text is None:
            return None
        suffix = normalize_hash_location_suffix_fragment(parsed.fragment) if parsed.fragment else None
        return path_text, suffix

    path_text = value
    suffix = None
    if "#" in value:
        candidate, fragment = value.rsplit("#", 1)
        normalized = normalize_hash_location_suffix_fragment(fragment)
        if normalized is not None:
            path_text = candidate
            suffix = normalized
    if suffix is None:
        colon_suffix = extract_colon_location_suffix(path_text)
        if colon_suffix is not None:
            path_text = path_text[: -len(colon_suffix)]
            suffix = colon_suffix
    return expand_local_link_path(unquote(path_text)), suffix


def normalize_hash_location_suffix_fragment(fragment: str) -> Optional[str]:
    if not HASH_LOCATION_SUFFIX_RE.match(str(fragment)):
        return None
    return "#" + str(fragment)


def extract_colon_location_suffix(path_text: str) -> Optional[str]:
    match = COLON_LOCATION_SUFFIX_RE.search(str(path_text))
    return match.group(0) if match and match.end() == len(str(path_text)) else None


def expand_local_link_path(path_text: str) -> str:
    value = str(path_text)
    if value.startswith("~/"):
        return normalize_local_link_path_text(str(Path.home() / value[2:]))
    return normalize_local_link_path_text(value)


def file_url_to_local_path_text(dest_url: str) -> Optional[str]:
    parsed = urlparse(str(dest_url))
    if parsed.scheme != "file":
        return None
    path = unquote(parsed.path or "")
    if parsed.netloc and parsed.netloc != "localhost":
        return normalize_local_link_path_text(f"//{parsed.netloc}{path}")
    if re.match(r"^/[A-Za-z]:/", path):
        path = path[1:]
    return normalize_local_link_path_text(path)


def normalize_local_link_path_text(path_text: str) -> str:
    value = str(path_text).replace("\\", "/")
    if value.startswith("//"):
        return "//" + value[2:].lstrip("/")
    return value


def is_absolute_local_link_path(path_text: str) -> bool:
    value = normalize_local_link_path_text(path_text)
    return value.startswith("/") or value.startswith("//") or bool(re.match(r"^[A-Za-z]:/", value))


def trim_trailing_local_path_separator(path_text: str) -> str:
    value = normalize_local_link_path_text(path_text)
    if value in {"/", "//"} or re.match(r"^[A-Za-z]:/$", value):
        return value
    return value.rstrip("/")


def strip_local_path_prefix(path_text: str, cwd_text: str) -> Optional[str]:
    path_value = trim_trailing_local_path_separator(path_text)
    cwd_value = trim_trailing_local_path_separator(cwd_text)
    if path_value == cwd_value:
        return None
    if cwd_value in {"/", "//"}:
        return path_value.lstrip("/")
    prefix = cwd_value + "/"
    if path_value.startswith(prefix):
        return path_value[len(prefix) :]
    return None


def display_local_link_path(path_text: str, cwd: Optional[Path] = None) -> str:
    value = normalize_local_link_path_text(path_text)
    if not is_absolute_local_link_path(value):
        return value
    if cwd is not None:
        stripped = strip_local_path_prefix(value, normalize_local_link_path_text(os.fspath(cwd)))
        if stripped is not None:
            return stripped
    return value


def lines_to_strings(text: Any) -> list[str]:
    lines = getattr(text, "lines", text)
    return [line_text(_coerce_line(line)) for line in lines]


def wraps_plain_text_when_width_provided() -> bool:
    return lines_to_strings(render_markdown_text_with_width("hello world", 7)) == ["hello", "world"]


def wraps_list_items_preserving_indent() -> bool:
    return lines_to_strings(render_markdown_text_with_width("- alpha beta gamma", 10)) == ["- alpha", "  beta", "  gamma"]


def wraps_nested_lists() -> bool:
    return lines_to_strings(render_markdown_text_with_width("- outer\n  - inner item", 12)) == ["- outer", "  - inner", "    item"]


def wraps_ordered_lists() -> bool:
    return lines_to_strings(render_markdown_text_with_width("1. alpha beta gamma", 10)) == ["1. alpha", "   beta", "   gamma"]


def wraps_blockquotes() -> bool:
    return lines_to_strings(render_markdown_text_with_width("> alpha beta gamma", 12)) == ["> alpha", "> beta", "> gamma"]


def wraps_blockquotes_inside_lists() -> bool:
    return lines_to_strings(render_markdown_text_with_width("- > alpha beta", 12)) == ["- > alpha", "  beta"]


def wraps_list_items_containing_blockquotes() -> bool:
    return wraps_blockquotes_inside_lists()


def does_not_wrap_code_blocks() -> bool:
    return lines_to_strings(render_markdown_text_with_width("```text\nalpha beta gamma\n```", 5)) == ["alpha beta gamma"]


def does_not_split_long_url_like_token_without_scheme() -> bool:
    return lines_to_strings(render_markdown_text_with_width("aaaaaaaaaaaaaaaa", 5)) == ["aaaaaaaaaaaaaaaa"]


def fenced_code_info_string_with_metadata_highlights() -> bool:
    return lines_to_strings(render_markdown_text("```python title=x\nprint(1)\n```")) == ["print(1)"]


def crlf_code_block_no_extra_blank_lines() -> bool:
    return lines_to_strings(render_markdown_text("```text\r\na\r\n```")) == ["a"]


def wrap_cell_preserves_hard_break_lines() -> bool:
    cell = TableCell()
    cell.push_span("alpha beta")
    cell.hard_break()
    cell.push_span("gamma")
    return [line_text(line.line) for line in wrap_cell(cell, 6)] == ["alpha", "beta", "gamma"]


def make_cell(text_value: str) -> TableCell:
    cell = TableCell()
    cell.push_span(text_value)
    return cell


def make_body_row(*values: str) -> TableBodyRow:
    return TableBodyRow(tuple(make_cell(value) for value in values), True)


def _render_blocks(markdown: str, width: Optional[int], cwd: Optional[Path]) -> list[HyperlinkLine]:
    raw_lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[HyperlinkLine] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if not paragraph:
            return
        source_lines = [part for part in paragraph if part.strip()]
        paragraph.clear()
        for source_line in source_lines:
            out.extend(
                _wrap_hyperlink_line(
                    _inline_hyperlink_line(source_line.strip(), cwd),
                    width,
                )
            )

    while index < len(raw_lines):
        line = raw_lines[index]
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if in_code:
                out.extend(HyperlinkLine.new(code_line) for code_line in code_lines)
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                in_code = True
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            if out and line == "":
                out.append(HyperlinkLine.new(""))
            index += 1
            continue
        table = _try_parse_table(raw_lines, index)
        if table is not None:
            flush_paragraph()
            header, rows, consumed = table
            out.extend(_render_table(header, rows, width))
            index += consumed
            continue
        if _split_table_row(line) is not None:
            # pulldown-cmark keeps a speculative table header as a standalone
            # paragraph until a delimiter confirms table structure.
            flush_paragraph()
            out.extend(_wrap_hyperlink_line(_inline_hyperlink_line(line.strip(), cwd), width))
            index += 1
            continue
        list_match = re.match(r"^(\s*)((?:[-*+])|\d+[.)])\s+(.*)$", line)
        if list_match:
            flush_paragraph()
            indent, marker, body = list_match.groups()
            prefix = f"{indent}{marker} "
            subsequent = " " * _display_width(prefix)
            out.extend(_wrap_with_prefix(_inline_hyperlink_line(body, cwd), width, prefix, subsequent))
            index += 1
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            quote = re.sub(r"^>\s?", "", stripped)
            out.extend(_wrap_with_prefix(_inline_hyperlink_line(quote, cwd), width, "> ", "> "))
            index += 1
            continue
        paragraph.append(line)
        index += 1

    flush_paragraph()
    if in_code:
        out.extend(HyperlinkLine.new(code_line) for code_line in code_lines)
    while out and line_text(out[-1].line) == "":
        out.pop()
    return out


def _try_parse_table(lines: Sequence[str], index: int) -> Optional[tuple[list[str], list[list[str]], int]]:
    if index + 1 >= len(lines):
        return None
    header = _split_table_row(lines[index])
    delimiter = _split_table_row(lines[index + 1])
    if header is None or delimiter is None or not delimiter or not all(re.match(r"^:?-{3,}:?$", cell.strip()) for cell in delimiter):
        return None
    rows: list[list[str]] = []
    cursor = index + 2
    while cursor < len(lines):
        row = _split_table_row(lines[cursor])
        if row is None:
            break
        rows.append(row)
        cursor += 1
    return header, rows, cursor - index


def _split_table_row(line: str) -> Optional[list[str]]:
    if "|" not in line:
        return None
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _render_table(header: Sequence[str], rows: Sequence[Sequence[str]], width: Optional[int]) -> list[HyperlinkLine]:
    writer = Writer("", width)
    normalized_rows = [writer.normalize_row(row, len(header)) for row in rows]
    metrics = writer.collect_table_column_metrics(header, normalized_rows)
    column_widths = writer.compute_column_widths(header, normalized_rows)
    if column_widths is None or should_render_records(header, column_widths, metrics):
        return render_records(header, normalized_rows, metrics, width)
    out: list[HyperlinkLine] = []
    out.extend(writer.render_table_row(header, column_widths))
    out.append(writer.render_table_separator(column_widths))
    for row in normalized_rows:
        out.extend(writer.render_table_row(row, column_widths))
    return out


def _inline_hyperlink_line(text_value: str, cwd: Optional[Path]) -> HyperlinkLine:
    line = HyperlinkLine.new("")
    cursor = 0
    pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for match in pattern.finditer(text_value):
        if match.start() > cursor:
            line.push_span(_strip_inline_markup(text_value[cursor : match.start()]))
        label, destination = match.group(1), match.group(2)
        if should_render_link_destination(destination):
            visible = _strip_inline_markup(label)
            start = line.width()
            line.push_span(visible)
            end = line.width()
            if end > start:
                line.hyperlinks.append(TerminalHyperlink(range(start, end), destination))
            if destination and destination != visible:
                line.push_span(f" ({destination})")
        else:
            target = render_local_link_target(destination, cwd) or destination
            line.push_span(target)
        cursor = match.end()
    if cursor < len(text_value):
        line.push_span(_strip_inline_markup(text_value[cursor:]))
    return annotate_web_urls_in_line(line.line) if not line.hyperlinks else line


def _strip_inline_markup(value: str) -> str:
    text_value = re.sub(r"`([^`]*)`", r"\1", str(value))
    text_value = re.sub(r"\*\*([^*]+)\*\*", r"\1", text_value)
    text_value = re.sub(r"(?<!\w)__([^_]+)__(?!\w)", r"\1", text_value)
    text_value = re.sub(r"\*([^*]+)\*", r"\1", text_value)
    # pulldown-cmark/CommonMark treats intraword underscores as literal text.
    text_value = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text_value)
    text_value = re.sub(r"~~([^~]+)~~", r"\1", text_value)
    return text_value


def _wrap_with_prefix(line: HyperlinkLine, width: Optional[int], initial_prefix: str, subsequent_prefix: str) -> list[HyperlinkLine]:
    text_value = line_text(line.line)
    if width is None:
        return [HyperlinkLine.new(initial_prefix + text_value)]
    initial_width = max(1, width - _display_width(initial_prefix))
    subsequent_width = max(1, width - _display_width(subsequent_prefix))
    chunks = _wrap_plain_text(text_value, initial_width)
    if len(chunks) > 1:
        rest: list[str] = []
        for chunk in chunks[1:]:
            rest.extend(_wrap_plain_text(chunk, subsequent_width))
        chunks = [chunks[0], *rest]
    return [HyperlinkLine.new((initial_prefix if idx == 0 else subsequent_prefix) + chunk) for idx, chunk in enumerate(chunks)]


def _wrap_hyperlink_line(line: HyperlinkLine, width: Optional[int]) -> list[HyperlinkLine]:
    if width is None or line.width() <= width:
        return [line]
    wrapped = adaptive_wrap_line(line.line, RtOptions.new(width))
    return [HyperlinkLine.new(wrapped_line) for wrapped_line in wrapped]


def _wrap_plain_text(text_value: str, width: int) -> list[str]:
    safe_width = max(1, int(width))
    if _display_width(text_value) <= safe_width:
        return [text_value]
    if " " not in text_value and "\t" not in text_value:
        return [text_value]
    return textwrap.wrap(
        text_value,
        width=safe_width,
        break_long_words=False,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
    ) or [""]


def _looks_token_heavy(value: str) -> bool:
    return any(token.startswith(("http://", "https://", "/", "./", "../")) or len(token) >= 24 for token in value.split())


def _cell_text(cell: Any) -> str:
    if isinstance(cell, TableCell):
        return cell.plain_text()
    if isinstance(cell, HyperlinkLine):
        return line_text(cell.line)
    if isinstance(cell, Line):
        return line_text(cell)
    return str(cell)


def _coerce_span(span: Any) -> Span:
    if isinstance(span, Span):
        return span
    if isinstance(span, str):
        return Span(span)
    return Span(str(getattr(span, "content", getattr(span, "text", span))), getattr(span, "style", None))


def _coerce_line(line: Any) -> Line:
    if isinstance(line, Line):
        return line
    if isinstance(line, HyperlinkLine):
        return line.line
    if isinstance(line, str):
        return Line.from_text(line)
    spans = getattr(line, "spans", None)
    if spans is not None:
        return Line.from_spans(spans, style=getattr(line, "style", None), alignment=getattr(line, "alignment", None))
    return Line.from_spans(line)


def _coerce_hyperlink_line(line: Any) -> HyperlinkLine:
    if isinstance(line, HyperlinkLine):
        return line
    return HyperlinkLine.new(_coerce_line(line))


__all__ = [
    "COLON_LOCATION_SUFFIX_RE",
    "HASH_LOCATION_SUFFIX_RE",
    "IndentContext",
    "LinkState",
    "MarkdownStyles",
    "RenderedTableLines",
    "RUST_MODULE",
    "TABLE_BODY_SEPARATOR_CHAR",
    "TABLE_CELL_PADDING",
    "TABLE_COLUMN_GAP",
    "TABLE_HEADER_SEPARATOR_CHAR",
    "TableBodyRow",
    "TableCell",
    "TableColumnKind",
    "TableColumnMetrics",
    "TableState",
    "Text",
    "Writer",
    "alignments_to_pipe_delimiter",
    "available_record_width",
    "available_table_width",
    "cell_display_width",
    "code",
    "collect_table_column_metrics",
    "column_shrink_priority",
    "compute_column_widths",
    "crlf_code_block_no_extra_blank_lines",
    "default",
    "display_local_link_path",
    "does_not_split_long_url_like_token_without_scheme",
    "does_not_wrap_code_blocks",
    "end_codeblock",
    "end_heading",
    "end_item",
    "end_list",
    "end_paragraph",
    "end_table",
    "end_table_cell",
    "end_table_head",
    "end_table_row",
    "extract_colon_location_suffix",
    "file_url_to_local_path_text",
    "first_non_empty_only_text",
    "flush_current_line",
    "handle_event",
    "hard_break",
    "html",
    "in_table_cell",
    "is_absolute_local_link_path",
    "is_blockquote_active",
    "is_local_path_like_link",
    "is_spillover_row",
    "line_display_width",
    "lines_to_strings",
    "longest_token_width",
    "looks_like_html_content",
    "looks_like_html_label_line",
    "make_body_row",
    "make_cell",
    "new",
    "normalize_hash_location_suffix_fragment",
    "normalize_local_link_path_text",
    "normalize_row",
    "parse_local_link_target",
    "pop_inline_style",
    "pop_link",
    "prefix_spans",
    "prepare_for_event",
    "preferred_column_floor",
    "push_annotated",
    "push_blank_line",
    "push_hyperlink_line",
    "push_inline_style",
    "push_line",
    "push_link",
    "push_output_line",
    "push_prewrapped_line",
    "push_span",
    "push_span_to_table_cell",
    "push_table_cell_hard_break",
    "push_text_spans",
    "push_text_spans_to_table_cell",
    "push_text_to_table_cell",
    "render_local_link_target",
    "render_markdown_lines_with_width_and_cwd",
    "render_markdown_text",
    "render_markdown_text_with_width",
    "render_markdown_text_with_width_and_cwd",
    "render_table_lines",
    "render_table_pipe_fallback",
    "render_table_row",
    "render_table_separator",
    "row_to_pipe_line",
    "run",
    "should_render_link_destination",
    "soft_break",
    "spans_display_width",
    "start_blockquote",
    "start_codeblock",
    "start_heading",
    "start_item",
    "start_list",
    "start_paragraph",
    "start_table",
    "start_table_cell",
    "start_table_head",
    "start_table_row",
    "strip_local_path_prefix",
    "suppressing_local_link_label",
    "text",
    "trim_trailing_local_path_separator",
    "wrap_cell",
    "wrap_cell_preserves_hard_break_lines",
    "wraps_blockquotes",
    "wraps_blockquotes_inside_lists",
    "wraps_list_items_containing_blockquotes",
    "wraps_list_items_preserving_indent",
    "wraps_nested_lists",
    "wraps_ordered_lists",
    "wraps_plain_text_when_width_provided",
]
