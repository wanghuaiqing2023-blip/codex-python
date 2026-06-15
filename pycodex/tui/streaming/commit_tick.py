"""Commit-tick orchestration for streaming controllers.

Upstream source: ``codex/codex-rs/tui/src/streaming/commit_tick.rs``.
This module intentionally does not implement controller internals; it mirrors
Rust's orchestration boundary by querying queue pressure, resolving a chunking
policy decision, and applying the chosen drain plan to available controllers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, List, Optional, Protocol, Tuple, Union

from .._porting import RustTuiModule
from .chunking import AdaptiveChunkingPolicy, ChunkingDecision, ChunkingMode, DrainPlan, QueueSnapshot

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="streaming::commit_tick",
    source="codex/codex-rs/tui/src/streaming/commit_tick.rs",
    status="complete",
)


class CommitTickScope(Enum):
    """Whether a commit tick may drain in any mode or only in catch-up mode."""

    ANY_MODE = "AnyMode"
    CATCH_UP_ONLY = "CatchUpOnly"


@dataclass
class CommitTickOutput:
    """Output produced by a single commit tick."""

    cells: List[Any] = field(default_factory=list)
    has_controller: bool = False
    all_idle: bool = True


class _StreamControllerLike(Protocol):
    def queued_lines(self) -> int: ...

    def oldest_queued_age(self, now: Union[float, int, timedelta]) -> Optional[Union[float, int, timedelta]]: ...

    def on_commit_tick(self) -> Tuple[Optional[Any], bool]: ...

    def on_commit_tick_batch(self, max_lines: int) -> Tuple[Optional[Any], bool]: ...


def default() -> CommitTickOutput:
    """Return Rust ``CommitTickOutput::default`` semantics."""

    return CommitTickOutput()


def run_commit_tick(
    policy: AdaptiveChunkingPolicy,
    stream_controller: Optional[_StreamControllerLike],
    plan_stream_controller: Optional[_StreamControllerLike],
    scope: CommitTickScope,
    now: Union[float, int, timedelta],
) -> CommitTickOutput:
    snapshot = stream_queue_snapshot(stream_controller, plan_stream_controller, now)
    decision = resolve_chunking_plan(policy, snapshot, now)
    if scope is CommitTickScope.CATCH_UP_ONLY and decision.mode is not ChunkingMode.CATCH_UP:
        return CommitTickOutput()
    return apply_commit_tick_plan(decision.drain_plan, stream_controller, plan_stream_controller)


def stream_queue_snapshot(
    stream_controller: Optional[_StreamControllerLike],
    plan_stream_controller: Optional[_StreamControllerLike],
    now: Union[float, int, timedelta],
) -> QueueSnapshot:
    queued_lines = 0
    oldest_age: Optional[float] = None

    if stream_controller is not None:
        queued_lines += int(stream_controller.queued_lines())
        oldest_age = max_duration(oldest_age, stream_controller.oldest_queued_age(now))
    if plan_stream_controller is not None:
        queued_lines += int(plan_stream_controller.queued_lines())
        oldest_age = max_duration(oldest_age, plan_stream_controller.oldest_queued_age(now))

    return QueueSnapshot(queued_lines=queued_lines, oldest_age=oldest_age)


def resolve_chunking_plan(
    policy: AdaptiveChunkingPolicy,
    snapshot: QueueSnapshot,
    now: Union[float, int, timedelta],
) -> ChunkingDecision:
    # Rust logs mode transitions with tracing; Python preserves the state transition
    # contract and leaves observability to callers/tests.
    return policy.decide(snapshot, now)


def apply_commit_tick_plan(
    drain_plan: DrainPlan,
    stream_controller: Optional[_StreamControllerLike],
    plan_stream_controller: Optional[_StreamControllerLike],
) -> CommitTickOutput:
    output = CommitTickOutput()

    if stream_controller is not None:
        output.has_controller = True
        cell, is_idle = drain_stream_controller(stream_controller, drain_plan)
        if cell is not None:
            output.cells.append(cell)
        output.all_idle = output.all_idle and bool(is_idle)

    if plan_stream_controller is not None:
        output.has_controller = True
        cell, is_idle = drain_plan_stream_controller(plan_stream_controller, drain_plan)
        if cell is not None:
            output.cells.append(cell)
        output.all_idle = output.all_idle and bool(is_idle)

    return output


def drain_stream_controller(
    controller: _StreamControllerLike,
    drain_plan: DrainPlan,
) -> Tuple[Optional[Any], bool]:
    if drain_plan.is_single():
        return controller.on_commit_tick()
    return controller.on_commit_tick_batch(drain_plan.batch_size or 1)


def drain_plan_stream_controller(
    controller: _StreamControllerLike,
    drain_plan: DrainPlan,
) -> Tuple[Optional[Any], bool]:
    if drain_plan.is_single():
        return controller.on_commit_tick()
    return controller.on_commit_tick_batch(drain_plan.batch_size or 1)


def max_duration(
    lhs: Optional[Union[float, int, timedelta]],
    rhs: Optional[Union[float, int, timedelta]],
) -> Optional[float]:
    left = _duration_seconds_or_none(lhs)
    right = _duration_seconds_or_none(rhs)
    if left is None:
        return right
    if right is None:
        return left
    return max(left, right)


def _duration_seconds_or_none(value: Optional[Union[float, int, timedelta]]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, timedelta):
        return value.total_seconds()
    return float(value)


__all__ = [
    "CommitTickOutput",
    "CommitTickScope",
    "RUST_MODULE",
    "apply_commit_tick_plan",
    "default",
    "drain_plan_stream_controller",
    "drain_stream_controller",
    "max_duration",
    "resolve_chunking_plan",
    "run_commit_tick",
    "stream_queue_snapshot",
]
