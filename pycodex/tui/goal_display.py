"""Goal display formatting for ``codex-tui::goal_display``.

Rust source: ``codex/codex-rs/tui/src/goal_display.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="goal_display",
    source="codex/codex-rs/tui/src/goal_display.rs",
)


class ThreadGoalStatus(Enum):
    Active = "active"
    Paused = "paused"
    Blocked = "blocked"
    UsageLimited = "usage_limited"
    BudgetLimited = "budget_limited"
    Complete = "complete"


@dataclass(eq=True)
class ThreadGoal:
    thread_id: str
    objective: str
    status: ThreadGoalStatus
    token_budget: int | None
    tokens_used: int
    time_used_seconds: int
    created_at: int = 0
    updated_at: int = 0


def format_goal_elapsed_seconds(seconds: int) -> str:
    seconds = max(int(seconds), 0)
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours >= 24:
        days = hours // 24
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours}h {remaining_minutes}m"

    if remaining_minutes == 0:
        return f"{hours}h"
    return f"{hours}h {remaining_minutes}m"


def goal_status_label(status: ThreadGoalStatus | str) -> str:
    normalized = _normalize_status(status)
    return {
        ThreadGoalStatus.Active: "active",
        ThreadGoalStatus.Paused: "paused",
        ThreadGoalStatus.Blocked: "blocked",
        ThreadGoalStatus.UsageLimited: "usage limited",
        ThreadGoalStatus.BudgetLimited: "limited by budget",
        ThreadGoalStatus.Complete: "complete",
    }[normalized]


def goal_usage_summary(goal: ThreadGoal | Any) -> str:
    objective = getattr(goal, "objective")
    time_used_seconds = int(getattr(goal, "time_used_seconds", 0))
    token_budget = getattr(goal, "token_budget", None)
    tokens_used = int(getattr(goal, "tokens_used", 0))

    parts = [f"Objective: {objective}"]
    if time_used_seconds > 0:
        parts.append(f"Time: {format_goal_elapsed_seconds(time_used_seconds)}.")
    if token_budget is not None:
        parts.append(f"Tokens: {format_tokens_compact(tokens_used)}/{format_tokens_compact(int(token_budget))}.")
    return " ".join(parts)


def format_tokens_compact(tokens: int) -> str:
    value = int(tokens)
    sign = "-" if value < 0 else ""
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        compact = abs_value / 1_000_000
        return sign + _format_compact_number(compact) + "M"
    if abs_value >= 1_000:
        compact = abs_value / 1_000
        return sign + _format_compact_number(compact) + "K"
    return sign + str(abs_value)


def _format_compact_number(value: float) -> str:
    rounded = round(value, 1)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def _normalize_status(status: ThreadGoalStatus | str) -> ThreadGoalStatus:
    if isinstance(status, ThreadGoalStatus):
        return status
    text = str(status)
    for item in ThreadGoalStatus:
        if text == item.value or text == item.name:
            return item
    raise ValueError(f"unknown ThreadGoalStatus: {status!r}")


__all__ = [
    "RUST_MODULE",
    "ThreadGoal",
    "ThreadGoalStatus",
    "format_goal_elapsed_seconds",
    "format_tokens_compact",
    "goal_status_label",
    "goal_usage_summary",
]
