"""Line utility helpers shared by TUI renderers.

Upstream source: ``codex/codex-rs/tui/src/render/line_utils.rs``.
"""

from __future__ import annotations

from typing import Iterable

from .._porting import RustTuiModule
from ..line_truncation import Line
from ..line_truncation import Span

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="render::line_utils",
    source="codex/codex-rs/tui/src/render/line_utils.rs",
)


def _coerce_span(span: Span | str) -> Span:
    return span if isinstance(span, Span) else Span(str(span))


def _coerce_line(line: Line | str | Iterable[Span | str]) -> Line:
    if isinstance(line, Line):
        return line
    if isinstance(line, str):
        return Line.from_text(line)
    return Line.from_spans(line)


def line_to_static(line: Line | str | Iterable[Span | str]) -> Line:
    """Clone a borrowed semantic ``Line`` into an owned line."""

    source = _coerce_line(line)
    return Line(
        tuple(Span(str(span.content), span.style) for span in source.spans),
        style=source.style,
        alignment=source.alignment,
    )


def push_owned_lines(src: Iterable[Line | str | Iterable[Span | str]], out: list[Line]) -> None:
    """Append owned copies of borrowed lines to ``out``."""

    for line in src:
        out.append(line_to_static(line))


def is_blank_line_spaces_only(line: Line | str | Iterable[Span | str]) -> bool:
    """Return true for empty lines or lines containing only literal spaces."""

    source = _coerce_line(line)
    if not source.spans:
        return True
    return all(span.content == "" or all(ch == " " for ch in span.content) for span in source.spans)


def prefix_lines(
    lines: Iterable[Line | str | Iterable[Span | str]],
    initial_prefix: Span | str,
    subsequent_prefix: Span | str,
) -> list[Line]:
    """Prefix each line, using a different prefix for the first line."""

    initial = _coerce_span(initial_prefix)
    subsequent = _coerce_span(subsequent_prefix)
    out: list[Line] = []
    for index, line in enumerate(lines):
        source = _coerce_line(line)
        prefix = initial if index == 0 else subsequent
        out.append(
            Line(
                (
                    Span(prefix.content, prefix.style),
                    *(Span(span.content, span.style) for span in source.spans),
                ),
                style=source.style,
            )
        )
    return out


__all__ = [
    "RUST_MODULE",
    "is_blank_line_spaces_only",
    "line_to_static",
    "prefix_lines",
    "push_owned_lines",
]
