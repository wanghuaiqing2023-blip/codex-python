"""Semantic port of codex-tui ``markdown_stream.rs``.

The Rust module owns the streaming source-buffer state machine used before
completed markdown chunks are rendered. This Python module ports that collector
boundary. Full ratatui markdown rendering remains a dependency boundary for the
Python TUI; line helpers expose plain semantic lines so callers can verify
source chunking without pretending to have Rust rendering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tempfile
from typing import Iterable, List, Optional, Union

from .line_truncation import Line
from ._porting import RustTuiModule


class MarkdownStreamLine(Line):
    def plain_text(self) -> str:
        return "".join(span.content for span in self.spans)


def _source_to_plain_lines(source: str) -> List[Line]:
    """Convert committed source text into semantic plain lines."""

    lines: List[Line] = []
    for line in source.splitlines():
        base = Line.from_text(line)
        lines.append(MarkdownStreamLine(base.spans, base.style, base.alignment))
    return lines


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="markdown_stream",
    source="codex/codex-rs/tui/src/markdown_stream.rs",
    status="complete",
)


@dataclass
class MarkdownStreamCollector:
    """Collect streamed markdown deltas and commit only complete source lines."""

    width: Optional[int] = None
    cwd: Path = field(default_factory=lambda: Path.cwd())
    buffer: str = ""
    committed_source_len: int = 0
    committed_line_count: int = 0

    @classmethod
    def new(cls, width: Optional[int] = None, cwd: Optional[Union[str, Path]] = None) -> "MarkdownStreamCollector":
        return cls(width=width, cwd=Path.cwd() if cwd is None else Path(cwd))

    def set_width(self, width: Optional[int]) -> None:
        self.width = width

    def clear(self) -> None:
        self.buffer = ""
        self.committed_source_len = 0
        self.committed_line_count = 0

    def push_delta(self, delta: str) -> None:
        self.buffer += delta

    def commit_complete_source(self) -> Optional[str]:
        """Return newly completed source through the last newline, if any."""

        newline_idx = self.buffer.rfind("\n")
        if newline_idx == -1:
            return None

        commit_end = newline_idx + 1
        if commit_end <= self.committed_source_len:
            return None

        source = self.buffer[self.committed_source_len:commit_end]
        self.committed_source_len = commit_end
        return source

    def finalize_and_drain_source(self) -> str:
        """Return remaining uncommitted source, newline-terminated, then clear."""

        if self.committed_source_len >= len(self.buffer):
            self.clear()
            return ""

        source = self.buffer[self.committed_source_len:]
        if source and not source.endswith("\n"):
            source += "\n"
        self.clear()
        return source

    def commit_complete_lines(self) -> List[Line]:
        """Semantic test helper for committed completed lines.

        Rust renders markdown into ratatui lines here. Python keeps the module
        boundary honest by returning plain semantic lines while preserving the
        exact source commit timing.
        """

        source = self.commit_complete_source()
        if source is None:
            return []
        lines = _source_to_plain_lines(source)
        self.committed_line_count += len(lines)
        return lines

    def finalize_and_drain(self) -> List[Line]:
        source = self.finalize_and_drain_source()
        lines = _source_to_plain_lines(source)
        self.committed_line_count = 0
        return lines


def test_cwd() -> Path:
    """Return a stable temporary cwd analogue for parity helpers."""

    return Path(tempfile.gettempdir())


def simulate_stream_markdown_for_tests(deltas: Iterable[str], finalize: bool) -> list[Line]:
    """Mirror Rust's stream simulation helper at the source-boundary level."""

    collector = MarkdownStreamCollector.new(None, test_cwd())
    lines: List[Line] = []
    for delta in deltas:
        collector.push_delta(delta)
        if "\n" in delta:
            lines.extend(collector.commit_complete_lines())
    if finalize:
        lines.extend(collector.finalize_and_drain())
    return lines


__all__ = [
    "RUST_MODULE",
    "MarkdownStreamCollector",
    "simulate_stream_markdown_for_tests",
    "test_cwd",
]
