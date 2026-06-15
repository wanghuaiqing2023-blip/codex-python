"""Thread goal action helpers for Rust ``codex-tui::app::thread_goal_actions``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_goal_actions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_goal_actions",
    source="codex/codex-rs/tui/src/app/thread_goal_actions.rs",
    status="complete",
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
    status: Any
    thread_id: str = "thread-1"
    objective: str = "Finish the thing."
    token_budget: Optional[int] = None
    tokens_used: int = 0
    time_used_seconds: int = 0
    created_at: int = 1_776_272_400
    updated_at: int = 1_776_272_460


class ThreadGoalSetMode(str, Enum):
    ConfirmIfExists = "confirm_if_exists"
    ReplaceExisting = "replace_existing"
    UpdateExisting = "update_existing"


@dataclass(frozen=True)
class UpdateExistingMode:
    status: Any
    token_budget: int


@dataclass(frozen=True)
class SelectionItemPlan:
    name: str
    description: Optional[str] = None
    dismiss_on_select: bool = True
    event: Any = None


@dataclass(frozen=True)
class SelectionViewPlan:
    title: Optional[str]
    subtitle: Optional[str]
    footer_hint: Optional[str]
    items: Tuple[SelectionItemPlan, ...]


@dataclass(frozen=True)
class ThreadGoalActionPlan:
    actions: Tuple[str, ...]
    message: Optional[str] = None
    hint: Optional[str] = None
    thread_id: Any = None
    objective: Optional[str] = None
    status: Any = None
    token_budget: Optional[int] = None
    selection_view: Optional[SelectionViewPlan] = None
    server_calls: Tuple[Tuple[str, Any], ...] = field(default_factory=tuple)


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


def _error_chain_messages(error: Any) -> List[str]:
    messages = []
    current = error
    seen = set()
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


def should_confirm_before_replacing_goal(goal: Any) -> bool:
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


def test_goal(status: Any) -> ThreadGoal:
    return ThreadGoal(status=status)


def goal_status_label(status: Any) -> str:
    value = _status_value(status)
    return value.replace("_", " ")


def goal_usage_summary(goal: ThreadGoal) -> str:
    if goal.token_budget is None:
        return "%s tokens used" % goal.tokens_used
    return "%s/%s tokens used" % (goal.tokens_used, goal.token_budget)


def show_no_thread_goal_to_edit_plan() -> ThreadGoalActionPlan:
    return ThreadGoalActionPlan(
        actions=("add_error_message", "add_info_message"),
        message="No goal is currently set.",
        hint="Create a goal before editing it.",
    )


def show_replace_thread_goal_confirmation_plan(thread_id: Any, objective: str) -> ThreadGoalActionPlan:
    selection = SelectionViewPlan(
        title="Replace goal?",
        subtitle="New objective: %s" % objective,
        footer_hint="Press Enter to select",
        items=(
            SelectionItemPlan(
                name="Replace current goal",
                description="Set the new objective and start it now",
                event={
                    "type": "SetThreadGoalObjective",
                    "thread_id": thread_id,
                    "objective": objective,
                    "mode": ThreadGoalSetMode.ReplaceExisting.value,
                },
            ),
            SelectionItemPlan(
                name="Cancel",
                description="Keep the current goal",
                event=None,
            ),
        ),
    )
    return ThreadGoalActionPlan(
        actions=("show_selection_view",),
        thread_id=thread_id,
        objective=objective,
        selection_view=selection,
    )


def open_thread_goal_menu_plan(goal: Optional[ThreadGoal] = None, error: Any = None) -> ThreadGoalActionPlan:
    if error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("read", error),
        )
    if goal is None:
        return ThreadGoalActionPlan(
            actions=("add_info_message",),
            message="Usage: /goal <objective>",
            hint="No goal is currently set.",
        )
    return ThreadGoalActionPlan(actions=("show_goal_summary",), thread_id=goal.thread_id)


def maybe_prompt_resume_paused_goal_after_resume_plan(
    thread_id: Any,
    goal: Optional[ThreadGoal] = None,
    error: Any = None,
) -> ThreadGoalActionPlan:
    if error is not None or goal is None:
        return ThreadGoalActionPlan(actions=("ignore",), thread_id=thread_id)
    if _status_value(goal.status) in {
        ThreadGoalStatus.Paused.value,
        ThreadGoalStatus.Blocked.value,
        ThreadGoalStatus.UsageLimited.value,
    }:
        return ThreadGoalActionPlan(
            actions=("show_resume_paused_goal_prompt",),
            thread_id=thread_id,
            objective=goal.objective,
        )
    return ThreadGoalActionPlan(actions=("ignore",), thread_id=thread_id)


def open_thread_goal_editor_plan(thread_id: Any = None, goal: Optional[ThreadGoal] = None, error: Any = None) -> ThreadGoalActionPlan:
    if thread_id is None or goal is None:
        return show_no_thread_goal_to_edit_plan()
    if error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("read", error),
            thread_id=thread_id,
        )
    return ThreadGoalActionPlan(actions=("show_goal_edit_prompt",), thread_id=thread_id)


def set_thread_goal_objective_plan(
    thread_id: Any,
    objective: str,
    mode: Any,
    existing_goal: Optional[ThreadGoal] = None,
    read_error: Any = None,
    clear_error: Any = None,
    set_error: Any = None,
    response_goal: Optional[ThreadGoal] = None,
) -> ThreadGoalActionPlan:
    if mode == ThreadGoalSetMode.ConfirmIfExists and read_error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("read", read_error),
            thread_id=thread_id,
        )
    effective_mode = mode
    if mode == ThreadGoalSetMode.ConfirmIfExists and existing_goal is not None:
        if should_confirm_before_replacing_goal(existing_goal):
            return show_replace_thread_goal_confirmation_plan(thread_id, objective)
        effective_mode = ThreadGoalSetMode.ReplaceExisting
    replacing_goal = effective_mode == ThreadGoalSetMode.ReplaceExisting
    if replacing_goal and clear_error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("replace", clear_error),
            thread_id=thread_id,
            server_calls=(("thread_goal_clear", thread_id),),
        )
    status = ThreadGoalStatus.Active
    token_budget = None
    if isinstance(effective_mode, UpdateExistingMode):
        status = effective_mode.status
        token_budget = effective_mode.token_budget
    if set_error is not None:
        action = "replace" if replacing_goal else "set"
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message(action, set_error),
            thread_id=thread_id,
        )
    goal = response_goal or ThreadGoal(status=status, thread_id=str(thread_id), objective=objective, token_budget=token_budget)
    return ThreadGoalActionPlan(
        actions=("thread_goal_clear", "thread_goal_set", "add_info_message") if replacing_goal else ("thread_goal_set", "add_info_message"),
        message="Goal %s" % goal_status_label(goal.status),
        hint=goal_usage_summary(goal),
        thread_id=thread_id,
        objective=objective,
        status=status,
        token_budget=token_budget,
    )


def set_thread_goal_status_plan(thread_id: Any, status: Any, error: Any = None, response_goal: Optional[ThreadGoal] = None) -> ThreadGoalActionPlan:
    if error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("update", error),
            thread_id=thread_id,
            status=status,
        )
    goal = response_goal or ThreadGoal(status=status, thread_id=str(thread_id))
    return ThreadGoalActionPlan(
        actions=("thread_goal_set", "add_info_message"),
        message="Goal %s" % goal_status_label(goal.status),
        hint=goal_usage_summary(goal),
        thread_id=thread_id,
        status=status,
    )


def clear_thread_goal_plan(thread_id: Any, cleared: Optional[bool] = None, error: Any = None) -> ThreadGoalActionPlan:
    if error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("clear", error),
            thread_id=thread_id,
        )
    if cleared:
        return ThreadGoalActionPlan(actions=("add_info_message",), message="Goal cleared", thread_id=thread_id)
    return ThreadGoalActionPlan(
        actions=("add_info_message",),
        message="No goal to clear",
        hint="This thread does not currently have a goal.",
        thread_id=thread_id,
    )


async def open_thread_goal_menu(*args: Any, **kwargs: Any) -> ThreadGoalActionPlan:
    return open_thread_goal_menu_plan(*args, **kwargs)


async def maybe_prompt_resume_paused_goal_after_resume(*args: Any, **kwargs: Any) -> ThreadGoalActionPlan:
    return maybe_prompt_resume_paused_goal_after_resume_plan(*args, **kwargs)


async def open_thread_goal_editor(*args: Any, **kwargs: Any) -> ThreadGoalActionPlan:
    return open_thread_goal_editor_plan(*args, **kwargs)


async def set_thread_goal_objective(*args: Any, **kwargs: Any) -> ThreadGoalActionPlan:
    return set_thread_goal_objective_plan(*args, **kwargs)


async def set_thread_goal_status(*args: Any, **kwargs: Any) -> ThreadGoalActionPlan:
    return set_thread_goal_status_plan(*args, **kwargs)


async def clear_thread_goal(*args: Any, **kwargs: Any) -> ThreadGoalActionPlan:
    return clear_thread_goal_plan(*args, **kwargs)


__all__ = [
    "EPHEMERAL_THREAD_GOAL_ERROR_MESSAGE",
    "RUST_MODULE",
    "SelectionItemPlan",
    "SelectionViewPlan",
    "ThreadGoal",
    "ThreadGoalActionPlan",
    "ThreadGoalSetMode",
    "ThreadGoalStatus",
    "UpdateExistingMode",
    "clear_thread_goal",
    "clear_thread_goal_plan",
    "goal_status_label",
    "goal_usage_summary",
    "is_ephemeral_thread_goal_error",
    "maybe_prompt_resume_paused_goal_after_resume",
    "maybe_prompt_resume_paused_goal_after_resume_plan",
    "open_thread_goal_editor",
    "open_thread_goal_editor_plan",
    "open_thread_goal_menu",
    "open_thread_goal_menu_plan",
    "set_thread_goal_objective",
    "set_thread_goal_objective_plan",
    "set_thread_goal_status",
    "set_thread_goal_status_plan",
    "should_confirm_before_replacing_goal",
    "show_no_thread_goal_to_edit_plan",
    "show_replace_thread_goal_confirmation_plan",
    "test_goal",
    "thread_goal_error_message",
]
