"""Shared semantic history-cell building blocks.

Upstream source: ``codex/codex-rs/tui/src/history_cell/base.rs``.

Rust implements these cells over ``ratatui::text::Line`` and the local
``HistoryCell`` trait.  The Python port uses the existing lightweight
``Line``/``Span`` and ``HyperlinkLine`` semantic models instead of ratatui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from ..terminal_hyperlinks import HyperlinkLine, annotate_web_urls, plain_hyperlink_lines
from ..wrapping import RtOptions, adaptive_wrap_lines as rust_adaptive_wrap_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::base",
    source="codex/codex-rs/tui/src/history_cell/base.rs",
)


class HistoryCell(Protocol):
    """Protocol-shaped equivalent of Rust's ``HistoryCell`` trait surface."""

    def display_lines(self, width: int) -> list[Line]:
        ...

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        ...

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        ...

    def raw_lines(self) -> list[Line]:
        ...


def _coerce_span(span: Span | str | Any) -> Span:
    if isinstance(span, Span):
        return span
    if isinstance(span, str):
        return Span(span)
    return Span(str(getattr(span, "content", getattr(span, "text", span))), getattr(span, "style", None))


def _coerce_line(line: Line | str | Iterable[Span | str] | Any) -> Line:
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


def _coerce_lines(lines: Iterable[Line | str | Iterable[Span | str] | Any] | str | Line) -> list[Line]:
    if isinstance(lines, Line):
        return [lines]
    if isinstance(lines, str):
        return [Line.from_text(part) for part in lines.splitlines() or [""]]
    return [_coerce_line(line) for line in lines]


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def plain_line(line: Line | str | Iterable[Span | str] | Any) -> Line:
    """Return a line with visible text preserved and styling removed."""

    coerced = _coerce_line(line)
    return Line.from_text(line_text(coerced))


def plain_lines(lines: Iterable[Line | str | Iterable[Span | str] | Any]) -> list[Line]:
    return [plain_line(line) for line in lines]


def adaptive_wrap_lines(
    text: Iterable[Line | str | Iterable[Span | str] | Any] | str | Line,
    width: int,
    initial_prefix: Line | str | Iterable[Span | str] | Any = "",
    subsequent_prefix: Line | str | Iterable[Span | str] | Any = "",
) -> list[Line]:
    """Wrap text with Rust-like initial/subsequent indentation semantics."""

    if width <= 0:
        return []
    options = (
        RtOptions.new(width)
        .initial_indent(_coerce_line(initial_prefix))
        .subsequent_indent(_coerce_line(subsequent_prefix))
    )
    return rust_adaptive_wrap_lines(_coerce_lines(text), options)


@dataclass
class PlainHistoryCell:
    lines: list[Line] = field(default_factory=list)

    @classmethod
    def new(cls, lines: Iterable[Line | str | Iterable[Span | str] | Any]) -> "PlainHistoryCell":
        return cls(_coerce_lines(lines))

    def display_lines(self, _width: int) -> list[Line]:
        return list(self.lines)

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return plain_hyperlink_lines(self.display_lines(width))

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(self.lines)


@dataclass
class WebHyperlinkHistoryCell:
    lines: list[Line] = field(default_factory=list)

    @classmethod
    def new(
        cls, lines: Iterable[Line | str | Iterable[Span | str] | Any]
    ) -> "WebHyperlinkHistoryCell":
        return cls(_coerce_lines(lines))

    def display_lines(self, _width: int) -> list[Line]:
        return list(self.lines)

    def display_hyperlink_lines(self, _width: int) -> list[HyperlinkLine]:
        return annotate_web_urls(self.lines)

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(self.lines)


@dataclass
class PrefixedWrappedHistoryCell:
    text: list[Line] = field(default_factory=list)
    initial_prefix: Line = field(default_factory=lambda: Line.from_text(""))
    subsequent_prefix: Line = field(default_factory=lambda: Line.from_text(""))

    @classmethod
    def new(
        cls,
        text: Iterable[Line | str | Iterable[Span | str] | Any] | str | Line,
        initial_prefix: Line | str | Iterable[Span | str] | Any,
        subsequent_prefix: Line | str | Iterable[Span | str] | Any,
    ) -> "PrefixedWrappedHistoryCell":
        return cls(
            _coerce_lines(text),
            _coerce_line(initial_prefix),
            _coerce_line(subsequent_prefix),
        )

    def display_lines(self, width: int) -> list[Line]:
        if width == 0:
            return []
        return adaptive_wrap_lines(
            self.text,
            max(1, int(width)),
            self.initial_prefix,
            self.subsequent_prefix,
        )

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return plain_hyperlink_lines(self.display_lines(width))

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(self.text)


@dataclass
class CompositeHistoryCell:
    parts: list[HistoryCell] = field(default_factory=list)

    @classmethod
    def new(cls, parts: Iterable[HistoryCell]) -> "CompositeHistoryCell":
        return cls(list(parts))

    def _join_non_empty(self, method_name: str, width: int) -> list[Any]:
        out: list[Any] = []
        first = True
        blank: Any
        for part in self.parts:
            method = getattr(part, method_name)
            lines = list(method(width)) if method_name != "raw_lines" else list(method())
            if not lines:
                continue
            if not first:
                sample = lines[0]
                blank = HyperlinkLine.new("") if isinstance(sample, HyperlinkLine) else Line.from_text("")
                out.append(blank)
            out.extend(lines)
            first = False
        return out

    def display_lines(self, width: int) -> list[Line]:
        return self._join_non_empty("display_lines", width)

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self._join_non_empty("display_hyperlink_lines", width)

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self._join_non_empty("transcript_hyperlink_lines", width)

    def raw_lines(self) -> list[Line]:
        return self._join_non_empty("raw_lines", 0)


def display_lines(cell: HistoryCell, width: int) -> list[Line]:
    return cell.display_lines(width)


def display_hyperlink_lines(cell: HistoryCell, width: int) -> list[HyperlinkLine]:
    return cell.display_hyperlink_lines(width)


def transcript_hyperlink_lines(cell: HistoryCell, width: int) -> list[HyperlinkLine]:
    return cell.transcript_hyperlink_lines(width)


def raw_lines(cell: HistoryCell) -> list[Line]:
    return cell.raw_lines()


__all__ = [
    "CompositeHistoryCell",
    "HistoryCell",
    "PlainHistoryCell",
    "PrefixedWrappedHistoryCell",
    "RUST_MODULE",
    "WebHyperlinkHistoryCell",
    "adaptive_wrap_lines",
    "display_hyperlink_lines",
    "display_lines",
    "line_text",
    "plain_line",
    "plain_lines",
    "raw_lines",
    "transcript_hyperlink_lines",
]
