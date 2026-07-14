from __future__ import annotations

from pycodex.tui.app.thread_goal_actions import (
    EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE,
    ThreadGoal,
    ThreadGoalSetMode,
    ThreadGoalStatus,
    clear_thread_goal_plan,
    is_ephemeral_thread_goal_error,
    maybe_prompt_resume_paused_goal_after_resume_plan,
    open_thread_goal_editor_plan,
    open_thread_goal_menu_plan,
    set_thread_goal_objective_plan,
    set_thread_goal_status_plan,
    should_confirm_before_replacing_goal,
    thread_goal_error_message,
)


def goal(
    status: ThreadGoalStatus,
    *,
    objective: str = "Finish the thing.",
    token_budget: int | None = None,
    tokens_used: int = 0,
) -> ThreadGoal:
    return ThreadGoal(
        thread_id="thread-1",
        objective=objective,
        status=status,
        token_budget=token_budget,
        tokens_used=tokens_used,
        time_used_seconds=0,
        created_at=1_776_272_400,
        updated_at=1_776_272_460,
    )


def test_thread_goal_error_message_explains_temporary_session() -> None:
    err = RuntimeError("thread/goal/get failed: ephemeral thread does not support goals: thread-1")

    assert thread_goal_error_message("read", err) == EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE
    assert is_ephemeral_thread_goal_error(err)


def test_thread_goal_error_message_detects_persisted_thread_ephemeral_phrase() -> None:
    # Rust matches both historical app-server phrasings in the error chain.
    err = RuntimeError(
        "thread goals require a persisted thread; this thread is ephemeral"
    )

    assert thread_goal_error_message("set", err) == EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE
    assert is_ephemeral_thread_goal_error(err)


def test_thread_goal_error_message_preserves_generic_failure_context() -> None:
    err = RuntimeError("thread/goal/get failed in TUI")

    assert thread_goal_error_message("read", err) == "Failed to read thread goal: thread/goal/get failed in TUI"


def test_completed_goal_does_not_require_replace_confirmation() -> None:
    assert not should_confirm_before_replacing_goal(goal(ThreadGoalStatus.COMPLETE))


def test_unfinished_goals_require_replace_confirmation() -> None:
    for status in [
        ThreadGoalStatus.ACTIVE,
        ThreadGoalStatus.PAUSED,
        ThreadGoalStatus.BLOCKED,
        ThreadGoalStatus.USAGE_LIMITED,
        ThreadGoalStatus.BUDGET_LIMITED,
    ]:
        assert should_confirm_before_replacing_goal(goal(status))


def test_menu_editor_resume_and_clear_plans_match_rust_branches() -> None:
    current_goal = goal(ThreadGoalStatus.PAUSED, objective="Resume me")

    assert open_thread_goal_menu_plan(None).actions == ("add_info_message",)
    assert open_thread_goal_menu_plan(current_goal).actions == ("show_goal_summary",)
    assert open_thread_goal_editor_plan(None).actions == ("add_error_message", "add_info_message")
    assert open_thread_goal_editor_plan("thread", current_goal).actions == ("show_goal_edit_prompt",)

    resume = maybe_prompt_resume_paused_goal_after_resume_plan("thread", current_goal)
    assert resume.actions == ("show_resume_paused_goal_prompt",)
    assert resume.objective == "Resume me"

    assert clear_thread_goal_plan("thread", True).message == "Goal cleared"
    no_goal = clear_thread_goal_plan("thread", False)
    assert no_goal.message == "No goal to clear"
    assert no_goal.hint == "This thread does not currently have a goal."


def test_set_thread_goal_objective_replace_confirmation_and_success_plans() -> None:
    active = goal(ThreadGoalStatus.ACTIVE)
    completed = goal(ThreadGoalStatus.COMPLETE)

    confirm = set_thread_goal_objective_plan(
        "thread", "New objective", ThreadGoalSetMode.confirm_if_exists(), active
    )
    assert confirm.actions == ("show_selection_view",)
    assert confirm.selection_view is not None
    assert confirm.selection_view.title == "Replace goal?"
    assert confirm.selection_view.items[0].name == "Replace current goal"

    replace_without_confirm = set_thread_goal_objective_plan(
        "thread",
        "New objective",
        ThreadGoalSetMode.confirm_if_exists(),
        completed,
    )
    assert replace_without_confirm.actions == ("thread_goal_clear", "thread_goal_set", "add_info_message")
    assert replace_without_confirm.status == ThreadGoalStatus.ACTIVE


def test_set_thread_goal_status_and_error_plans() -> None:
    updated = set_thread_goal_status_plan(
        "thread",
        ThreadGoalStatus.BLOCKED,
        response_goal=goal(ThreadGoalStatus.BLOCKED, tokens_used=5),
    )
    assert updated.actions == ("thread_goal_set", "add_info_message")
    assert updated.message == "Goal blocked"
    assert updated.hint == "Objective: Finish the thing."

    err = RuntimeError("server disappeared")
    failed = set_thread_goal_objective_plan(
        "thread", "x", ThreadGoalSetMode.replace_existing(), set_error=err
    )
    assert failed.actions == ("add_error_message",)
    assert failed.message == "Failed to replace thread goal: server disappeared"
