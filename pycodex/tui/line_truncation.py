"""Line truncation helpers for styled TUI lines.

Upstream source: ``codex/codex-rs/tui/src/line_truncation.rs``.

Rust operates on ``ratatui::text::Line`` and ``Span``.  The Python port uses
small semantic equivalents so other TUI modules can depend on the same object
behavior without reimplementing ratatui.
"""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Any, Iterable

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="line_truncation",
    source="codex/codex-rs/tui/src/line_truncation.rs",
)


@dataclass(frozen=True)
class Span:
    """Semantic equivalent of Rust ``ratatui::text::Span`` for this module."""

    content: str
    style: Any = None


@dataclass(frozen=True)
class Line:
    """Semantic equivalent of Rust ``ratatui::text::Line`` for this module."""

    spans: tuple[Span, ...]
    style: Any = None
    alignment: Any = None

    @classmethod
    def from_text(cls, text: str, *, style: Any = None, alignment: Any = None) -> "Line":
        return cls((Span(text),), style=style, alignment=alignment)

    @classmethod
    def from_spans(
        cls,
        spans: Iterable[Span | str],
        *,
        style: Any = None,
        alignment: Any = None,
    ) -> "Line":
        return cls(tuple(_coerce_span(span) for span in spans), style=style, alignment=alignment)

    def __iter__(self):
        return iter(self.spans)


def _coerce_span(span: Span | str | Any) -> Span:
    if isinstance(span, Span):
        return span
    if isinstance(span, str):
        return Span(span)
    content = getattr(span, "content", getattr(span, "text", ""))
    style = getattr(span, "style", None)
    return Span(str(content), style)


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


def _char_display_width(ch: str) -> int:
    if not ch:
        return 0
    category = unicodedata.category(ch)
    if category in {"Mn", "Me", "Cf", "Cc"}:
        return 0
    if unicodedata.east_asian_width(ch) in {"F", "W"}:
        return 2
    return 1


def _display_width(text: str) -> int:
    return sum(_char_display_width(ch) for ch in text)


def line_width(line: Line | str | Iterable[Span | str] | Any) -> int:
    """Return display width for all spans in a line."""

    coerced = _coerce_line(line)
    return sum(_display_width(span.content) for span in coerced.spans)


def truncate_line_to_width(line: Line | str | Iterable[Span | str] | Any, max_width: int) -> Line:
    """Truncate a styled line to ``max_width`` display columns."""

    if max_width < 0:
        raise ValueError("max_width must be non-negative")
    coerced = _coerce_line(line)
    if max_width == 0:
        return Line(())

    used = 0
    spans_out: list[Span] = []

    for span in coerced.spans:
        span_width = _display_width(span.content)
        if span_width == 0:
            spans_out.append(span)
            continue
        if used >= max_width:
            break
        if used + span_width <= max_width:
            used += span_width
            spans_out.append(span)
            continue

        end_idx = 0
        for idx, ch in enumerate(span.content):
            ch_width = _char_display_width(ch)
            if used + ch_width > max_width:
                break
            end_idx = idx + 1
            used += ch_width

        if end_idx > 0:
            spans_out.append(Span(span.content[:end_idx], span.style))
        break

    return Line(tuple(spans_out), style=coerced.style, alignment=coerced.alignment)


def truncate_line_with_ellipsis_if_overflow(
    line: Line | str | Iterable[Span | str] | Any,
    max_width: int,
) -> Line:
    """Truncate a styled line and append an ellipsis on overflow."""

    if max_width < 0:
        raise ValueError("max_width must be non-negative")
    coerced = _coerce_line(line)
    if max_width == 0:
        return Line(())
    if line_width(coerced) <= max_width:
        return coerced

    truncated = truncate_line_to_width(coerced, max_width - 1)
    ellipsis_style = truncated.spans[-1].style if truncated.spans else None
    return Line(
        (*truncated.spans, Span("\u2026", ellipsis_style)),
        style=truncated.style,
        alignment=truncated.alignment,
    )


__all__ = [
    "Line",
    "RUST_MODULE",
    "Span",
    "line_width",
    "truncate_line_to_width",
    "truncate_line_with_ellipsis_if_overflow",
]

