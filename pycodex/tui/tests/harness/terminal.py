"""Terminal capture helpers for TUI automation tests.

Rust evidence:
- `codex-tui/tests/suite/vt100_live_commit.rs`
- `codex-tui/tests/suite/resize_reflow.rs`

Python uses a normalized text capture as the first virtual-terminal layer. It
does not claim exact ratatui cell parity; it gives stable assertions for product
paths that currently write ANSI to a terminal stream.
"""

from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass, field

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class TtyInput(io.StringIO):
    """String input stream that can opt into terminal-like `isatty()` behavior."""

    def __init__(self, value: str = "", *, is_tty: bool = False) -> None:
        super().__init__(value)
        self._is_tty = bool(is_tty)

    def isatty(self) -> bool:
        return self._is_tty


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


@dataclass
class TerminalCapture:
    stdout: io.StringIO = field(default_factory=io.StringIO)
    stderr: io.StringIO = field(default_factory=io.StringIO)

    def write_lines(self, lines: list[str]) -> None:
        self.stdout.write("\n".join(lines))
        if lines:
            self.stdout.write("\n")

    def raw_stdout(self) -> str:
        return self.stdout.getvalue()

    def raw_stderr(self) -> str:
        return self.stderr.getvalue()

    def text(self) -> str:
        return strip_ansi(self.raw_stdout())

    def combined_text(self) -> str:
        return strip_ansi(self.raw_stdout() + self.raw_stderr())

    def lines(self) -> list[str]:
        return self.text().splitlines()

    def first_row_containing(self, needle: str) -> int | None:
        for index, line in enumerate(self.lines()):
            if needle in line:
                return index
        return None

    def last_row_matching_prefix(self, prefix: str) -> int | None:
        row: int | None = None
        for index, line in enumerate(self.lines()):
            if line.lstrip().startswith(prefix):
                row = index
        return row

    def wait_for_text(self, needle: str, *, timeout: float = 1.0, interval: float = 0.01) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            text = self.text()
            if needle in text:
                return text
            time.sleep(interval)
        return self.text()
