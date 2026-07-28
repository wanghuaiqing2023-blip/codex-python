from types import SimpleNamespace

from pycodex.otel.metrics.client import MetricsClient
from pycodex.otel.metrics.names import GOAL_BLOCKED_METRIC
from pycodex.otel.metrics.names import GOAL_CREATED_METRIC
from pycodex.otel.metrics.names import GOAL_DURATION_SECONDS_METRIC
from pycodex.otel.metrics.names import GOAL_RESUMED_METRIC
from pycodex.otel.metrics.names import GOAL_TOKEN_COUNT_METRIC
from pycodex.state import ThreadGoalStatus


def test_metrics_rs_records_created_resumed_and_terminal_transition() -> None:
    from pycodex.ext.goal.metrics import GoalMetrics

    client = MetricsClient()
    metrics = GoalMetrics(client)
    goal = SimpleNamespace(
        status=ThreadGoalStatus.BLOCKED,
        tokens_used=42,
        time_used_seconds=9,
    )

    metrics.record_created()
    metrics.record_resumed_if_status_changed(
        ThreadGoalStatus.PAUSED,
        ThreadGoalStatus.ACTIVE,
    )
    metrics.record_terminal_if_status_changed(ThreadGoalStatus.ACTIVE, goal)

    assert [record.name for record in client.counter_records] == [
        GOAL_CREATED_METRIC,
        GOAL_RESUMED_METRIC,
        GOAL_BLOCKED_METRIC,
    ]
    assert client.histogram_records[0].name == GOAL_TOKEN_COUNT_METRIC
    assert client.histogram_records[0].value == 42
    assert client.histogram_records[0].tags == [("status", "blocked")]
    assert client.histogram_records[1].name == GOAL_DURATION_SECONDS_METRIC
    assert client.histogram_records[1].value == 9


def test_metrics_rs_ignores_same_status_and_absent_client() -> None:
    from pycodex.ext.goal.metrics import GoalMetrics

    client = MetricsClient()
    metrics = GoalMetrics(client)
    goal = SimpleNamespace(
        status=ThreadGoalStatus.BLOCKED,
        tokens_used=42,
        time_used_seconds=9,
    )

    metrics.record_terminal_if_status_changed(ThreadGoalStatus.BLOCKED, goal)
    GoalMetrics().record_created()
    GoalMetrics().record_resumed()
    GoalMetrics().record_terminal_if_status_changed(None, goal)

    assert client.counter_records == []
    assert client.histogram_records == []
