"""Pull progress events/reporters for Rust ``codex-ollama/src/pull.rs``."""

from __future__ import annotations

from dataclasses import dataclass
import sys
import time
from typing import Callable, Protocol, TextIO, TypeAlias


@dataclass(frozen=True)
class Status:
    status: str


@dataclass(frozen=True)
class ChunkProgress:
    digest: str
    total: int | None = None
    completed: int | None = None


@dataclass(frozen=True)
class Success:
    pass


@dataclass(frozen=True)
class Error:
    message: str


PullEvent: TypeAlias = Status | ChunkProgress | Success | Error


class PullProgressReporter(Protocol):
    def on_event(self, event: PullEvent) -> None:
        """Observe one pull progress event."""


class CliProgressReporter:
    """Minimal CLI reporter mirroring Rust inline stderr rendering."""

    def __init__(
        self,
        writer: TextIO | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.printed_header = False
        self.last_line_len = 0
        self.last_completed_sum = 0
        self.last_instant = (clock or time.monotonic)()
        self.totals_by_digest: dict[str, tuple[int, int]] = {}
        self._writer = writer
        self._clock = clock or time.monotonic

    @property
    def writer(self) -> TextIO:
        return self._writer if self._writer is not None else sys.stderr

    def on_event(self, event: PullEvent) -> None:
        out = self.writer
        if isinstance(event, Status):
            if event.status.lower() == "pulling manifest":
                return
            pad = max(self.last_line_len - len(event.status), 0)
            out.write(f"\r{event.status}{' ' * pad}")
            self.last_line_len = len(event.status)
            out.flush()
            return

        if isinstance(event, ChunkProgress):
            current_total, current_completed = self.totals_by_digest.get(event.digest, (0, 0))
            if event.total is not None:
                current_total = event.total
            if event.completed is not None:
                current_completed = event.completed
            self.totals_by_digest[event.digest] = (current_total, current_completed)

            sum_total = sum(total for total, _completed in self.totals_by_digest.values())
            sum_completed = sum(completed for _total, completed in self.totals_by_digest.values())
            if sum_total <= 0:
                return

            if not self.printed_header:
                total_gb_for_header = sum_total / (1024.0 * 1024.0 * 1024.0)
                out.write("\r\x1b[2K")
                out.write(f"Downloading model: total {total_gb_for_header:.2f} GB\n")
                self.printed_header = True

            now = self._clock()
            dt = max(now - self.last_instant, 0.001)
            dbytes = max(sum_completed - self.last_completed_sum, 0)
            speed_mb_s = dbytes / (1024.0 * 1024.0) / dt
            self.last_completed_sum = sum_completed
            self.last_instant = now

            done_gb = sum_completed / (1024.0 * 1024.0 * 1024.0)
            total_gb = sum_total / (1024.0 * 1024.0 * 1024.0)
            pct = sum_completed * 100.0 / sum_total
            text = f"{done_gb:.2f}/{total_gb:.2f} GB ({pct:.1f}%) {speed_mb_s:.1f} MB/s"
            pad = max(self.last_line_len - len(text), 0)
            out.write(f"\r{text}{' ' * pad}")
            self.last_line_len = len(text)
            out.flush()
            return

        if isinstance(event, Error):
            return

        if isinstance(event, Success):
            out.write("\n")
            out.flush()


class TuiProgressReporter:
    """TUI reporter currently delegates to the CLI reporter, like Rust."""

    def __init__(self, reporter: CliProgressReporter | None = None) -> None:
        self.reporter = reporter if reporter is not None else CliProgressReporter()

    def on_event(self, event: PullEvent) -> None:
        self.reporter.on_event(event)


__all__ = [
    "ChunkProgress",
    "CliProgressReporter",
    "Error",
    "PullEvent",
    "PullProgressReporter",
    "Status",
    "Success",
    "TuiProgressReporter",
]
