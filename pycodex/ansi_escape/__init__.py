"""ANSI escape helpers ported from ``codex-rs/ansi-escape``.

The Rust crate returns ratatui ``Text``/``Line`` values after parsing ANSI
styling.  The Python port keeps the dependency-light behavior needed by core:
tabs are normalized for transcript rendering, ANSI control sequences are
stripped, and the line helper returns the first rendered line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|[@-Z\\-_])")
_ANSI_TOKEN_RE = re.compile(
    r"(\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_])"
)


@dataclass(frozen=True)
class AnsiStyle:
    """Serializable subset of the ratatui style produced by ``ansi-to-tui``."""

    fg: str | tuple[int, int, int] | int | None = None
    bg: str | tuple[int, int, int] | int | None = None
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underlined: bool = False
    reversed: bool = False


@dataclass(frozen=True)
class Span:
    text: str
    style: AnsiStyle = AnsiStyle()


@dataclass(frozen=True)
class Line:
    text: str
    spans: tuple[Span, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not self.spans and self.text:
            object.__setattr__(self, "spans", (Span(self.text),))

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class Text:
    lines: list[Line]

    def __post_init__(self) -> None:
        if not isinstance(self.lines, list) or not all(isinstance(line, Line) for line in self.lines):
            raise TypeError("lines must be a list of Line")

    def plain(self) -> str:
        return "\n".join(line.text for line in self.lines)


def expand_tabs(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    return value.replace("\t", "    ")


def ansi_escape(value: str) -> Text:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    normalized = expand_tabs(value)
    style = AnsiStyle()
    line_spans: list[list[Span]] = [[]]
    for token in _ANSI_TOKEN_RE.split(normalized):
        if not token:
            continue
        if token.startswith("\x1b[") and token.endswith("m"):
            style = _apply_sgr(style, token[2:-1])
            continue
        if token.startswith("\x1b"):
            continue
        parts = token.split("\n")
        for index, part in enumerate(parts):
            if part:
                if part.endswith("\r"):
                    part = part[:-1]
                if part:
                    line_spans[-1].append(Span(part, style))
            if index < len(parts) - 1:
                line_spans.append([])
    return Text(
        [
            Line("".join(span.text for span in spans), tuple(spans))
            for spans in line_spans
        ]
    )


def _apply_sgr(style: AnsiStyle, raw: str) -> AnsiStyle:
    values = _sgr_values(raw)
    current = style
    index = 0
    while index < len(values):
        code = values[index]
        if code == 0:
            current = AnsiStyle()
        elif code == 1:
            current = _replace_style(current, bold=True)
        elif code == 2:
            current = _replace_style(current, dim=True)
        elif code == 3:
            current = _replace_style(current, italic=True)
        elif code == 4:
            current = _replace_style(current, underlined=True)
        elif code == 7:
            current = _replace_style(current, reversed=True)
        elif code == 22:
            current = _replace_style(current, bold=False, dim=False)
        elif code == 23:
            current = _replace_style(current, italic=False)
        elif code == 24:
            current = _replace_style(current, underlined=False)
        elif code == 27:
            current = _replace_style(current, reversed=False)
        elif 30 <= code <= 37:
            current = _replace_style(current, fg=_ANSI_COLORS[code - 30])
        elif 90 <= code <= 97:
            current = _replace_style(current, fg=_ANSI_BRIGHT_COLORS[code - 90])
        elif 40 <= code <= 47:
            current = _replace_style(current, bg=_ANSI_COLORS[code - 40])
        elif 100 <= code <= 107:
            current = _replace_style(current, bg=_ANSI_BRIGHT_COLORS[code - 100])
        elif code == 39:
            current = _replace_style(current, fg=None)
        elif code == 49:
            current = _replace_style(current, bg=None)
        elif code in {38, 48}:
            color, consumed = _extended_color(values[index + 1 :])
            if color is not None:
                current = _replace_style(
                    current,
                    **({"fg": color} if code == 38 else {"bg": color}),
                )
            index += consumed
        index += 1
    return current


def _sgr_values(raw: str) -> list[int]:
    if not raw:
        return [0]
    values: list[int] = []
    for value in raw.split(";"):
        try:
            values.append(int(value or "0"))
        except ValueError:
            values.append(0)
    return values


def _extended_color(values: list[int]) -> tuple[str | tuple[int, int, int] | int | None, int]:
    if len(values) >= 2 and values[0] == 5:
        return max(0, min(values[1], 255)), 2
    if len(values) >= 4 and values[0] == 2:
        return tuple(max(0, min(value, 255)) for value in values[1:4]), 4
    return None, 0


def _replace_style(style: AnsiStyle, **updates: object) -> AnsiStyle:
    values = {
        "fg": style.fg,
        "bg": style.bg,
        "bold": style.bold,
        "dim": style.dim,
        "italic": style.italic,
        "underlined": style.underlined,
        "reversed": style.reversed,
    }
    values.update(updates)
    return AnsiStyle(**values)  # type: ignore[arg-type]


_ANSI_COLORS = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "gray")
_ANSI_BRIGHT_COLORS = (
    "dark_gray",
    "light_red",
    "light_green",
    "light_yellow",
    "light_blue",
    "light_magenta",
    "light_cyan",
    "white",
)


def ansi_escape_line(value: str) -> Line:
    text = ansi_escape(value)
    return text.lines[0] if text.lines else Line("")


__all__ = [
    "AnsiStyle",
    "Line",
    "Span",
    "Text",
    "ansi_escape",
    "ansi_escape_line",
    "expand_tabs",
]
