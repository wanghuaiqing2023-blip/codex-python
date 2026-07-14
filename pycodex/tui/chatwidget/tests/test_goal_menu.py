from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/goal_menu.rs
# Behavior contract: bare /goal summary lines, status labels, command hints,
# and edit-status normalization for completed/budget-limited goals.

import pytest

from pycodex.tui.chatwidget.goal_menu import (
    edited_goal_status,
    goal_edit_prompt,
    goal_status_label,
    goal_summary_lines,
)
from pycodex.tui.goal_display import ThreadGoal, ThreadGoalStatus


def goal(status: ThreadGoalStatus, *, budget=None, used=12_500, seconds=120, objective="ship it"):
    return ThreadGoal(
        thread_id="thread",
        objective=objective,
        status=status,
        token_budget=budget,
        tokens_used=used,
        time_used_seconds=seconds,
        created_at=1,
        updated_at=1,
    )


@pytest.mark.parametrize(
    ("status", "label"),
    [
        (ThreadGoalStatus.ACTIVE, "active"),
        (ThreadGoalStatus.PAUSED, "paused"),
        (ThreadGoalStatus.BLOCKED, "blocked"),
        (ThreadGoalStatus.USAGE_LIMITED, "usage limited"),
        (ThreadGoalStatus.BUDGET_LIMITED, "limited by budget"),
        (ThreadGoalStatus.COMPLETE, "complete"),
    ],
)
def test_goal_status_label_matches_rust_variants(status, label):
    assert goal_status_label(status) == label


def test_goal_summary_lines_for_active_goal_include_budget_and_pause_hint():
    assert goal_summary_lines(goal(ThreadGoalStatus.ACTIVE, budget=50_000)) == [
        "Goal",
        "Status: active",
        "Objective: ship it",
        "Time used: 2m",
        "Tokens used: 12.5K",
        "Token budget: 50K",
        "",
        "Commands: /goal edit, /goal pause, /goal clear",
    ]


@pytest.mark.parametrize(
    "status",
    [ThreadGoalStatus.PAUSED, ThreadGoalStatus.BLOCKED, ThreadGoalStatus.USAGE_LIMITED],
)
def test_goal_summary_lines_for_resumeable_statuses_use_resume_hint(status):
    lines = goal_summary_lines(goal(status, budget=None, objective="resume me"))

    assert "Token budget:" not in "\n".join(lines)
    assert lines[1] == f"Status: {goal_status_label(status)}"
    assert lines[-1] == "Commands: /goal edit, /goal resume, /goal clear"


@pytest.mark.parametrize("status", [ThreadGoalStatus.BUDGET_LIMITED, ThreadGoalStatus.COMPLETE])
def test_goal_summary_lines_for_terminal_statuses_hide_resume_and_pause(status):
    assert goal_summary_lines(goal(status))[-1] == "Commands: /goal edit, /goal clear"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (ThreadGoalStatus.ACTIVE, ThreadGoalStatus.ACTIVE),
        (ThreadGoalStatus.PAUSED, ThreadGoalStatus.PAUSED),
        (ThreadGoalStatus.BLOCKED, ThreadGoalStatus.BLOCKED),
        (ThreadGoalStatus.USAGE_LIMITED, ThreadGoalStatus.USAGE_LIMITED),
        (ThreadGoalStatus.BUDGET_LIMITED, ThreadGoalStatus.ACTIVE),
        (ThreadGoalStatus.COMPLETE, ThreadGoalStatus.ACTIVE),
    ],
)
def test_edited_goal_status_matches_rust_transition(status, expected):
    assert edited_goal_status(status) is expected


def test_goal_edit_prompt_prefills_objective_and_submits_edited_text():
    # Rust: chatwidget/tests/goal_menu.rs::goal_edit_prompt_submits_preserved_status_and_budget.
    submitted = []
    view = goal_edit_prompt(
        goal(ThreadGoalStatus.PAUSED, budget=80_000, objective="Keep improving"),
        submitted.append,
    )

    assert view.title == "Edit goal"
    assert view.textarea.text() == "Keep improving"
    view.handle_paste(" with clearer wording")
    view.handle_key_event("enter")

    assert submitted == ["Keep improving with clearer wording"]
    assert view.is_complete()


def test_goal_summary_accepts_protocol_like_dict_status_names():
    lines = goal_summary_lines(
        {
            "status": "budgetLimited",
            "objective": "dict goal",
            "time_used_seconds": 36_720,
            "tokens_used": 63_876,
            "token_budget": 50_000,
        }
    )

    assert lines[1] == "Status: limited by budget"
    assert lines[3] == "Time used: 10h 12m"
    assert lines[4] == "Tokens used: 63.9K"
    assert lines[5] == "Token budget: 50K"

