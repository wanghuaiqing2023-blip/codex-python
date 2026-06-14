"""Parity tests for ``codex-tui/src/streaming/commit_tick.rs``.

The Rust module has no local ``#[cfg(test)]`` block. These tests anchor the
module-scoped behavior contract from the Rust source: queue snapshot merging,
policy resolution, scope suppression, and applying drain plans in controller
order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from pycodex.tui.streaming.chunking import AdaptiveChunkingPolicy, ChunkingMode, DrainPlan, QueueSnapshot
from pycodex.tui.streaming.commit_tick import (
    CommitTickOutput,
    CommitTickScope,
    apply_commit_tick_plan,
    default,
    max_duration,
    run_commit_tick,
    stream_queue_snapshot,
)


@dataclass
class FakeController:
    queued: int
    age: float | None
    single_result: tuple[Any | None, bool] = (None, True)
    batch_result: tuple[Any | None, bool] = (None, True)
    calls: list[tuple[str, int | None]] = field(default_factory=list)

    def queued_lines(self) -> int:
        return self.queued

    def oldest_queued_age(self, now: float) -> float | None:
        return self.age

    def on_commit_tick(self) -> tuple[Any | None, bool]:
        self.calls.append(("single", None))
        return self.single_result

    def on_commit_tick_batch(self, max_lines: int) -> tuple[Any | None, bool]:
        self.calls.append(("batch", max_lines))
        return self.batch_result


def test_default_commit_tick_output_matches_rust_default() -> None:
    # Rust: CommitTickOutput::default
    assert default() == CommitTickOutput(cells=[], has_controller=False, all_idle=True)


def test_stream_queue_snapshot_sums_depth_and_keeps_max_oldest_age() -> None:
    # Rust: stream_queue_snapshot
    stream = FakeController(queued=3, age=0.010)
    plan = FakeController(queued=5, age=0.250)
    assert stream_queue_snapshot(stream, plan, 1.0) == QueueSnapshot(8, 0.250)


def test_stream_queue_snapshot_preserves_present_age_when_other_missing() -> None:
    # Rust: max_duration helper used by stream_queue_snapshot
    stream = FakeController(queued=1, age=None)
    plan = FakeController(queued=2, age=timedelta(milliseconds=80))
    assert stream_queue_snapshot(stream, plan, 1.0) == QueueSnapshot(3, 0.080)


def test_max_duration_matches_optional_duration_rules() -> None:
    # Rust: max_duration
    assert max_duration(None, None) is None
    assert max_duration(0.010, None) == 0.010
    assert max_duration(None, timedelta(milliseconds=20)) == 0.020
    assert max_duration(0.010, 0.020) == 0.020


def test_apply_single_plan_drains_stream_then_plan_and_tracks_idle() -> None:
    # Rust: apply_commit_tick_plan with DrainPlan::Single
    stream = FakeController(1, 0.0, single_result=("stream-cell", True))
    plan = FakeController(1, 0.0, single_result=("plan-cell", False))
    output = apply_commit_tick_plan(DrainPlan.single(), stream, plan)
    assert output.cells == ["stream-cell", "plan-cell"]
    assert output.has_controller is True
    assert output.all_idle is False
    assert stream.calls == [("single", None)]
    assert plan.calls == [("single", None)]


def test_apply_batch_plan_uses_batch_api_on_both_controllers() -> None:
    # Rust: drain_stream_controller / drain_plan_stream_controller with DrainPlan::Batch
    stream = FakeController(8, 0.0, batch_result=("stream-batch", True))
    plan = FakeController(4, 0.0, batch_result=(None, True))
    output = apply_commit_tick_plan(DrainPlan.batch(8), stream, plan)
    assert output.cells == ["stream-batch"]
    assert output.has_controller is True
    assert output.all_idle is True
    assert stream.calls == [("batch", 8)]
    assert plan.calls == [("batch", 8)]


def test_run_commit_tick_catch_up_only_suppresses_smooth_drain() -> None:
    # Rust: run_commit_tick scope == CatchUpOnly and decision mode != CatchUp returns default.
    policy = AdaptiveChunkingPolicy()
    stream = FakeController(queued=1, age=0.001, single_result=("cell", False))
    output = run_commit_tick(policy, stream, None, CommitTickScope.CATCH_UP_ONLY, 0.0)
    assert output == CommitTickOutput()
    assert stream.calls == []
    assert policy.mode() is ChunkingMode.SMOOTH


def test_run_commit_tick_any_mode_applies_smooth_single_drain() -> None:
    # Rust: run_commit_tick applies decision.drain_plan when scope allows it.
    policy = AdaptiveChunkingPolicy()
    stream = FakeController(queued=1, age=0.001, single_result=("cell", True))
    output = run_commit_tick(policy, stream, None, CommitTickScope.ANY_MODE, 0.0)
    assert output.cells == ["cell"]
    assert output.has_controller is True
    assert output.all_idle is True
    assert stream.calls == [("single", None)]


def test_run_commit_tick_enters_catch_up_and_batches_current_backlog() -> None:
    # Rust: chunking decision is resolved before applying the drain plan.
    policy = AdaptiveChunkingPolicy()
    stream = FakeController(queued=8, age=0.001, batch_result=("batch", False))
    output = run_commit_tick(policy, stream, None, CommitTickScope.CATCH_UP_ONLY, 0.0)
    assert policy.mode() is ChunkingMode.CATCH_UP
    assert output.cells == ["batch"]
    assert output.all_idle is False
    assert stream.calls == [("batch", 8)]
