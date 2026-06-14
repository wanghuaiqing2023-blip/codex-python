"""Key/value record rendering for markdown tables.

Upstream source: ``codex/codex-rs/tui/src/markdown_render/table_key_value.rs``.

Rust uses ratatui text primitives; the Python port uses the semantic ``Line``,
``Span`` and ``HyperlinkLine`` models already shared by the TUI modules.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .._porting import RustTuiModule
from ..line_truncation import Line, Span, _display_width
from ..terminal_hyperlinks import HyperlinkLine, TerminalHyperlink, line_text

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="markdown_render::table_key_value",
    source="codex/codex-rs/tui/src/markdown_render/table_key_value.rs",
)

FIELD_LEADING_PADDING = 1
FIELD_GAP = 2
MIN_VALUE_WIDTH = 3
MIN_ALIGNED_COMPACT_VALUE_WIDTH = 12
MIN_ALIGNED_EXPANSIVE_VALUE_WIDTH = 24
MIN_SCANNABLE_NARRATIVE_WIDTH = 12
MIN_SCANNABLE_TOKEN_HEAVY_WIDTH = 12
CRAMPED_EXPANSIVE_CELL_LINES = 4
CATASTROPHIC_NARRATIVE_CELL_LINES = 7
STACKED_VALUE_INDENT = 2
TABLE_BODY_SEPARATOR_CHAR = "─"


def should_render_records(
    rows: Sequence[Sequence[Any]],
    column_widths: Sequence[int],
    metrics: Sequence[Any],
) -> bool:
    """Return whether a table should switch to key/value record rendering."""

    if not rows:
        return False

    affected_rows = 0
    for row in rows:
        fragmented = False
        for cell, width, metric in zip(row, column_widths, metrics):
            kind = _metric_kind(metric)
            if kind == "narrative":
                continue
            has_fragmented_token = any(
                _display_width(token) > int(width)
                for token in _plain_text(cell).split()
            )
            if kind == "compact":
                fragmented = fragmented or has_fragmented_token
            else:
                fragmented = fragmented or (
                    int(width) < MIN_SCANNABLE_TOKEN_HEAVY_WIDTH and has_fragmented_token
                )
        if fragmented or expansive_cells_are_starved(row, column_widths, metrics):
            affected_rows += 1

    threshold = 1 if len(rows) == 1 else max(2, (len(rows) + 2) // 3)
    return affected_rows >= threshold


def expansive_cells_are_starved(
    row: Sequence[Any],
    column_widths: Sequence[int],
    metrics: Sequence[Any],
) -> bool:
    """Detect Rust's cramped expansive-cell cases for record rendering."""

    expansive: list[tuple[str, int, int]] = []
    for cell, width, metric in zip(row, column_widths, metrics):
        kind = _metric_kind(metric)
        if kind == "compact":
            continue
        int_width = int(width)
        expansive.append((kind, int_width, len(wrap_cell(cell, int_width))))

    cramped = sum(1 for _, _, height in expansive if height >= CRAMPED_EXPANSIVE_CELL_LINES)
    if cramped >= 2:
        return True
    return any(
        kind == "narrative"
        and width < MIN_SCANNABLE_NARRATIVE_WIDTH
        and height >= CATASTROPHIC_NARRATIVE_CELL_LINES
        for kind, width, height in expansive
    )


def render_records(
    headers: Sequence[Any],
    rows: Sequence[Sequence[Any]],
    metrics: Sequence[Any],
    available_width: int | None,
    label_style: Any = None,
    separator_style: Any = None,
) -> list[HyperlinkLine]:
    """Render table rows as readable key/value records."""

    label_width = max((_display_width(_plain_text(header)) for header in headers), default=0)
    minimum_value_width = (
        MIN_ALIGNED_EXPANSIVE_VALUE_WIDTH
        if any(_metric_kind(metric) != "compact" for metric in metrics)
        else MIN_ALIGNED_COMPACT_VALUE_WIDTH
    )
    aligned_fields = available_width is None or (
        FIELD_LEADING_PADDING + label_width + FIELD_GAP + minimum_value_width <= available_width
    )

    out: list[HyperlinkLine] = []
    for row_index, row in enumerate(rows):
        for header, value in zip(headers, row):
            if aligned_fields:
                render_aligned_field(out, header, value, label_width, available_width, label_style)
            else:
                render_stacked_field(out, header, value, available_width, label_style)

        if row_index + 1 < len(rows):
            separator_width = available_width if available_width is not None else widest_line_width(out)
            out.append(HyperlinkLine.new(Line.from_text(TABLE_BODY_SEPARATOR_CHAR * separator_width, style=separator_style)))

    return out


