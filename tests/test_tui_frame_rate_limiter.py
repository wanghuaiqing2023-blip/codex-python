from datetime import datetime

from pycodex.tui.tui.frame_rate_limiter import (
    MIN_FRAME_INTERVAL,
    FrameRateLimiter,
    clamps_to_min_interval_since_last_emit,
    default_does_not_clamp,
)


def test_default_does_not_clamp_matches_rust() -> None:
    # Rust: codex-tui tui/frame_rate_limiter.rs default_does_not_clamp
    assert default_does_not_clamp()


def test_clamps_to_min_interval_since_last_emit_matches_rust() -> None:
    # Rust: codex-tui tui/frame_rate_limiter.rs clamps_to_min_interval_since_last_emit
    assert clamps_to_min_interval_since_last_emit()


def test_requested_after_min_interval_is_not_moved_back() -> None:
    # Rust uses requested.max(last + MIN_FRAME_INTERVAL).
    limiter = FrameRateLimiter()
    limiter.mark_emitted(10_000)
    requested = 10_000 + MIN_FRAME_INTERVAL + 5

    assert limiter.clamp_deadline(requested) == requested


def test_mark_emitted_replaces_previous_instant() -> None:
    # Rust stores only the most recent emitted draw instant.
    limiter = FrameRateLimiter()
    limiter.mark_emitted(10_000)
    limiter.mark_emitted(20_000)

    assert limiter.clamp_deadline(21_000) == 20_000 + MIN_FRAME_INTERVAL


def test_datetime_deadlines_use_same_min_interval_semantics() -> None:
    # Python semantic model also supports datetime-like monotonic stand-ins.
    t0 = datetime(2026, 6, 12, 0, 0, 0)
    limiter = FrameRateLimiter()
    limiter.mark_emitted(t0)

    assert limiter.clamp_deadline(t0) > t0
