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


@dataclass(frozen=True)
class Line:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

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
    stripped = _ANSI_RE.sub("", normalized)
    raw_lines = stripped.splitlines()
    if not raw_lines:
        raw_lines = [""]
    return Text([Line(line) for line in raw_lines])


def ansi_escape_line(value: str) -> Line:
    text = ansi_escape(value)
    return text.lines[0] if text.lines else Line("")


__all__ = [
    "Line",
    "Text",
    "ansi_escape",
    "ansi_escape_line",
    "expand_tabs",
]