def render_aligned_field(
    out: list[HyperlinkLine],
    label: Any,
    value: Any,
    label_width: int,
    available_width: int | None,
    label_style: Any = None,
) -> None:
    label_text = _plain_text(label)
    value_indent = FIELD_LEADING_PADDING + label_width + FIELD_GAP
    value_width = (
        max(MIN_VALUE_WIDTH, available_width - value_indent)
        if available_width is not None
        else max(MIN_VALUE_WIDTH, cell_width(value))
    )
    wrapped = wrap_cell(value, value_width)
    first_prefix = [
        Span(" " * FIELD_LEADING_PADDING),
        Span(label_text, label_style),
        Span(" " * (label_width - _display_width(label_text) + FIELD_GAP)),
    ]
    subsequent_prefix = [Span(" " * value_indent)]

    for index, value_line in enumerate(wrapped):
        push_prefixed_value_line(out, first_prefix if index == 0 else subsequent_prefix, value_line)


def render_stacked_field(
    out: list[HyperlinkLine],
    label: Any,
    value: Any,
    available_width: int | None,
    label_style: Any = None,
) -> None:
    label_width = (
        max(1, available_width - FIELD_LEADING_PADDING)
        if available_width is not None
        else max(1, _display_width(_plain_text(label)))
    )
    for label_line in _wrap_plain_text(_plain_text(label), label_width):
        out.append(
            HyperlinkLine.new(
                Line.from_spans(
                    [Span(" " * FIELD_LEADING_PADDING), Span(label_line, label_style)]
                )
            )
        )

    value_width = (
        max(1, available_width - STACKED_VALUE_INDENT)
        if available_width is not None
        else max(1, cell_width(value))
    )
    prefix = [Span(" " * STACKED_VALUE_INDENT)]
    for value_line in wrap_cell(value, value_width):
        push_prefixed_value_line(out, prefix, value_line)


def push_prefixed_value_line(
    out: list[HyperlinkLine],
    prefix: Iterable[Span | str],
    value_line: HyperlinkLine,
) -> None:
    prefix_spans = tuple(_coerce_span(span) for span in prefix)
    shift = sum(_display_width(span.content) for span in prefix_spans)
    out.append(
        HyperlinkLine(
            Line((*prefix_spans, *value_line.line.spans)),
            [
                TerminalHyperlink(
                    range(link.columns.start + shift, link.columns.stop + shift),
                    link.destination,
                )
                for link in value_line.hyperlinks
            ],
        )
    )


def wrap_cell(cell: Any, width: int) -> list[HyperlinkLine]:
    """Wrap a table cell while preserving hard-break lines and hyperlinks."""

    safe_width = max(1, int(width))
    source_lines = _cell_lines(cell)
    if not source_lines:
        return [HyperlinkLine.new("")]

    out: list[HyperlinkLine] = []
    for source in source_lines:
        source = _coerce_hyperlink_line(source)
        wrapped_parts = _wrap_hyperlink_line(source, safe_width)
        out.extend(wrapped_parts or [HyperlinkLine.new("")])
    return out or [HyperlinkLine.new("")]


def cell_width(cell: Any) -> int:
    return max((sum(_display_width(span.content) for span in line.line.spans) for line in _cell_lines(cell)), default=0)


def widest_line_width(lines: Sequence[HyperlinkLine]) -> int:
    return max((sum(_display_width(span.content) for span in line.line.spans) for line in lines), default=0)


def _metric_kind(metric: Any) -> str:
    kind = getattr(metric, "kind", metric)
    value = getattr(kind, "value", kind)
    name = getattr(kind, "name", value)
    text = str(name).lower()
    if "compact" in text:
        return "compact"
    if "narrative" in text:
        return "narrative"
    if "token" in text:
        return "tokenheavy"
    return "compact"


