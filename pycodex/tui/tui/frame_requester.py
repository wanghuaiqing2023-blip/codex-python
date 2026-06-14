"""Frame draw scheduling utilities for the TUI.

Rust counterpart: ``codex-rs/tui/src/tui/frame_requester.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule
from .frame_rate_limiter import MIN_FRAME_INTERVAL, FrameRateLimiter


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="tui::frame_requester",
    source="codex/codex-rs/tui/src/tui/frame_requester.rs",
    status="complete_slice",
)


@dataclass
class DrawChannel:
    """Semantic broadcast channel collecting draw notifications."""

    notifications: list[None] = field(default_factory=list)

    def send(self) -> None:
        self.notifications.append(None)

    def recv_count(self) -> int:
        return len(self.notifications)


@dataclass
class FrameScheduler:
    """Coalesces requested draw deadlines and emits draw notifications."""

    draw_tx: DrawChannel = field(default_factory=DrawChannel)
    rate_limiter: FrameRateLimiter = field(default_factory=FrameRateLimiter)
    now: int = 0
    next_deadline: int | None = None
    closed: bool = False

    @classmethod
    def new(cls, draw_tx: DrawChannel | None = None) -> "FrameScheduler":
        return cls(draw_tx=draw_tx if draw_tx is not None else DrawChannel())

    def request_at(self, draw_at: int) -> None:
        if self.closed:
            return
        clamped = self.rate_limiter.clamp_deadline(int(draw_at))
        self.next_deadline = (
            clamped if self.next_deadline is None else min(self.next_deadline, clamped)
        )

    def advance_to(self, now: int) -> int:
        self.now = int(now)
        emitted = 0
        if self.next_deadline is not None and self.now >= self.next_deadline:
            target = self.next_deadline
            self.next_deadline = None
            self.rate_limiter.mark_emitted(target)
            self.draw_tx.send()
            emitted = 1
        return emitted

    def advance_by(self, dur: int) -> int:
        return self.advance_to(self.now + int(dur))

    async def run(self) -> None:
        """Async shape placeholder for Rust's spawned scheduler loop.

        The Python port exposes deterministic ``request_at``/``advance_*``
        methods instead of running an infinite background task.
        """

        return None


@dataclass
class FrameRequester:
    """Handle that schedules draw requests on a shared scheduler."""

    scheduler: FrameScheduler = field(default_factory=FrameScheduler)

    @classmethod
    def new(cls, draw_tx: DrawChannel | None = None) -> "FrameRequester":
        return cls(FrameScheduler.new(draw_tx))

    def schedule_frame(self) -> None:
        self.scheduler.request_at(self.scheduler.now)

    def schedule_frame_in(self, dur: int) -> None:
        self.scheduler.request_at(self.scheduler.now + int(dur))

    @classmethod
    def test_dummy(cls) -> "FrameRequester":
        scheduler = FrameScheduler.new(DrawChannel())
        scheduler.closed = True
        return cls(scheduler)


def test_schedule_frame_immediate_triggers_once() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame()
    requester.scheduler.advance_by(1)
    return requester.scheduler.draw_tx.recv_count() == 1


def test_schedule_frame_in_triggers_at_delay() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame_in(50_000_000)
    requester.scheduler.advance_by(30_000_000)
    early = requester.scheduler.draw_tx.recv_count() == 0
    requester.scheduler.advance_by(25_000_000)
    return early and requester.scheduler.draw_tx.recv_count() == 1


def test_coalesces_multiple_requests_into_single_draw() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame()
    requester.schedule_frame()
    requester.schedule_frame()
    requester.scheduler.advance_by(1)
    return requester.scheduler.draw_tx.recv_count() == 1


def test_coalesces_mixed_immediate_and_delayed_requests() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame_in(100_000_000)
    requester.schedule_frame()
    requester.scheduler.advance_by(1)
    requester.scheduler.advance_by(120_000_000)
    return requester.scheduler.draw_tx.recv_count() == 1


def test_limits_draw_notifications_to_120fps() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame()
    requester.scheduler.advance_by(1)
    first = requester.scheduler.draw_tx.recv_count() == 1
    requester.schedule_frame()
    requester.scheduler.advance_by(1)
    too_early = requester.scheduler.draw_tx.recv_count() == 1
    requester.scheduler.advance_by(MIN_FRAME_INTERVAL)
    return first and too_early and requester.scheduler.draw_tx.recv_count() == 2


def test_rate_limit_clamps_early_delayed_requests() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame()
    requester.scheduler.advance_by(1)
    first = requester.scheduler.draw_tx.recv_count() == 1
    requester.schedule_frame_in(1_000_000)
    requester.scheduler.advance_by(MIN_FRAME_INTERVAL // 2)
    too_early = requester.scheduler.draw_tx.recv_count() == 1
    requester.scheduler.advance_by(MIN_FRAME_INTERVAL)
    return first and too_early and requester.scheduler.draw_tx.recv_count() == 2


def test_rate_limit_does_not_delay_future_draws() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame()
    requester.scheduler.advance_by(1)
    first = requester.scheduler.draw_tx.recv_count() == 1
    requester.schedule_frame_in(50_000_000)
    requester.scheduler.advance_by(49_000_000)
    early = requester.scheduler.draw_tx.recv_count() == 1
    requester.scheduler.advance_by(1_000_000)
    return first and early and requester.scheduler.draw_tx.recv_count() == 2


def test_multiple_delayed_requests_coalesce_to_earliest() -> bool:
    requester = FrameRequester.new()
    requester.schedule_frame_in(100_000_000)
    requester.schedule_frame_in(20_000_000)
    requester.schedule_frame_in(120_000_000)
    requester.scheduler.advance_by(10_000_000)
    early = requester.scheduler.draw_tx.recv_count() == 0
    requester.scheduler.advance_by(20_000_000)
    requester.scheduler.advance_by(120_000_000)
    return early and requester.scheduler.draw_tx.recv_count() == 1


__all__ = [
    "DrawChannel",
    "FrameRequester",
    "FrameScheduler",
    "RUST_MODULE",
    "test_coalesces_mixed_immediate_and_delayed_requests",
    "test_coalesces_multiple_requests_into_single_draw",
    "test_limits_draw_notifications_to_120fps",
    "test_multiple_delayed_requests_coalesce_to_earliest",
    "test_rate_limit_clamps_early_delayed_requests",
    "test_rate_limit_does_not_delay_future_draws",
    "test_schedule_frame_immediate_triggers_once",
    "test_schedule_frame_in_triggers_at_delay",
]
