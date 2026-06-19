"""Semantic history insertion helpers for the TUI port.

Rust counterpart: ``codex-rs/tui/src/insert_history.rs``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum, IntFlag
from io import StringIO
from typing import Iterable, Sequence, TextIO


class HistoryLineWrapPolicy(str, Enum):
    PRE_WRAP = "pre_wrap"
    TERMINAL = "terminal"


class InsertHistoryMode(str, Enum):
    STANDARD = "standard"
    ZELLIJ_RAW = "zellij_raw"


class Modifier(IntFlag):
    REVERSED = 1 << 0
    BOLD = 1 << 1
    ITALIC = 1 << 2
    UNDERLINED = 1 << 3
    DIM = 1 << 4
    CROSSED_OUT = 1 << 5
    SLOW_BLINK = 1 << 6
    RAPID_BLINK = 1 << 7


@dataclass(frozen=True)
class Style:
    fg: str | None = None
    bg: str | None = None
    add_modifier: Modifier = Modifier(0)
    sub_modifier: Modifier = Modifier(0)

    def patch(self, other: "Style") -> "Style":
        return Style(
            fg=other.fg if other.fg is not None else self.fg,
            bg=other.bg if other.bg is not None else self.bg,
            add_modifier=(self.add_modifier | other.add_modifier) & ~other.sub_modifier,
            sub_modifier=self.sub_modifier | other.sub_modifier,
        )


@dataclass(frozen=True)
class Span:
    content: str
    style: Style = Style()


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...]
    style: Style = Style()

    @classmethod
    def from_text(cls, text: str, style: Style = Style()) -> "Line":
        return cls((Span(str(text)),), style)

    @property
    def text(self) -> str:
        return "".join(span.content for span in self.spans)

    def width(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class Hyperlink:
    start: int
    end: int
    uri: str


@dataclass(frozen=True)
class HyperlinkLine:
    line: Line
    hyperlinks: tuple[Hyperlink, ...] = ()

    @property
    def text(self) -> str:
        return self.line.text

    def width(self) -> int:
        return self.line.width()


@dataclass(frozen=True)
class SetScrollRegion:
    range: range | tuple[int, int]

    def write_ansi(self) -> str:
        start, end = _range_bounds(self.range)
        return f"\x1b[{start};{end}r"


@dataclass(frozen=True)
class ResetScrollRegion:
    def write_ansi(self) -> str:
        return "\x1b[r"


@dataclass(frozen=True)
class ModifierDiff:
    from_modifier: Modifier
    to_modifier: Modifier

    def ansi(self) -> str:
        parts: list[str] = []
        removed = self.from_modifier & ~self.to_modifier
        if removed & Modifier.REVERSED:
            parts.append("\x1b[27m")
        if removed & Modifier.BOLD:
            parts.append("\x1b[22m")
            if self.to_modifier & Modifier.DIM:
                parts.append("\x1b[2m")
        if removed & Modifier.ITALIC:
            parts.append("\x1b[23m")
        if removed & Modifier.UNDERLINED:
            parts.append("\x1b[24m")
        if removed & Modifier.DIM:
            parts.append("\x1b[22m")
        if removed & Modifier.CROSSED_OUT:
            parts.append("\x1b[29m")
        if removed & (Modifier.SLOW_BLINK | Modifier.RAPID_BLINK):
            parts.append("\x1b[25m")

        added = self.to_modifier & ~self.from_modifier
        if added & Modifier.REVERSED:
            parts.append("\x1b[7m")
        if added & Modifier.BOLD:
            parts.append("\x1b[1m")
        if added & Modifier.ITALIC:
            parts.append("\x1b[3m")
        if added & Modifier.UNDERLINED:
            parts.append("\x1b[4m")
        if added & Modifier.DIM:
            parts.append("\x1b[2m")
        if added & Modifier.CROSSED_OUT:
            parts.append("\x1b[9m")
        if added & Modifier.SLOW_BLINK:
            parts.append("\x1b[5m")
        if added & Modifier.RAPID_BLINK:
            parts.append("\x1b[6m")
        return "".join(parts)

    def queue(self, writer: TextIO) -> None:
        writer.write(self.ansi())


@dataclass
class TerminalModel:
    width: int
    height: int
    viewport_y: int = 0
    viewport_height: int = 1
    history_rows_inserted: int = 0
    output: StringIO = field(default_factory=StringIO)

    def write(self, text: str) -> int:
        self.output.write(text)
        return len(text)

    def note_history_rows_inserted(self, rows: int) -> None:
        self.history_rows_inserted += rows


def _range_bounds(value: range | tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, range):
        return value.start, value.stop
    return int(value[0]), int(value[1])


def _coerce_line(value: str | Line | HyperlinkLine) -> Line:
    if isinstance(value, HyperlinkLine):
        return value.line
    if isinstance(value, Line):
        return value
    return Line.from_text(str(value))


def _coerce_hyperlink_line(value: str | Line | HyperlinkLine) -> HyperlinkLine:
    if isinstance(value, HyperlinkLine):
        return value
    return HyperlinkLine(_coerce_line(value))


def line_contains_url_like(line: Line) -> bool:
    return bool(re.search(r"(?:https?://|\b[\w.-]+\.[A-Za-z]{2,}/)", line.text))


def line_has_mixed_url_and_non_url_tokens(line: Line) -> bool:
    text = line.text.strip()
    if not line_contains_url_like(line):
        return False
    tokens = text.split()
    url_tokens = [token for token in tokens if line_contains_url_like(Line.from_text(token))]
    return bool(url_tokens and len(url_tokens) < len(tokens))


def leading_whitespace_prefix(line: str | Line | HyperlinkLine) -> Line:
    source = _coerce_line(line)
    spans: list[Span] = []
    for span in source.spans:
        match = re.match(r"\s*", span.content)
        prefix_end = match.end() if match else 0
        if prefix_end > 0:
            spans.append(Span(span.content[:prefix_end], span.style))
        if prefix_end < len(span.content):
            break
    return Line(tuple(spans), source.style)


def _wrap_text_preserving_prefix(text: str, width: int, prefix: str) -> list[str]:
    if width <= 0:
        return [text]
    if len(text) <= width:
        return [text]
    body = text[len(prefix) :] if prefix and text.startswith(prefix) else text
    words = body.split(" ")
    rows: list[str] = []
    current = prefix
    continuation_prefix = prefix
    for word in words:
        if current == prefix:
            candidate = current + word
        else:
            candidate = word if current == "" else current + " " + word
        limit = width if not rows else max(width - len(continuation_prefix), 1)
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            rows.append((continuation_prefix if rows else "") + current)
            current = word
        else:
            for start in range(0, len(word), limit):
                chunk = word[start : start + limit]
                rows.append((continuation_prefix if rows else "") + chunk)
            current = ""
    if current or not rows:
        rows.append((continuation_prefix if rows else "") + current)
    return rows


def wrap_history_line(line: HyperlinkLine, wrap_width: int, wrap_policy: HistoryLineWrapPolicy) -> list[HyperlinkLine]:
    if wrap_policy == HistoryLineWrapPolicy.TERMINAL:
        return [line]
    if line_contains_url_like(line.line) and not line_has_mixed_url_and_non_url_tokens(line.line):
        return [line]
    prefix = leading_whitespace_prefix(line).text
    rows = _wrap_text_preserving_prefix(line.text, max(wrap_width, 1), prefix)
    return [HyperlinkLine(Line.from_text(row, line.line.style), line.hyperlinks if idx == 0 else ()) for idx, row in enumerate(rows)]


def _ansi_color(name: str | None, foreground: bool) -> str:
    if name is None or name.lower() == "reset":
        return "\x1b[39m" if foreground else "\x1b[49m"
    table = {
        "black": 30,
        "red": 31,
        "green": 32,
        "yellow": 33,
        "blue": 34,
        "magenta": 35,
        "cyan": 36,
        "white": 37,
    }
    code = table.get(name.lower(), 39 if foreground else 49)
    if not foreground and code < 40:
        code += 10
    return f"\x1b[{code}m"


def _decorate_hyperlinks(line: HyperlinkLine, text: str) -> str:
    if not line.hyperlinks:
        return text
    out = text
    for link in sorted(line.hyperlinks, key=lambda item: item.start, reverse=True):
        visible = out[link.start : link.end]
        out = out[: link.start] + f"\x1b]8;;{link.uri}\x07{visible}\x1b]8;;\x07" + out[link.end :]
    return out


def write_spans(writer: TextIO, content: Iterable[Span]) -> None:
    fg: str | None = "reset"
    bg: str | None = "reset"
    last_modifier = Modifier(0)
    for span in content:
        modifier = (span.style.add_modifier & ~span.style.sub_modifier)
        if modifier != last_modifier:
            ModifierDiff(last_modifier, modifier).queue(writer)
            last_modifier = modifier
        next_fg = span.style.fg or "reset"
        next_bg = span.style.bg or "reset"
        if next_fg != fg:
            writer.write(_ansi_color(next_fg, True))
            fg = next_fg
        if next_bg != bg:
            writer.write(_ansi_color(next_bg, False))
            bg = next_bg
        writer.write(span.content)
    writer.write("\x1b[39m\x1b[49m\x1b[0m")


def write_history_line(writer: TextIO, line: HyperlinkLine | Line | str, wrap_width: int) -> None:
    hline = _coerce_hyperlink_line(line)
    physical_rows = math.ceil(max(hline.width(), 1) / max(wrap_width, 1))
    if physical_rows > 1:
        writer.write("<save>")
        for _ in range(1, physical_rows):
            writer.write("<down><col0><clear-eol>")
        writer.write("<restore>")
    writer.write(_ansi_color(hline.line.style.fg, True))
    writer.write(_ansi_color(hline.line.style.bg, False))
    writer.write("<clear-eol>")
    merged = [Span(span.content, span.style.patch(hline.line.style)) for span in hline.line.spans]
    if hline.hyperlinks:
        plain = "".join(span.content for span in merged)
        writer.write(_decorate_hyperlinks(hline, plain))
        writer.write("\x1b[39m\x1b[49m\x1b[0m")
    else:
        write_spans(writer, merged)


def insert_history_hyperlink_lines_with_mode_and_wrap_policy(
    terminal: TerminalModel,
    lines: Sequence[HyperlinkLine | Line | str],
    mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    wrap_policy: HistoryLineWrapPolicy = HistoryLineWrapPolicy.PRE_WRAP,
) -> list[HyperlinkLine]:
    wrap_width = max(terminal.width, 1)
    wrapped: list[HyperlinkLine] = []
    wrapped_rows = 0
    for raw_line in lines:
        hline = _coerce_hyperlink_line(raw_line)
        line_wrapped = wrap_history_line(hline, wrap_width, wrap_policy)
        wrapped_rows += sum(math.ceil(max(item.width(), 1) / wrap_width) for item in line_wrapped)
        wrapped.extend(line_wrapped)

    if mode == InsertHistoryMode.ZELLIJ_RAW:
        terminal.write("<clear-after-viewport><move-viewport-top>")
    else:
        terminal.write(SetScrollRegion(range(1, max(terminal.viewport_y, 1))).write_ansi())
    for line in wrapped:
        terminal.write("\r\n")
        write_history_line(terminal.output, line, wrap_width)
    terminal.write(ResetScrollRegion().write_ansi())
    if wrapped_rows > 0:
        terminal.note_history_rows_inserted(wrapped_rows)
    return wrapped


def insert_history_lines_with_mode_and_wrap_policy(
    terminal: TerminalModel,
    lines: Sequence[Line | str],
    mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    wrap_policy: HistoryLineWrapPolicy = HistoryLineWrapPolicy.PRE_WRAP,
) -> list[HyperlinkLine]:
    return insert_history_hyperlink_lines_with_mode_and_wrap_policy(terminal, list(lines), mode, wrap_policy)


def insert_history_lines_with_wrap_policy(
    terminal: TerminalModel,
    lines: Sequence[Line | str],
    wrap_policy: HistoryLineWrapPolicy = HistoryLineWrapPolicy.PRE_WRAP,
) -> list[HyperlinkLine]:
    return insert_history_lines_with_mode_and_wrap_policy(terminal, lines, InsertHistoryMode.STANDARD, wrap_policy)


def insert_history_lines(terminal: TerminalModel, lines: Sequence[Line | str]) -> list[HyperlinkLine]:
    return insert_history_lines_with_wrap_policy(terminal, lines, HistoryLineWrapPolicy.PRE_WRAP)


def write_ansi(command: SetScrollRegion | ResetScrollRegion) -> str:
    return command.write_ansi()


def execute_winapi(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("tried to execute scroll region command using WinAPI, use ANSI instead")


def is_ansi_code_supported() -> bool:
    return True


__all__ = [
    "HistoryLineWrapPolicy",
    "Hyperlink",
    "HyperlinkLine",
    "InsertHistoryMode",
    "Line",
    "Modifier",
    "ModifierDiff",
    "ResetScrollRegion",
    "SetScrollRegion",
    "Span",
    "Style",
    "TerminalModel",
    "execute_winapi",
    "insert_history_hyperlink_lines_with_mode_and_wrap_policy",
    "insert_history_lines",
    "insert_history_lines_with_mode_and_wrap_policy",
    "insert_history_lines_with_wrap_policy",
    "is_ansi_code_supported",
    "leading_whitespace_prefix",
    "line_contains_url_like",
    "line_has_mixed_url_and_non_url_tokens",
    "wrap_history_line",
    "write_ansi",
    "write_history_line",
    "write_spans",
]
