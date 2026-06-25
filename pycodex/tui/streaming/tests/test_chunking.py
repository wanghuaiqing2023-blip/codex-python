"""Parity tests for ``codex-tui/src/streaming/chunking.rs``.

The Rust tests live in the module's local ``#[cfg(test)]`` block and define the
behavior contract for adaptive smooth/catch-up streaming.
"""

from pycodex.tui.streaming.chunking import (
    AdaptiveChunkingPolicy,
    ChunkingMode,
    DrainPlan,
    QueueSnapshot,
    snapshot,
)


def test_smooth_mode_is_default() -> None:
    # Rust: codex-tui streaming::chunking::tests::smooth_mode_is_default
    assert AdaptiveChunkingPolicy().mode() is ChunkingMode.SMOOTH


def test_enters_catch_up_on_depth_threshold() -> None:
    # Rust: enters_catch_up_on_depth_threshold
    policy = AdaptiveChunkingPolicy()
    decision = policy.decide(snapshot(8, 1), 0.0)
    assert decision.mode is ChunkingMode.CATCH_UP
    assert decision.entered_catch_up is True
    assert decision.drain_plan == DrainPlan.batch(8)


def test_enters_catch_up_on_age_threshold() -> None:
    # Rust: enters_catch_up_on_age_threshold
    policy = AdaptiveChunkingPolicy()
    decision = policy.decide(snapshot(1, 120), 0.0)
    assert decision.mode is ChunkingMode.CATCH_UP
    assert decision.entered_catch_up is True
    assert decision.drain_plan == DrainPlan.batch(1)


def test_severe_backlog_uses_faster_paced_batches() -> None:
    # Rust: severe_backlog_uses_faster_paced_batches
    policy = AdaptiveChunkingPolicy()
    decision = policy.decide(snapshot(64, 1), 0.0)
    assert decision.mode is ChunkingMode.CATCH_UP
    assert decision.drain_plan == DrainPlan.batch(64)


def test_catch_up_batch_drains_current_backlog() -> None:
    # Rust: catch_up_batch_drains_current_backlog
    policy = AdaptiveChunkingPolicy()
    first = policy.decide(snapshot(8, 1), 0.0)
    second = policy.decide(snapshot(5, 80), 0.010)
    assert first.drain_plan == DrainPlan.batch(8)
    assert second.mode is ChunkingMode.CATCH_UP
    assert second.entered_catch_up is False
    assert second.drain_plan == DrainPlan.batch(5)


def test_exits_catch_up_after_hysteresis_hold() -> None:
    # Rust: exits_catch_up_after_hysteresis_hold
    policy = AdaptiveChunkingPolicy()
    assert policy.decide(snapshot(8, 1), 0.0).mode is ChunkingMode.CATCH_UP

    still_catch_up = policy.decide(snapshot(2, 40), 0.100)
    assert still_catch_up.mode is ChunkingMode.CATCH_UP

    exited = policy.decide(snapshot(2, 40), 0.350)
    assert exited.mode is ChunkingMode.SMOOTH
    assert exited.drain_plan == DrainPlan.single()


def test_drops_back_to_smooth_when_idle() -> None:
    # Rust: drops_back_to_smooth_when_idle
    policy = AdaptiveChunkingPolicy()
    assert policy.decide(snapshot(8, 1), 0.0).mode is ChunkingMode.CATCH_UP
    idle = policy.decide(QueueSnapshot(0, None), 0.010)
    assert idle.mode is ChunkingMode.SMOOTH
    assert idle.entered_catch_up is False
    assert idle.drain_plan == DrainPlan.single()
    assert policy.reentry_hold_active(0.100) is True


def test_holds_reentry_after_catch_up_exit() -> None:
    # Rust: holds_reentry_after_catch_up_exit
    policy = AdaptiveChunkingPolicy()
    assert policy.decide(snapshot(8, 1), 0.0).mode is ChunkingMode.CATCH_UP
    assert policy.decide(snapshot(2, 40), 0.100).mode is ChunkingMode.CATCH_UP
    assert policy.decide(snapshot(2, 40), 0.350).mode is ChunkingMode.SMOOTH

    held = policy.decide(snapshot(8, 1), 0.400)
    assert held.mode is ChunkingMode.SMOOTH
    assert held.entered_catch_up is False
    assert held.drain_plan == DrainPlan.single()

    reentered = policy.decide(snapshot(8, 1), 0.601)
    assert reentered.mode is ChunkingMode.CATCH_UP
    assert reentered.entered_catch_up is True


def test_severe_backlog_can_reenter_during_hold() -> None:
    # Rust: severe_backlog_can_reenter_during_hold
    policy = AdaptiveChunkingPolicy()
    assert policy.decide(snapshot(8, 1), 0.0).mode is ChunkingMode.CATCH_UP
    assert policy.decide(snapshot(2, 40), 0.100).mode is ChunkingMode.CATCH_UP
    assert policy.decide(snapshot(2, 40), 0.350).mode is ChunkingMode.SMOOTH

    severe = policy.decide(snapshot(64, 1), 0.400)
    assert severe.mode is ChunkingMode.CATCH_UP
    assert severe.entered_catch_up is True
    assert severe.drain_plan == DrainPlan.batch(64)


def test_exit_requires_oldest_age_to_be_known() -> None:
    # Rust source: should_exit_catch_up uses Option::is_some_and, so None does not exit.
    policy = AdaptiveChunkingPolicy()
    assert policy.decide(snapshot(8, 1), 0.0).mode is ChunkingMode.CATCH_UP
    decision = policy.decide(QueueSnapshot(1, None), 1.0)
    assert decision.mode is ChunkingMode.CATCH_UP
