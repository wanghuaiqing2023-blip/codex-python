"""Behavior port for Rust ``codex-tui::status::format``."""

from __future__ import annotations

from dataclasses import dataclass
import unicodedata
from typing import Iterable, MutableSequence, MutableSet

from .._porting import RustTuiModule
from ..line_truncation import Line, Span

RUST_MODULE = RustTuiModule(crate="codex-tui", module="status::format", source="codex/codex-rs/tui/src/status/format.rs")

DIM_STYLE = {"dim": True}


@dataclass(frozen=True)
class FieldFormatter:
    """Semantic equivalent of Rust ``status::format::FieldFormatter``."""

    indent: str
    label_width: int
    value_offset: int
    value_indent: str

    INDENT = " "

    @classmethod
    def from_labels(cls, labels: Iterable[str]) -> "FieldFormatter":
        label_width = max((_display_width(str(label)) for label in labels), default=0)
        indent_width = _display_width(cls.INDENT)
        value_offset = indent_width + label_width + 1 + 3
        return cls(
            indent=cls.INDENT,
            label_width=label_width,
            value_offset=value_offset,
            value_indent=" " * value_offset,
        )

    def line(self, label: str, value_spans: Iterable[Span | str]) -> Line:
        return Line.from_spans(self.full_spans(label, value_spans))

    def continuation(self, spans: Iterable[Span | str]) -> Line:
        return Line.from_spans((Span(self.value_indent, DIM_STYLE), *tuple(_coerce_span(span) for span in spans)))

    def value_width(self, available_inner_width: int) -> int:
        return max(0, int(available_inner_width) - self.value_offset)

    def full_spans(self, label: str, value_spans: Iterable[Span | str]) -> tuple[Span, ...]:
        return (self.label_span(label), *tuple(_coerce_span(span) for span in value_spans))

    def label_span(self, label: str) -> Span:
        label_text = str(label)
        padding = 3 + max(0, self.label_width - _display_width(label_text))
        return Span(f"{self.indent}{label_text}:{' ' * padding}", DIM_STYLE)


def push_label(labels: MutableSequence[str], seen: MutableSet[str], label: str) -> None:
    """Append ``label`` once, mirroring Rust's Vec plus BTreeSet guard."""

    owned = str(label)
    if owned in seen:
        return
    seen.add(owned)
    labels.append(owned)


def line_display_width(line: Line | str | Iterable[Span | str]) -> int:
    coerced = _coerce_line(line)
    return sum(_display_width(span.content) for span in coerced.spans)


def truncate_line_to_width(line: Line | str | Iterable[Span | str], max_width: int) -> Line:
    max_width = int(max_width)
    if max_width < 0:
        raise ValueError("max_width must be non-negative")
    source = _coerce_line(line)
    if max_width == 0:
        return Line(())

    used = 0
    spans_out: list[Span] = []
    for span in source.spans:
        text = span.content
        span_width = _display_width(text)

        if span_width == 0:
            spans_out.append(Span(text, span.style))
            continue
        if used >= max_width:
            break
        if used + span_width <= max_width:
            used += span_width
            spans_out.append(Span(text, span.style))
            continue

        truncated_chars: list[str] = []
        for ch in text:
            ch_width = _char_display_width(ch)
            if used + ch_width > max_width:
                break
            truncated_chars.append(ch)
            used += ch_width

        if truncated_chars:
            spans_out.append(Span("".join(truncated_chars), span.style))
        break

    return Line(tuple(spans_out))


def _coerce_span(span: Span | str) -> Span:
    if isinstance(span, Span):
        return span
    return Span(str(span))


def _coerce_line(line: Line | str | Iterable[Span | str]) -> Line:
    if isinstance(line, Line):
        return line
    if isinstance(line, str):
        return Line.from_text(line)
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


__all__ = [
    "DIM_STYLE",
    "FieldFormatter",
    "RUST_MODULE",
    "line_display_width",
    "push_label",
    "truncate_line_to_width",
]
