"""Parity tests for Rust ``codex-tui::goal_display``.

Rust source: ``codex/codex-rs/tui/src/goal_display.rs``.
"""

from pycodex.tui.goal_display import (
    ThreadGoal,
    ThreadGoalStatus,
    format_goal_elapsed_seconds,
    format_tokens_compact,
    goal_status_label,
    goal_usage_summary,
)


def test_format_goal_elapsed_seconds_is_compact() -> None:
    assert format_goal_elapsed_seconds(0) == "0s"
    assert format_goal_elapsed_seconds(59) == "59s"
    assert format_goal_elapsed_seconds(60) == "1m"
    assert format_goal_elapsed_seconds(30 * 60) == "30m"
    assert format_goal_elapsed_seconds(90 * 60) == "1h 30m"
    assert format_goal_elapsed_seconds(2 * 60 * 60) == "2h"
    assert format_goal_elapsed_seconds(24 * 60 * 60 - 1) == "23h 59m"
    assert format_goal_elapsed_seconds(24 * 60 * 60) == "1d 0h 0m"
    assert format_goal_elapsed_seconds(2 * 24 * 60 * 60 + 23 * 60 * 60 + 42 * 60) == "2d 23h 42m"
    assert format_goal_elapsed_seconds(-5) == "0s"


def test_goal_status_label_matches_rust_variants() -> None:
    assert goal_status_label(ThreadGoalStatus.Active) == "active"
    assert goal_status_label(ThreadGoalStatus.Paused) == "paused"
    assert goal_status_label(ThreadGoalStatus.Blocked) == "blocked"
    assert goal_status_label(ThreadGoalStatus.UsageLimited) == "usage limited"
    assert goal_status_label(ThreadGoalStatus.BudgetLimited) == "limited by budget"
    assert goal_status_label(ThreadGoalStatus.Complete) == "complete"


def test_goal_usage_summary_formats_time_and_budgeted_tokens() -> None:
    goal = ThreadGoal(
        thread_id="thread-1",
        objective="Complete the task described in ../gameboy-long-running-prompt5.txt",
        status=ThreadGoalStatus.BudgetLimited,
        token_budget=50_000,
        tokens_used=63_876,
        time_used_seconds=120,
        created_at=0,
        updated_at=0,
    )
    assert goal_usage_summary(goal) == (
        "Objective: Complete the task described in ../gameboy-long-running-prompt5.txt "
        "Time: 2m. Tokens: 63.9K/50K."
    )


def test_goal_usage_summary_omits_absent_time_or_budget() -> None:
    goal = ThreadGoal(
        thread_id="thread-1",
        objective="Do the thing",
        status=ThreadGoalStatus.Active,
        token_budget=None,
        tokens_used=100,
        time_used_seconds=0,
    )
    assert goal_usage_summary(goal) == "Objective: Do the thing"


def test_format_tokens_compact_representative_values() -> None:
    assert format_tokens_compact(999) == "999"
    assert format_tokens_compact(50_000) == "50K"
    assert format_tokens_compact(63_876) == "63.9K"
    assert format_tokens_compact(1_250_000) == "1.2M"
