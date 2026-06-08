from __future__ import annotations

from types import SimpleNamespace

import pytest

from pycodex.core.state import TaskKind
from pycodex.core.tasks.regular import RegularTask, SessionStartupPrewarmResolution


class Timing:
    async def started_at_unix_secs(self) -> int:
        return 123


class InputQueue:
    def __init__(self, pending: list[bool]) -> None:
        self.pending = pending
        self.seen_active_turns: list[object] = []

    async def has_pending_input(self, active_turn: object) -> bool:
        self.seen_active_turns.append(active_turn)
        return self.pending.pop(0)


class CancellationToken:
    def __init__(self) -> None:
        self.children = 0

    def child_token(self) -> str:
        self.children += 1
        return f"child-{self.children}"


def turn_context() -> SimpleNamespace:
    return SimpleNamespace(
        sub_id="turn-1",
        trace_id="trace-1",
        turn_timing_state=Timing(),
        model_context_window=lambda: 128000,
        collaboration_mode=SimpleNamespace(mode="default"),
    )


def session_context(session: object, extension_data: object = "ext") -> SimpleNamespace:
    return SimpleNamespace(
        clone_session=lambda: session,
        turn_extension_data=lambda: extension_data,
    )


def test_regular_task_identity_matches_rust_session_task_contract() -> None:
    # Rust source: codex-rs/core/src/tasks/regular.rs
    # Contract: RegularTask::new, kind, and span_name.
    task = RegularTask.new()

    assert task.kind() == TaskKind.REGULAR
    assert task.span_name() == "session_task.turn"


@pytest.mark.asyncio
async def test_regular_task_emits_turn_started_and_runs_until_no_pending_input() -> None:
    # Rust source: RegularTask::run.
    # Contract: TurnStarted is emitted inline, server reasoning is reset,
    # prewarmed session is used once, and pending input causes another run_turn
    # with empty input.
    events: list[object] = []
    reasoning_values: list[bool] = []
    queue = InputQueue([True, False])

    async def consume_startup_prewarm_for_regular_turn(_token: object) -> object:
        return SimpleNamespace(kind=SessionStartupPrewarmResolution.READY, client_session="prewarm-1")

    session = SimpleNamespace(
        active_turn="active-turn",
        input_queue=queue,
        send_event=lambda _ctx, event: events.append(event),
        set_server_reasoning_included=lambda included: reasoning_values.append(included),
        consume_startup_prewarm_for_regular_turn=consume_startup_prewarm_for_regular_turn,
    )
    calls: list[tuple[object, object, object, list[object], object, object]] = []

    class Runner:
        async def run_turn(
            self,
            sess: object,
            ctx: object,
            turn_extension_data: object,
            input_items: list[object],
            prewarmed_client_session: object,
            child_token: object,
        ) -> str:
            calls.append((sess, ctx, turn_extension_data, input_items, prewarmed_client_session, child_token))
            return f"message-{len(calls)}"

    token = CancellationToken()
    ctx = turn_context()

    result = await RegularTask().run(session_context(session), ctx, ["initial"], token, Runner())

    assert result == "message-2"
    assert events[0].type == "task_started"
    assert events[0].payload.turn_id == "turn-1"
    assert events[0].payload.trace_id == "trace-1"
    assert events[0].payload.started_at == 123
    assert events[0].payload.model_context_window == 128000
    assert events[0].payload.collaboration_mode_kind == "default"
    assert reasoning_values == [False]
    assert calls[0] == (session, ctx, "ext", ["initial"], "prewarm-1", "child-1")
    assert calls[1] == (session, ctx, "ext", [], None, "child-2")
    assert queue.seen_active_turns == ["active-turn", "active-turn"]


@pytest.mark.asyncio
async def test_regular_task_cancelled_prewarm_returns_without_running_turn() -> None:
    # Rust source: RegularTask::run returns None when startup prewarm
    # resolution is Cancelled.
    events: list[object] = []

    async def consume_startup_prewarm_for_regular_turn(_token: object) -> str:
        return SessionStartupPrewarmResolution.CANCELLED

    session = SimpleNamespace(
        send_event=lambda _ctx, event: events.append(event),
        set_server_reasoning_included=lambda _included: None,
        consume_startup_prewarm_for_regular_turn=consume_startup_prewarm_for_regular_turn,
    )

    class Runner:
        async def run_turn(self, *_args: object) -> str:
            raise AssertionError("run_turn should not be called after cancelled prewarm")

    result = await RegularTask().run(session_context(session), turn_context(), ["input"], CancellationToken(), Runner())

    assert result is None
    assert events[0].type == "task_started"
