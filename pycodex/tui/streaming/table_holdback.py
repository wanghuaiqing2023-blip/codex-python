"""Pipe-table holdback scanner for source-backed streaming output.

Upstream source: ``codex/codex-rs/tui/src/streaming/table_holdback.rs``.
The scanner keeps markdown table header/delimiter regions mutable so streamed
pipe tables can be re-rendered as later rows arrive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule
from ..table_detect import (
    FenceKind,
    FenceTracker,
    is_table_delimiter_line,
    is_table_header_line,
    parse_table_segments,
    strip_blockquote_prefix,
)

RUST_MODULE = RustTuiModule(crate="codex-tui", module="streaming::table_holdback", source="codex/codex-rs/tui/src/streaming/table_holdback.rs")


@dataclass(frozen=True)
class TableHoldbackState:
    """Semantic equivalent of Rust ``TableHoldbackState`` variants."""

    kind: str
    header_start: int | None = None
    table_start: int | None = None

    @classmethod
    def none(cls) -> "TableHoldbackState":
        return cls("None")

    @classmethod
    def pending_header(cls, header_start: int) -> "TableHoldbackState":
        return cls("PendingHeader", header_start=header_start)

    @classmethod
    def confirmed(cls, table_start: int) -> "TableHoldbackState":
        return cls("Confirmed", table_start=table_start)

    def is_none(self) -> bool:
        return self.kind == "None"

    def is_pending_header(self) -> bool:
        return self.kind == "PendingHeader"

    def is_confirmed(self) -> bool:
        return self.kind == "Confirmed"


@dataclass(frozen=True)
class PreviousLineState:
    source_start: int
    fence_kind: FenceKind
    is_header: bool


@dataclass
class TableHoldbackScanner:
    """Incremental append-only scanner for table holdback state."""

    source_offset: int = 0
    fence_tracker: FenceTracker | None = None
    previous_line: PreviousLineState | None = None
    pending_header_start: int | None = None
    confirmed_table_start: int | None = None

    def __post_init__(self) -> None:
        if self.fence_tracker is None:
            self.fence_tracker = FenceTracker.new()

    @classmethod
    def new(cls) -> "TableHoldbackScanner":
        return cls()

    def reset(self) -> None:
        fresh = type(self).new()
        self.source_offset = fresh.source_offset
        self.fence_tracker = fresh.fence_tracker
        self.previous_line = fresh.previous_line
        self.pending_header_start = fresh.pending_header_start
        self.confirmed_table_start = fresh.confirmed_table_start

    def state(self) -> TableHoldbackState:
        if self.confirmed_table_start is not None:
            return TableHoldbackState.confirmed(self.confirmed_table_start)
        if self.pending_header_start is not None:
            return TableHoldbackState.pending_header(self.pending_header_start)
        return TableHoldbackState.none()

    def push_source_chunk(self, source_chunk: str) -> None:
        if not source_chunk:
            return
        for source_line in _split_inclusive_newline(source_chunk):
            self.push_line(source_line)

    def push_line(self, source_line: str) -> None:
        line = source_line[:-1] if source_line.endswith("\n") else source_line
        source_start = self.source_offset
        assert self.fence_tracker is not None
        fence_kind = self.fence_tracker.kind()

        candidate_text = None if fence_kind is FenceKind.Other else table_candidate_text(line)
        is_header = candidate_text is not None and is_table_header_line(candidate_text)
        is_delimiter = candidate_text is not None and is_table_delimiter_line(candidate_text)

        if (
            self.confirmed_table_start is None
            and self.previous_line is not None
            and self.previous_line.fence_kind is not FenceKind.Other
            and fence_kind is not FenceKind.Other
            and self.previous_line.is_header
            and is_delimiter
        ):
            self.confirmed_table_start = self.previous_line.source_start
            self.pending_header_start = None

        if self.confirmed_table_start is None and line.strip():
            if fence_kind is not FenceKind.Other and is_header:
                self.pending_header_start = source_start
            else:
                self.pending_header_start = None

        self.previous_line = PreviousLineState(
            source_start=source_start,
            fence_kind=fence_kind,
            is_header=is_header,
        )
        self.fence_tracker.advance(line)
        self.source_offset += _byte_len(source_line)


def table_candidate_text(line: str) -> str | None:
    stripped = strip_blockquote_prefix(line).strip()
    return stripped if parse_table_segments(stripped) is not None else None


@dataclass(frozen=True)
class ParsedLine:
    text: str
    fence_context: FenceKind
    source_start: int


def parse_lines_with_fence_state(source: str) -> list[ParsedLine]:
    tracker = FenceTracker.new()
    lines: list[ParsedLine] = []
    source_start = 0

    for raw_line in source.split("\n"):
        lines.append(ParsedLine(text=raw_line, fence_context=tracker.kind(), source_start=source_start))
        tracker.advance(raw_line)
        source_start += _byte_len(raw_line) + 1

    return lines


def table_holdback_state(source: str) -> TableHoldbackState:
    lines = parse_lines_with_fence_state(source)
    for header_line, delimiter_line in zip(lines, lines[1:]):
        if header_line.fence_context is FenceKind.Other or delimiter_line.fence_context is FenceKind.Other:
            continue

        header_text = table_candidate_text(header_line.text)
        delimiter_text = table_candidate_text(delimiter_line.text)
        if header_text is None or delimiter_text is None:
            continue

        if is_table_header_line(header_text) and is_table_delimiter_line(delimiter_text):
            return TableHoldbackState.confirmed(header_line.source_start)

    for line in reversed(lines):
        if not line.text.strip():
            continue
        if line.fence_context is not FenceKind.Other:
            candidate = table_candidate_text(line.text)
            if candidate is not None and is_table_header_line(candidate):
                return TableHoldbackState.pending_header(line.source_start)
        break

    return TableHoldbackState.none()


def _split_inclusive_newline(source: str) -> list[str]:
    if source == "":
        return []
    parts = source.splitlines(keepends=True)
    return parts if parts else [source]


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


__all__ = [
    "ParsedLine",
    "PreviousLineState",
    "RUST_MODULE",
    "TableHoldbackScanner",
    "TableHoldbackState",
    "parse_lines_with_fence_state",
    "table_candidate_text",
    "table_holdback_state",
]
