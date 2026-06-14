"""Thread goal action helpers for Rust ``codex-tui::app::thread_goal_actions``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_goal_actions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_goal_actions",
    source="codex/codex-rs/tui/src/app/thread_goal_actions.rs",
)

EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE = (
    "Goals need a saved session. This session is temporary.\n"
    "Run `codex` to start a saved session, or `codex resume` / `/resume` to reopen one."
)


class ThreadGoalStatus(str, Enum):
    Active = "active"
    Paused = "paused"
    Blocked = "blocked"
    UsageLimited = "usage_limited"
    BudgetLimited = "budget_limited"
    Complete = "complete"


@dataclass(frozen=True)
class ThreadGoal:
    status: ThreadGoalStatus | str
    thread_id: str = "thread-1"
    objective: str = "Finish the thing."
    token_budget: int | None = None
    tokens_used: int = 0
    time_used_seconds: int = 0
    created_at: int = 1_776_272_400
    updated_at: int = 1_776_272_460


def _status_value(status: Any) -> str:
    if isinstance(status, ThreadGoalStatus):
        return status.value
    if hasattr(status, "name"):
        name = str(status.name)
        rust_name_map = {
            "Active": ThreadGoalStatus.Active.value,
            "Paused": ThreadGoalStatus.Paused.value,
            "Blocked": ThreadGoalStatus.Blocked.value,
            "UsageLimited": ThreadGoalStatus.UsageLimited.value,
            "BudgetLimited": ThreadGoalStatus.BudgetLimited.value,
            "Complete": ThreadGoalStatus.Complete.value,
        }
        if name in rust_name_map:
            return rust_name_map[name]
    return str(status)


def _error_chain_messages(error: Any) -> list[str]:
    messages: list[str] = []
    current = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        messages.append(str(current))
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    if not messages:
        messages.append(str(error))
    return messages


def is_ephemeral_thread_goal_error(error: Any) -> bool:
    for message in _error_chain_messages(error):
        if (
            "ephemeral thread does not support goals" in message
            or "thread goals require a persisted thread; this thread is ephemeral" in message
        ):
            return True
    return False


def thread_goal_error_message(action: str, error: Any) -> str:
    if is_ephemeral_thread_goal_error(error):
        return EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE
    return f"Failed to {action} thread goal: {error}"


def should_confirm_before_replacing_goal(goal: ThreadGoal | Any) -> bool:
    status = _status_value(getattr(goal, "status", goal))
    if status == ThreadGoalStatus.Complete.value:
        return False
    return status in {
        ThreadGoalStatus.Active.value,
        ThreadGoalStatus.Paused.value,
        ThreadGoalStatus.Blocked.value,
        ThreadGoalStatus.UsageLimited.value,
        ThreadGoalStatus.BudgetLimited.value,
    }


def test_goal(status: ThreadGoalStatus | str) -> ThreadGoal:
    return ThreadGoal(status=status)


async def open_thread_goal_menu(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_goal_actions.open_thread_goal_menu app-server/UI path is not ported")


async def maybe_prompt_resume_paused_goal_after_resume(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_goal_actions.maybe_prompt_resume_paused_goal_after_resume app-server/UI path is not ported")


async def open_thread_goal_editor(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_goal_actions.open_thread_goal_editor app-server/UI path is not ported")


async def set_thread_goal_objective(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_goal_actions.set_thread_goal_objective app-server/UI path is not ported")


async def set_thread_goal_status(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_goal_actions.set_thread_goal_status app-server/UI path is not ported")


async def clear_thread_goal(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_goal_actions.clear_thread_goal app-server/UI path is not ported")


__all__ = [
    "EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE",
    "RUST_MODULE",
    "ThreadGoal",
    "ThreadGoalStatus",
    "clear_thread_goal",
    "is_ephemeral_thread_goal_error",
    "maybe_prompt_resume_paused_goal_after_resume",
    "open_thread_goal_editor",
    "open_thread_goal_menu",
    "set_thread_goal_objective",
    "set_thread_goal_status",
    "should_confirm_before_replacing_goal",
    "test_goal",
    "thread_goal_error_message",
]