def _plain_text(cell: Any) -> str:
    plain = getattr(cell, "plain_text", None)
    if callable(plain):
        return str(plain())
    if isinstance(plain, str):
        return plain
    if isinstance(cell, str):
        return cell
    return "\n".join(line_text(line) for line in _cell_lines(cell))


def _cell_lines(cell: Any) -> list[HyperlinkLine]:
    if isinstance(cell, HyperlinkLine):
        return [cell]
    if isinstance(cell, Line):
        return [HyperlinkLine.new(cell)]
    if isinstance(cell, str):
        return [HyperlinkLine.new(cell)]
    lines = getattr(cell, "lines", None)
    if lines is None:
        lines = getattr(getattr(cell, "_payload", None), "lines", None)
    if lines is None:
        payload = getattr(cell, "_payload", None)
        if isinstance(payload, (str, Line, HyperlinkLine)):
            return _cell_lines(payload)
        if isinstance(payload, Iterable):
            lines = payload
    if lines is None:
        return [HyperlinkLine.new(_plain_text_fallback(cell))]
    return [_coerce_hyperlink_line(line) for line in lines]


def _plain_text_fallback(cell: Any) -> str:
    value = getattr(cell, "text", None)
    if value is not None:
        return str(value)
    return "" if cell is None else str(cell)


def _coerce_hyperlink_line(value: Any) -> HyperlinkLine:
    if isinstance(value, HyperlinkLine):
        return value
    if isinstance(value, Line):
        return HyperlinkLine.new(value)
    return HyperlinkLine.new(value)


def _coerce_span(value: Span | str | Any) -> Span:
    if isinstance(value, Span):
        return value
    if isinstance(value, str):
        return Span(value)
    return Span(str(getattr(value, "content", value)), getattr(value, "style", None))


def _wrap_hyperlink_line(source: HyperlinkLine, width: int) -> list[HyperlinkLine]:
    text = line_text(source.line)
    segments = _wrap_plain_text(text, width)
    out: list[HyperlinkLine] = []
    source_column = 0
    for segment in segments:
        line = HyperlinkLine.new(segment)
        segment_start = source_column
        segment_end = source_column + _display_width(segment)
        for link in source.hyperlinks:
            start = max(link.columns.start, segment_start) - segment_start
            stop = min(link.columns.stop, segment_end) - segment_start
            if stop > start:
                line.hyperlinks.append(TerminalHyperlink(range(start, stop), link.destination))
        out.append(line)
        source_column = segment_end
        while source_column < _display_width(text) and text[_column_to_index(text, source_column)].isspace():
            source_column += 1
    return out


def _wrap_plain_text(text: str, width: int) -> list[str]:
    if text == "":
        return [""]
    out: list[str] = []
    remaining = text
    while _display_width(remaining) > width:
        split = _find_wrap_split(remaining, width)
        out.append(remaining[:split].rstrip())
        remaining = remaining[split:].lstrip()
    out.append(remaining)
    return out


def _find_wrap_split(text: str, width: int) -> int:
    used = 0
    last_space_end: int | None = None
    for index, ch in enumerate(text):
        next_used = used + _display_width(ch)
        if next_used > width:
            return last_space_end if last_space_end is not None else max(1, index)
        used = next_used
        if ch.isspace() and used > 0:
            last_space_end = index + len(ch)
    return len(text)


def _column_to_index(text: str, column: int) -> int:
    used = 0
    for index, ch in enumerate(text):
        if used >= column:
            return index
        used += _display_width(ch)
    return len(text)


__all__ = [
    "CATASTROPHIC_NARRATIVE_CELL_LINES",
    "CRAMPED_EXPANSIVE_CELL_LINES",
    "FIELD_GAP",
    "FIELD_LEADING_PADDING",
    "MIN_ALIGNED_COMPACT_VALUE_WIDTH",
    "MIN_ALIGNED_EXPANSIVE_VALUE_WIDTH",
    "MIN_SCANNABLE_NARRATIVE_WIDTH",
    "MIN_SCANNABLE_TOKEN_HEAVY_WIDTH",
    "MIN_VALUE_WIDTH",
    "RUST_MODULE",
    "STACKED_VALUE_INDENT",
    "cell_width",
    "expansive_cells_are_starved",
    "push_prefixed_value_line",
    "render_aligned_field",
    "render_records",
    "render_stacked_field",
    "should_render_records",
    "widest_line_width",
    "wrap_cell",
]
