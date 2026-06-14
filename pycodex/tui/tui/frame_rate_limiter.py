"""Frame draw rate limiting helpers.

Rust counterpart: ``codex-rs/tui/src/tui/frame_rate_limiter.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from numbers import Real
from typing import Any

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="tui::frame_rate_limiter",
    source="codex/codex-rs/tui/src/tui/frame_rate_limiter.rs",
    status="complete",
)

# Rust: Duration::from_nanos(8_333_334), a 120 FPS minimum frame interval.
# Python keeps the exact nanosecond count for deterministic tests and integer
# monotonic-clock callers.
MIN_FRAME_INTERVAL = 8_333_334


def _add_min_interval(value: Any) -> Any:
    if isinstance(value, datetime):
        return value + timedelta(seconds=MIN_FRAME_INTERVAL / 1_000_000_000)
    if isinstance(value, Real):
        return value + MIN_FRAME_INTERVAL
    try:
        return value + MIN_FRAME_INTERVAL
    except TypeError as exc:
        raise TypeError(
            "FrameRateLimiter deadlines must support addition with "
            "MIN_FRAME_INTERVAL"
        ) from exc


@dataclass
class FrameRateLimiter:
    """Clamp draw deadlines to the Rust module's 120 FPS minimum interval."""

    last_emitted_at: Any = None

    def clamp_deadline(self, requested: Any) -> Any:
        """Return ``requested`` unless it is earlier than the next allowed draw."""

        if self.last_emitted_at is None:
            return requested
        min_allowed = _add_min_interval(self.last_emitted_at)
        return max(requested, min_allowed)

    def mark_emitted(self, emitted_at: Any) -> None:
        """Record the instant at which a draw notification was emitted."""

        self.last_emitted_at = emitted_at


def default_does_not_clamp() -> bool:
    """Executable Python copy of the Rust default_does_not_clamp test."""

    t0 = 1_000_000_000
    limiter = FrameRateLimiter()
    return limiter.clamp_deadline(t0) == t0


def clamps_to_min_interval_since_last_emit() -> bool:
    """Executable Python copy of the Rust min-interval clamp test."""

    t0 = 1_000_000_000
    limiter = FrameRateLimiter()
    if limiter.clamp_deadline(t0) != t0:
        return False
    limiter.mark_emitted(t0)
    too_soon = t0 + 1_000_000
    return limiter.clamp_deadline(too_soon) == t0 + MIN_FRAME_INTERVAL


__all__ = [
    "FrameRateLimiter",
    "MIN_FRAME_INTERVAL",
    "RUST_MODULE",
    "clamps_to_min_interval_since_last_emit",
    "default_does_not_clamp",
]
