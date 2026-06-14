from __future__ import annotations

from pycodex.tui.app.thread_goal_actions import (
    EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE,
    ThreadGoal,
    ThreadGoalStatus,
    is_ephemeral_thread_goal_error,
    should_confirm_before_replacing_goal,
    thread_goal_error_message,
)


def test_thread_goal_error_message_explains_temporary_session() -> None:
    err = RuntimeError("thread/goal/get failed: ephemeral thread does not support goals: thread-1")

    assert thread_goal_error_message("read", err) == EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE
    assert is_ephemeral_thread_goal_error(err)


def test_thread_goal_error_message_preserves_generic_failure_context() -> None:
    err = RuntimeError("thread/goal/get failed in TUI")

    assert thread_goal_error_message("read", err) == "Failed to read thread goal: thread/goal/get failed in TUI"


def test_completed_goal_does_not_require_replace_confirmation() -> None:
    assert not should_confirm_before_replacing_goal(ThreadGoal(status=ThreadGoalStatus.Complete))


def test_unfinished_goals_require_replace_confirmation() -> None:
    for status in [
        ThreadGoalStatus.Active,
        ThreadGoalStatus.Paused,
        ThreadGoalStatus.Blocked,
        ThreadGoalStatus.UsageLimited,
        ThreadGoalStatus.BudgetLimited,
    ]:
        assert should_confirm_before_replacing_goal(ThreadGoal(status=status))
