"""Goal event emitter aligned with ``codex-goal-extension::events``."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import Event, EventMsg, ThreadGoal, ThreadGoalUpdatedEvent


@dataclass(frozen=True)
class GoalEventEmitter:
    sink: Any

    async def thread_goal_updated(
        self,
        event_id: str,
        turn_id: str | None,
        goal: ThreadGoal,
    ) -> None:
        event = Event(
            id=str(event_id),
            msg=EventMsg.with_payload(
                "thread_goal_updated",
                ThreadGoalUpdatedEvent(
                    thread_id=goal.thread_id,
                    turn_id=None if turn_id is None else str(turn_id),
                    goal=goal,
                ),
            ),
        )
        result = self.sink.emit(event)
        if inspect.isawaitable(result):
            await result


__all__ = ["GoalEventEmitter"]
