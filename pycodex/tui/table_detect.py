"""Markdown table and fenced-code detection for ``codex-tui::table_detect``.

This module ports the local behavior from
``codex/codex-rs/tui/src/table_detect.rs`` using Python strings and enums as
semantic equivalents for Rust references and enum values.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="table_detect",
    source="codex/codex-rs/tui/src/table_detect.rs",
)


def parse_table_segments(line: str) -> list[str] | None:
    """Split a pipe-delimited table line into trimmed structural segments."""
    trimmed = line.strip()
    if not trimmed:
        return None

    has_outer_pipe = trimmed.startswith("|") or trimmed.endswith("|")
    content = trimmed[1:] if trimmed.startswith("|") else trimmed
    content = content[:-1] if content.endswith("|") else content
    raw_segments = split_unescaped_pipe(content)
    if not has_outer_pipe and len(raw_segments) <= 1:
        return None

    segments = [segment.strip() for segment in raw_segments]
    return segments if segments else None


def split_unescaped_pipe(content: str) -> list[str]:
    """Split ``content`` on ``|`` unless the pipe is escaped by ``\\``."""
    segments: list[str] = []
    start = 0
    i = 0
    while i < len(content):
        if content[i] == "\\":
            i += 2
        elif content[i] == "|":
            segments.append(content[start:i])
            start = i + 1
            i += 1
        else:
            i += 1
    segments.append(content[start:])
    return segments


def is_table_header_line(line: str) -> bool:
    """Return whether ``line`` can be a markdown table header row."""
    segments = parse_table_segments(line)
    return segments is not None and any(segment != "" for segment in segments)


def is_table_delimiter_segment(segment: str) -> bool:
    """Return whether one segment matches GFM table delimiter syntax."""
    trimmed = segment.strip()
    if not trimmed:
        return False
    without_leading = trimmed[1:] if trimmed.startswith(":") else trimmed
    without_ends = without_leading[:-1] if without_leading.endswith(":") else without_leading
    return len(without_ends) >= 3 and all(ch == "-" for ch in without_ends)


def is_table_delimiter_line(line: str) -> bool:
    """Return whether ``line`` can be a markdown table delimiter row."""
    segments = parse_table_segments(line)
    return segments is not None and all(is_table_delimiter_segment(segment) for segment in segments)


class FenceKind(Enum):
    """Context of the current source line relative to fenced code blocks."""

    Outside = "outside"
    Markdown = "markdown"
    Other = "other"


@dataclass
class FenceTracker:
    """Incremental fenced-code-block open/close tracker."""

    state: tuple[str, int, FenceKind] | None = None

    @classmethod
    def new(cls) -> "FenceTracker":
        return cls()

    def advance(self, raw_line: str) -> None:
        leading_spaces = 0
        for ch in raw_line:
            if ch == " ":
                leading_spaces += 1
            else:
                break
        if leading_spaces > 3:
            return

        trimmed = raw_line[leading_spaces:]
        fence_scan_text = strip_blockquote_prefix(trimmed)
        marker = parse_fence_marker(fence_scan_text)
        if marker is None:
            return

        marker_char, marker_len = marker
        if self.state is not None:
            open_char, open_len, _kind = self.state
            if (
                marker_char == open_char
                and marker_len >= open_len
                and fence_scan_text[marker_len:].strip() == ""
            ):
                self.state = None
            return

        kind = (
            FenceKind.Markdown
            if is_markdown_fence_info(fence_scan_text, marker_len)
            else FenceKind.Other
        )
        self.state = (marker_char, marker_len, kind)

    def kind(self) -> FenceKind:
        return FenceKind.Outside if self.state is None else self.state[2]


def parse_fence_marker(line: str) -> tuple[str, int] | None:
    """Return fence marker char and run length for 3+ backticks or tildes."""
    if not line:
        return None
    first = line[0]
    if first not in ("`", "~"):
        return None
    length = 0
    for ch in line:
        if ch == first:
            length += 1
        else:
            break
    if length < 3:
        return None
    return first, length


def is_markdown_fence_info(trimmed_line: str, marker_len: int) -> bool:
    """Return whether a fence info string is ``md`` or ``markdown``."""
    rest = trimmed_line[marker_len:]
    info = rest.split(None, 1)[0] if rest.split(None, 1) else ""
    lowered = info.lower()
    return lowered == "md" or lowered == "markdown"


def strip_blockquote_prefix(line: str) -> str:
    """Strip repeated leading markdown blockquote prefixes from ``line``."""
    rest = line.lstrip()
    while rest.startswith(">"):
        stripped = rest[1:]
        rest = stripped[1:] if stripped.startswith(" ") else stripped
        rest = rest.lstrip()
    return rest


__all__ = [
    "FenceKind",
    "FenceTracker",
    "RUST_MODULE",
    "is_markdown_fence_info",
    "is_table_delimiter_line",
    "is_table_delimiter_segment",
    "is_table_header_line",
    "parse_fence_marker",
    "parse_table_segments",
    "split_unescaped_pipe",
    "strip_blockquote_prefix",
]
