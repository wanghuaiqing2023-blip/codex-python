"""Goal status indicator helpers for ``codex-tui::chatwidget::goal_status``.

The Rust module maps app-server thread goal state into the compact footer goal
indicator.  Python keeps that module boundary as lightweight semantic values and
accepts either the local ``ThreadGoal`` dataclass or duck-typed protocol objects.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .._porting import RustTuiModule
from ..bottom_pane.footer import GoalStatusIndicator
from ..goal_display import ThreadGoal, ThreadGoalStatus, format_goal_elapsed_seconds
from ..status.helpers import format_tokens_compact

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::goal_status",
    source="codex/codex-rs/tui/src/chatwidget/goal_status.rs",
)


@dataclass(frozen=True)
class GoalStatusState:
    goal: Any
    observed_at: Any

    @classmethod
    def new(cls, goal: Any, observed_at: Any) -> "GoalStatusState":
        return cls(goal=goal, observed_at=observed_at)

    def is_active(self) -> bool:
        return _normalize_status(_get(self.goal, "status")) is ThreadGoalStatus.Active

    def indicator(self, now: Any, active_turn_started_at: Any | None = None) -> GoalStatusIndicator | None:
        goal = _copy_goal(self.goal)
        if _normalize_status(_get(goal, "status")) is ThreadGoalStatus.Active and active_turn_started_at is not None:
            baseline = _max_instant(self.observed_at, active_turn_started_at)
            active_seconds = int(max(_duration_seconds(now, baseline), 0))
            current = int(_get(goal, "time_used_seconds", 0))
            _set(goal, "time_used_seconds", _saturating_add_i64(current, active_seconds))
        return goal_status_indicator_from_app_goal(goal)


def goal_status_indicator_from_app_goal(goal: Any) -> GoalStatusIndicator | None:
    status = _normalize_status(_get(goal, "status"))
    token_budget = _get(goal, "token_budget", None)
    tokens_used = int(_get(goal, "tokens_used", 0))
    time_used_seconds = int(_get(goal, "time_used_seconds", 0))

    if status is ThreadGoalStatus.Active:
        return GoalStatusIndicator.Active(active_goal_usage(token_budget, tokens_used, time_used_seconds))
    if status is ThreadGoalStatus.Paused:
        return GoalStatusIndicator("Paused")
    if status is ThreadGoalStatus.Blocked:
        return GoalStatusIndicator("Blocked")
    if status is ThreadGoalStatus.UsageLimited:
        return GoalStatusIndicator("UsageLimited")
    if status is ThreadGoalStatus.BudgetLimited:
        return GoalStatusIndicator.BudgetLimited(stopped_goal_budget_usage(token_budget, tokens_used))
    if status is ThreadGoalStatus.Complete:
        return GoalStatusIndicator.Complete(completed_goal_usage(token_budget, tokens_used, time_used_seconds))
    return None


def active_goal_usage(token_budget: int | None, tokens_used: int, time_used_seconds: int) -> str | None:
    if token_budget is not None:
        return f"{format_tokens_compact(tokens_used)} / {format_tokens_compact(token_budget)}"
    return format_goal_elapsed_seconds(time_used_seconds)


def stopped_goal_budget_usage(token_budget: int | None, tokens_used: int) -> str | None:
    if token_budget is None:
        return None
    return f"{format_tokens_compact(tokens_used)} / {format_tokens_compact(token_budget)} tokens"


def completed_goal_usage(token_budget: int | None, tokens_used: int, time_used_seconds: int) -> str:
    if token_budget is not None:
        return f"{format_tokens_compact(tokens_used)} tokens"
    return format_goal_elapsed_seconds(time_used_seconds)


def active_goal_state(observed_at: Any, time_used_seconds: int) -> GoalStatusState:
    return GoalStatusState.new(
        ThreadGoal(
            thread_id="thread",
            objective="do the thing",
            status=ThreadGoalStatus.Active,
            token_budget=None,
            tokens_used=0,
            time_used_seconds=time_used_seconds,
            created_at=1,
            updated_at=1,
        ),
        observed_at,
    )


def _normalize_status(status: Any) -> ThreadGoalStatus:
    if isinstance(status, ThreadGoalStatus):
        return status
    text = str(getattr(status, "value", status))
    aliases = {
        "active": ThreadGoalStatus.Active,
        "Active": ThreadGoalStatus.Active,
        "paused": ThreadGoalStatus.Paused,
        "Paused": ThreadGoalStatus.Paused,
        "blocked": ThreadGoalStatus.Blocked,
        "Blocked": ThreadGoalStatus.Blocked,
        "usage_limited": ThreadGoalStatus.UsageLimited,
        "usageLimited": ThreadGoalStatus.UsageLimited,
        "UsageLimited": ThreadGoalStatus.UsageLimited,
        "budget_limited": ThreadGoalStatus.BudgetLimited,
        "budgetLimited": ThreadGoalStatus.BudgetLimited,
        "BudgetLimited": ThreadGoalStatus.BudgetLimited,
        "complete": ThreadGoalStatus.Complete,
        "Complete": ThreadGoalStatus.Complete,
    }
    try:
        return aliases[text]
    except KeyError as exc:
        raise ValueError(f"unknown ThreadGoalStatus: {status!r}") from exc


def _copy_goal(goal: Any) -> Any:
    if isinstance(goal, ThreadGoal):
        return replace(goal)
    if hasattr(goal, "__dataclass_fields__"):
        try:
            return replace(goal)
        except TypeError:
            pass
    if isinstance(goal, dict):
        return dict(goal)
    return _GoalProxy(goal)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _set(obj: Any, name: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[name] = value
    else:
        setattr(obj, name, value)


class _GoalProxy:
    def __init__(self, goal: Any) -> None:
        self.thread_id = _get(goal, "thread_id", "")
        self.objective = _get(goal, "objective", "")
        self.status = _get(goal, "status")
        self.token_budget = _get(goal, "token_budget", None)
        self.tokens_used = _get(goal, "tokens_used", 0)
        self.time_used_seconds = _get(goal, "time_used_seconds", 0)
        self.created_at = _get(goal, "created_at", 0)
        self.updated_at = _get(goal, "updated_at", 0)


def _max_instant(left: Any, right: Any) -> Any:
    return left if _duration_seconds(left, right) >= 0 else right


def _duration_seconds(now: Any, baseline: Any) -> float:
    if isinstance(now, datetime) and isinstance(baseline, datetime):
        return (now - baseline).total_seconds()
    if hasattr(now, "total_seconds") and not isinstance(now, (int, float)):
        return float(now.total_seconds()) - float(baseline.total_seconds())
    return float(now) - float(baseline)


def _saturating_add_i64(left: int, right: int) -> int:
    max_i64 = 2**63 - 1
    result = int(left) + int(right)
    return min(result, max_i64)


__all__ = [
    "GoalStatusState",
    "RUST_MODULE",
    "active_goal_state",
    "active_goal_usage",
    "completed_goal_usage",
    "goal_status_indicator_from_app_goal",
    "stopped_goal_budget_usage",
]
