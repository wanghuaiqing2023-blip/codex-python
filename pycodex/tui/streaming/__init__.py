"""Streaming primitives used by the Python TUI transcript pipeline.

Upstream source: ``codex/codex-rs/tui/src/streaming/mod.rs``.
This module owns the small FIFO queue state used by streaming controllers; it
keeps markdown collection as a dependency boundary rather than implementing the
collector itself.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Union

from .._porting import RustTuiModule
from ..markdown_stream import MarkdownStreamCollector

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="streaming",
    source="codex/codex-rs/tui/src/streaming/mod.rs",
    status="complete",
)


@dataclass(frozen=True)
class QueuedLine:
    """One committed stream line plus its enqueue timestamp."""

    line: Any
    enqueued_at: float


@dataclass
class StreamState:
    """In-flight markdown stream state and FIFO queue of committed lines."""

    collector: Any
    queued_lines: List[QueuedLine] = field(default_factory=list)
    has_seen_delta: bool = False
    _clock: Callable[[], float] = time.monotonic

    @classmethod
    def new(
        cls,
        width: Optional[int],
        cwd: Union[str, Path],
        *,
        collector: Any = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> "StreamState":
        if collector is None:
            collector = MarkdownStreamCollector({"width": width, "cwd": Path(cwd)})
        return cls(collector=collector, _clock=clock)

    def clear(self) -> None:
        clear = getattr(self.collector, "clear", None)
        if clear is None:
            raise NotImplementedError("StreamState.clear requires collector.clear()")
        clear()
        self.queued_lines.clear()
        self.has_seen_delta = False

    def step(self) -> List[Any]:
        if not self.queued_lines:
            return []
        queued = self.queued_lines.pop(0)
        return [queued.line]

    def drain_n(self, max_lines: int) -> List[Any]:
        end = min(max(0, int(max_lines)), len(self.queued_lines))
        drained = self.queued_lines[:end]
        del self.queued_lines[:end]
        return [queued.line for queued in drained]

    def clear_queue(self) -> None:
        self.queued_lines.clear()

    def is_idle(self) -> bool:
        return not self.queued_lines

    def queued_len(self) -> int:
        return len(self.queued_lines)

    def oldest_queued_age(self, now: Optional[float] = None) -> Optional[float]:
        if not self.queued_lines:
            return None
        current = self._clock() if now is None else float(now)
        return max(0.0, current - self.queued_lines[0].enqueued_at)

    def enqueue(self, lines: List[Any], *, enqueued_at: Optional[float] = None) -> None:
        now = self._clock() if enqueued_at is None else float(enqueued_at)
        self.queued_lines.extend(QueuedLine(line=line, enqueued_at=now) for line in lines)


def test_cwd() -> Path:
    """Stable absolute cwd helper matching Rust tests' temp-dir intent."""

    return Path.cwd().resolve()


test_cwd.__test__ = False


__all__ = [
    "QueuedLine",
    "RUST_MODULE",
    "StreamState",
    "test_cwd",
]
