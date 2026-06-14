"""Goal menu summary helpers for ``codex-tui::chatwidget::goal_menu``.

The Rust module builds the visible summary for the bare ``/goal`` command and
contains small status mapping helpers.  Python represents ratatui ``Line``
values as plain semantic strings because the styling is already a renderer
boundary for this port.
"""

from __future__ import annotations

from typing import Any

from .._porting import RustTuiModule
from ..goal_display import ThreadGoalStatus, format_goal_elapsed_seconds
from ..status.helpers import format_tokens_compact

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::goal_menu",
    source="codex/codex-rs/tui/src/chatwidget/goal_menu.rs",
)


def goal_summary_lines(goal: Any) -> list[str]:
    status = _normalize_status(_get(goal, "status"))
    lines = [
        "Goal",
        f"Status: {goal_status_label(status)}",
        f"Objective: {_get(goal, 'objective', '')}",
        f"Time used: {format_goal_elapsed_seconds(int(_get(goal, 'time_used_seconds', 0)))}",
        f"Tokens used: {format_tokens_compact(int(_get(goal, 'tokens_used', 0)))}",
    ]
    token_budget = _get(goal, "token_budget", None)
    if token_budget is not None:
        lines.append(f"Token budget: {format_tokens_compact(int(token_budget))}")
    lines.append("")
    lines.append(_command_hint(status))
    return lines


def goal_status_label(status: ThreadGoalStatus | str | Any) -> str:
    normalized = _normalize_status(status)
    return {
        ThreadGoalStatus.Active: "active",
        ThreadGoalStatus.Paused: "paused",
        ThreadGoalStatus.Blocked: "blocked",
        ThreadGoalStatus.UsageLimited: "usage limited",
        ThreadGoalStatus.BudgetLimited: "limited by budget",
        ThreadGoalStatus.Complete: "complete",
    }[normalized]


def edited_goal_status(status: ThreadGoalStatus | str | Any) -> ThreadGoalStatus:
    normalized = _normalize_status(status)
    if normalized in {ThreadGoalStatus.BudgetLimited, ThreadGoalStatus.Complete}:
        return ThreadGoalStatus.Active
    return normalized


def _command_hint(status: ThreadGoalStatus) -> str:
    if status is ThreadGoalStatus.Active:
        return "Commands: /goal edit, /goal pause, /goal clear"
    if status in {ThreadGoalStatus.Paused, ThreadGoalStatus.Blocked, ThreadGoalStatus.UsageLimited}:
        return "Commands: /goal edit, /goal resume, /goal clear"
    return "Commands: /goal edit, /goal clear"


def _normalize_status(status: ThreadGoalStatus | str | Any) -> ThreadGoalStatus:
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


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


__all__ = [
    "RUST_MODULE",
    "edited_goal_status",
    "goal_status_label",
    "goal_summary_lines",
]
