"""Adaptive streaming chunking policy for the Python TUI port.

Upstream source: ``codex/codex-rs/tui/src/streaming/chunking.rs``.
The Rust module decides when live streamed rows should switch from smooth
single-line draining to catch-up batch draining under backlog pressure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="streaming::chunking", source="codex/codex-rs/tui/src/streaming/chunking.rs")

# Durations are represented as seconds to keep the policy dependency-free while
# preserving Rust's millisecond thresholds exactly enough for behavior tests.
ENTER_QUEUE_DEPTH_LINES = 8
ENTER_OLDEST_AGE = 0.120

EXIT_QUEUE_DEPTH_LINES = 2
EXIT_OLDEST_AGE = 0.040
EXIT_HOLD = 0.250

REENTER_CATCH_UP_HOLD = 0.250

SEVERE_QUEUE_DEPTH_LINES = 64
SEVERE_OLDEST_AGE = 0.300


class ChunkingMode(Enum):
    """Streaming drain mode, mirroring Rust ``ChunkingMode``."""

    SMOOTH = "Smooth"
    CATCH_UP = "CatchUp"


@dataclass(frozen=True)
class QueueSnapshot:
    """Snapshot of queued display rows used by the adaptive policy."""

    queued_lines: int
    oldest_age: float | None = None


@dataclass(frozen=True)
class DrainPlan:
    """Drain plan returned by ``AdaptiveChunkingPolicy.decide``."""

    kind: str
    batch_size: int | None = None

    @classmethod
    def single(cls) -> "DrainPlan":
        return cls("Single", None)

    @classmethod
    def batch(cls, batch_size: int) -> "DrainPlan":
        return cls("Batch", max(1, int(batch_size)))

    def is_single(self) -> bool:
        return self.kind == "Single"

    def is_batch(self) -> bool:
        return self.kind == "Batch"


@dataclass(frozen=True)
class ChunkingDecision:
    """Mode transition and drain decision for one policy tick."""

    mode: ChunkingMode
    entered_catch_up: bool
    drain_plan: DrainPlan


@dataclass
class AdaptiveChunkingPolicy:
    """Hysteresis-based streaming chunking policy.

    This follows the Rust policy: enter catch-up under depth/age pressure, stay
    there until the backlog remains below the exit thresholds for ``EXIT_HOLD``,
    and suppress immediate re-entry unless the backlog is severe.
    """

    _mode: ChunkingMode = ChunkingMode.SMOOTH
    below_exit_threshold_since: float | None = None
    last_catch_up_exit_at: float | None = None

    def mode(self) -> ChunkingMode:
        return self._mode

    def reset(self) -> None:
        self._mode = ChunkingMode.SMOOTH
        self.below_exit_threshold_since = None
        self.last_catch_up_exit_at = None

    def decide(self, snapshot: QueueSnapshot, now: float | int | timedelta) -> ChunkingDecision:
        now_seconds = _duration_seconds(now)

        if snapshot.queued_lines == 0:
            if self._mode is ChunkingMode.CATCH_UP:
                self.note_catch_up_exit(now_seconds)
            self._mode = ChunkingMode.SMOOTH
            self.below_exit_threshold_since = None
            return ChunkingDecision(ChunkingMode.SMOOTH, False, DrainPlan.single())

        entered_catch_up = False
        if self._mode is ChunkingMode.SMOOTH:
            entered_catch_up = self.maybe_enter_catch_up(snapshot, now_seconds)
        else:
            self.maybe_exit_catch_up(snapshot, now_seconds)

        drain_plan = DrainPlan.single()
        if self._mode is ChunkingMode.CATCH_UP:
            drain_plan = DrainPlan.batch(snapshot.queued_lines)

        return ChunkingDecision(self._mode, entered_catch_up, drain_plan)

    def maybe_enter_catch_up(self, snapshot: QueueSnapshot, now: float | int | timedelta) -> bool:
        now_seconds = _duration_seconds(now)
        if not should_enter_catch_up(snapshot):
            return False
        if self.reentry_hold_active(now_seconds) and not is_severe_backlog(snapshot):
            return False
        self._mode = ChunkingMode.CATCH_UP
        self.below_exit_threshold_since = None
        return True

    def maybe_exit_catch_up(self, snapshot: QueueSnapshot, now: float | int | timedelta) -> None:
        now_seconds = _duration_seconds(now)
        if not should_exit_catch_up(snapshot):
            self.below_exit_threshold_since = None
            return

        if self.below_exit_threshold_since is None:
            self.below_exit_threshold_since = now_seconds
            return

        if now_seconds - self.below_exit_threshold_since >= EXIT_HOLD:
            self._mode = ChunkingMode.SMOOTH
            self.below_exit_threshold_since = None
            self.note_catch_up_exit(now_seconds)

    def note_catch_up_exit(self, now: float | int | timedelta) -> None:
        self.last_catch_up_exit_at = _duration_seconds(now)

    def reentry_hold_active(self, now: float | int | timedelta) -> bool:
        if self.last_catch_up_exit_at is None:
            return False
        return _duration_seconds(now) - self.last_catch_up_exit_at < REENTER_CATCH_UP_HOLD


def should_enter_catch_up(snapshot: QueueSnapshot) -> bool:
    if snapshot.queued_lines >= ENTER_QUEUE_DEPTH_LINES:
        return True
    return snapshot.oldest_age is not None and snapshot.oldest_age >= ENTER_OLDEST_AGE


def should_exit_catch_up(snapshot: QueueSnapshot) -> bool:
    return (
        snapshot.queued_lines <= EXIT_QUEUE_DEPTH_LINES
        and snapshot.oldest_age is not None
        and snapshot.oldest_age <= EXIT_OLDEST_AGE
    )


def is_severe_backlog(snapshot: QueueSnapshot) -> bool:
    if snapshot.queued_lines >= SEVERE_QUEUE_DEPTH_LINES:
        return True
    return snapshot.oldest_age is not None and snapshot.oldest_age >= SEVERE_OLDEST_AGE


def snapshot(queued_lines: int, oldest_age_ms: int | float | None) -> QueueSnapshot:
    """Test/helper constructor matching Rust tests' millisecond snapshot helper."""

    oldest_age = None if oldest_age_ms is None else float(oldest_age_ms) / 1000.0
    return QueueSnapshot(int(queued_lines), oldest_age)


def _duration_seconds(value: float | int | timedelta) -> float:
    if isinstance(value, timedelta):
        return value.total_seconds()
    return float(value)


__all__ = [
    "AdaptiveChunkingPolicy",
    "ChunkingDecision",
    "ChunkingMode",
    "DrainPlan",
    "ENTER_OLDEST_AGE",
    "ENTER_QUEUE_DEPTH_LINES",
    "EXIT_HOLD",
    "EXIT_OLDEST_AGE",
    "EXIT_QUEUE_DEPTH_LINES",
    "QueueSnapshot",
    "REENTER_CATCH_UP_HOLD",
    "RUST_MODULE",
    "SEVERE_OLDEST_AGE",
    "SEVERE_QUEUE_DEPTH_LINES",
    "is_severe_backlog",
    "should_enter_catch_up",
    "should_exit_catch_up",
    "snapshot",
]
