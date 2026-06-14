from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/goal_status.rs
# Behavior contract: map app-server ThreadGoal state into footer
# GoalStatusIndicator values and format compact goal usage strings.

from pycodex.tui.bottom_pane.footer import GoalStatusIndicator
from pycodex.tui.chatwidget.goal_status import (
    GoalStatusState,
    active_goal_state,
    active_goal_usage,
    completed_goal_usage,
    goal_status_indicator_from_app_goal,
    stopped_goal_budget_usage,
)
from pycodex.tui.goal_display import ThreadGoal, ThreadGoalStatus


def goal(status: ThreadGoalStatus, *, budget=None, used=0, seconds=0):
    return ThreadGoal(
        thread_id="thread",
        objective="do the thing",
        status=status,
        token_budget=budget,
        tokens_used=used,
        time_used_seconds=seconds,
        created_at=1,
        updated_at=1,
    )


def test_active_goal_usage_prefers_token_budget():
    assert active_goal_usage(50_000, 12_500, 90) == "12.5K / 50K"


def test_active_goal_usage_reports_time_without_budget():
    assert active_goal_usage(None, 12_500, 120) == "2m"


def test_stopped_goal_budget_usage_reports_budgeted_tokens():
    assert stopped_goal_budget_usage(50_000, 63_876) == "63.9K / 50K tokens"


def test_stopped_goal_budget_usage_omits_unbudgeted_usage():
    assert stopped_goal_budget_usage(None, 12_500) is None


def test_completed_goal_usage_reports_tokens_when_budgeted():
    assert completed_goal_usage(50_000, 40_000, 120) == "40K tokens"


def test_completed_goal_usage_reports_time_without_token_budget():
    assert completed_goal_usage(None, 40_000, 36_720) == "10h 12m"


def test_goal_status_indicator_from_app_goal_maps_status_variants():
    assert goal_status_indicator_from_app_goal(goal(ThreadGoalStatus.Active, seconds=60)) == GoalStatusIndicator.Active("1m")
    assert goal_status_indicator_from_app_goal(goal(ThreadGoalStatus.Paused)) == GoalStatusIndicator("Paused")
    assert goal_status_indicator_from_app_goal(goal(ThreadGoalStatus.Blocked)) == GoalStatusIndicator("Blocked")
    assert goal_status_indicator_from_app_goal(goal(ThreadGoalStatus.UsageLimited)) == GoalStatusIndicator("UsageLimited")
    assert goal_status_indicator_from_app_goal(goal(ThreadGoalStatus.BudgetLimited, budget=50_000, used=63_876)) == GoalStatusIndicator.BudgetLimited("63.9K / 50K tokens")
    assert goal_status_indicator_from_app_goal(goal(ThreadGoalStatus.Complete, used=40_000, seconds=120)) == GoalStatusIndicator.Complete("2m")


def test_active_goal_status_includes_current_turn_elapsed_time():
    observed_at = 1_000.0
    state = active_goal_state(observed_at, 60)

    assert state.indicator(observed_at + 60, observed_at - 120) == GoalStatusIndicator.Active("2m")


def test_active_goal_status_does_not_count_idle_time_before_turn_start():
    observed_at = 1_000.0
    active_turn_started_at = observed_at + 120
    state = active_goal_state(observed_at, 60)

    assert state.indicator(active_turn_started_at + 60, active_turn_started_at) == GoalStatusIndicator.Active("2m")


def test_state_is_active_and_duck_typed_protocol_goal_statuses():
    state = GoalStatusState.new(goal(ThreadGoalStatus.Active), 0)
    assert state.is_active() is True

    duck_goal = {
        "status": "budgetLimited",
        "token_budget": 50_000,
        "tokens_used": 1_250,
        "time_used_seconds": 0,
    }
    assert goal_status_indicator_from_app_goal(duck_goal) == GoalStatusIndicator.BudgetLimited("1.25K / 50K tokens")
