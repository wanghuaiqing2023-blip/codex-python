"""Goal lifecycle metrics owned by ``codex-goal-extension::metrics``."""

from __future__ import annotations

from typing import Any

from pycodex.otel.metrics.names import GOAL_BLOCKED_METRIC
from pycodex.otel.metrics.names import GOAL_BUDGET_LIMITED_METRIC
from pycodex.otel.metrics.names import GOAL_COMPLETED_METRIC
from pycodex.otel.metrics.names import GOAL_CREATED_METRIC
from pycodex.otel.metrics.names import GOAL_DURATION_SECONDS_METRIC
from pycodex.otel.metrics.names import GOAL_RESUMED_METRIC
from pycodex.otel.metrics.names import GOAL_TOKEN_COUNT_METRIC
from pycodex.otel.metrics.names import GOAL_USAGE_LIMITED_METRIC
from pycodex.state import ThreadGoalStatus


class GoalMetrics:
    def __init__(self, metrics_client: Any | None = None) -> None:
        self.metrics_client = metrics_client

    def record_created(self) -> None:
        self._counter(GOAL_CREATED_METRIC)

    def record_resumed(self) -> None:
        self._counter(GOAL_RESUMED_METRIC)

    def record_resumed_if_status_changed(
        self,
        previous_status: ThreadGoalStatus | None,
        goal_status: ThreadGoalStatus,
    ) -> None:
        if goal_status is ThreadGoalStatus.ACTIVE and previous_status in {
            ThreadGoalStatus.PAUSED,
            ThreadGoalStatus.BLOCKED,
            ThreadGoalStatus.USAGE_LIMITED,
        }:
            self.record_resumed()

    def record_terminal_if_status_changed(
        self,
        previous_status: ThreadGoalStatus | None,
        goal: Any,
    ) -> None:
        if previous_status is goal.status:
            return
        counter = {
            ThreadGoalStatus.BLOCKED: GOAL_BLOCKED_METRIC,
            ThreadGoalStatus.USAGE_LIMITED: GOAL_USAGE_LIMITED_METRIC,
            ThreadGoalStatus.BUDGET_LIMITED: GOAL_BUDGET_LIMITED_METRIC,
            ThreadGoalStatus.COMPLETE: GOAL_COMPLETED_METRIC,
        }.get(goal.status)
        if counter is None or self.metrics_client is None:
            return
        status_tag = (("status", goal.status.value),)
        self.metrics_client.counter(counter, 1, ())
        self.metrics_client.histogram(
            GOAL_TOKEN_COUNT_METRIC,
            goal.tokens_used,
            status_tag,
        )
        self.metrics_client.histogram(
            GOAL_DURATION_SECONDS_METRIC,
            goal.time_used_seconds,
            status_tag,
        )

    def _counter(self, name: str) -> None:
        if self.metrics_client is not None:
            self.metrics_client.counter(name, 1, ())


__all__ = ["GoalMetrics"]
