"""Thread goal action helpers for Rust ``codex-tui::app::thread_goal_actions``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_goal_actions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

from pycodex.app_server_protocol import ThreadGoal, ThreadGoalStatus

from .._porting import RustTuiModule
from ..app_event import AppEvent, ThreadGoalSetMode as AppThreadGoalSetMode
from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams
from ..bottom_pane.popup_consts import standard_popup_hint_line
from ..bottom_pane.custom_prompt_view import CustomPromptView
from ..chatwidget.goal_menu import edited_goal_status, goal_edit_prompt
from ..goal_display import goal_status_label as display_goal_status_label
from ..goal_display import goal_usage_summary as display_goal_usage_summary

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


ThreadGoalSetMode = AppThreadGoalSetMode


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
    return ThreadGoalStatus.parse(status).value


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
    status = ThreadGoalStatus.parse(getattr(goal, "status", goal))
    return status is not ThreadGoalStatus.COMPLETE


def _new_thread_goal(
    *,
    status: Any,
    thread_id: str = "thread-1",
    objective: str = "Finish the thing.",
    token_budget: Optional[int] = None,
    tokens_used: int = 0,
    time_used_seconds: int = 0,
) -> ThreadGoal:
    return ThreadGoal(
        thread_id=thread_id,
        objective=objective,
        status=ThreadGoalStatus.parse(status),
        token_budget=token_budget,
        tokens_used=tokens_used,
        time_used_seconds=time_used_seconds,
        created_at=1_776_272_400,
        updated_at=1_776_272_460,
    )


def test_goal(status: Any) -> ThreadGoal:
    return _new_thread_goal(status=status)


def goal_status_label(status: Any) -> str:
    return display_goal_status_label(ThreadGoalStatus.parse(status))


def goal_usage_summary(goal: ThreadGoal) -> str:
    return display_goal_usage_summary(goal)


def show_no_thread_goal_to_edit_plan() -> ThreadGoalActionPlan:
    return ThreadGoalActionPlan(
        actions=("add_error_message", "add_info_message"),
        message="No goal is currently set.",
        hint="Create a goal before editing it.",
    )


def open_thread_goal_menu_runtime(
    active_runtime: Any,
    thread_id: Any,
    *,
    current_displayed_thread_id: Callable[[], Any],
    add_error_message: Callable[[str], Any],
    add_info_message: Callable[[str, Optional[str]], Any],
    show_goal_summary: Callable[[Any], Any],
) -> Any:
    """Execute Rust ``App::open_thread_goal_menu`` at the local RPC boundary."""

    try:
        goal = active_runtime.thread_goal_get(thread_id)
    except Exception as error:
        if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
            return None
        add_error_message(thread_goal_error_message("read", error))
        return None
    if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
        return None
    if goal is None:
        add_info_message("Usage: /goal <objective>", "No goal is currently set.")
        return None
    show_goal_summary(goal)
    return goal


def open_thread_goal_editor_runtime(
    active_runtime: Any,
    thread_id: Any,
    *,
    current_displayed_thread_id: Callable[[], Any],
    send_app_event: Callable[[AppEvent], Any],
    show_view: Callable[[CustomPromptView], Any],
    add_error_message: Callable[[str], Any],
    add_info_message: Callable[[str, Optional[str]], Any],
) -> CustomPromptView | None:
    """Execute Rust ``App::open_thread_goal_editor`` and its ChatWidget anchor."""

    if thread_id is None:
        _show_no_thread_goal_to_edit(add_error_message, add_info_message)
        return None
    try:
        goal = active_runtime.thread_goal_get(thread_id)
    except Exception as error:
        if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
            return None
        add_error_message(thread_goal_error_message("read", error))
        return None
    if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
        return None
    if goal is None:
        _show_no_thread_goal_to_edit(add_error_message, add_info_message)
        return None

    status = edited_goal_status(getattr(goal, "status", "active"))
    token_budget = getattr(goal, "token_budget", None)

    def submit(objective: str) -> None:
        send_app_event(
            AppEvent.set_thread_goal_objective(
                thread_id,
                objective,
                AppThreadGoalSetMode.update_existing(status, token_budget),
            )
        )

    view = goal_edit_prompt(goal, submit)
    show_view(view)
    return view


def set_thread_goal_objective_runtime(
    active_runtime: Any,
    thread_id: Any,
    objective: str,
    mode: Any,
    *,
    current_displayed_thread_id: Callable[[], Any],
    show_view: Callable[[Any], Any],
    add_error_message: Callable[[str], Any],
    add_info_message: Callable[[str, Optional[str]], Any],
) -> Any:
    """Execute Rust ``App::set_thread_goal_objective`` synchronously."""

    mode_kind = _app_mode_kind(mode)
    if mode_kind == AppThreadGoalSetMode.CONFIRM_IF_EXISTS:
        try:
            existing = active_runtime.thread_goal_get(thread_id)
        except Exception as error:
            if _thread_is_still_displayed(current_displayed_thread_id, thread_id):
                add_error_message(thread_goal_error_message("read", error))
            return None
        if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
            return None
        if existing is not None and should_confirm_before_replacing_goal(existing):
            show_view(replace_thread_goal_confirmation_view(thread_id, objective))
            return None
        if existing is not None:
            mode_kind = AppThreadGoalSetMode.REPLACE_EXISTING

    replacing_goal = mode_kind == AppThreadGoalSetMode.REPLACE_EXISTING
    if replacing_goal:
        try:
            active_runtime.thread_goal_clear(thread_id)
        except Exception as error:
            if _thread_is_still_displayed(current_displayed_thread_id, thread_id):
                add_error_message(thread_goal_error_message("replace", error))
            return None

    status: Any = ThreadGoalStatus.ACTIVE.value
    set_kwargs: dict[str, Any] = {"objective": objective, "status": status}
    if mode_kind == AppThreadGoalSetMode.UPDATE_EXISTING:
        status = getattr(mode, "status", ThreadGoalStatus.ACTIVE)
        set_kwargs["status"] = getattr(status, "value", status)
        set_kwargs["token_budget"] = getattr(mode, "token_budget", None)
    try:
        updated_goal = active_runtime.thread_goal_set(thread_id, **set_kwargs)
    except Exception as error:
        if _thread_is_still_displayed(current_displayed_thread_id, thread_id):
            add_error_message(thread_goal_error_message("replace" if replacing_goal else "set", error))
        return None
    if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
        return None
    add_info_message(
        f"Goal {display_goal_status_label(getattr(updated_goal, 'status', status))}",
        display_goal_usage_summary(updated_goal),
    )
    return updated_goal


def set_thread_goal_status_runtime(
    active_runtime: Any,
    thread_id: Any,
    status: Any,
    *,
    current_displayed_thread_id: Callable[[], Any],
    add_error_message: Callable[[str], Any],
    add_info_message: Callable[[str, Optional[str]], Any],
) -> Any:
    try:
        updated_goal = active_runtime.thread_goal_set(
            thread_id,
            status=getattr(status, "value", status),
        )
    except Exception as error:
        if _thread_is_still_displayed(current_displayed_thread_id, thread_id):
            add_error_message(thread_goal_error_message("update", error))
        return None
    if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
        return None
    add_info_message(
        f"Goal {display_goal_status_label(getattr(updated_goal, 'status', status))}",
        display_goal_usage_summary(updated_goal),
    )
    return updated_goal


def clear_thread_goal_runtime(
    active_runtime: Any,
    thread_id: Any,
    *,
    current_displayed_thread_id: Callable[[], Any],
    add_error_message: Callable[[str], Any],
    add_info_message: Callable[[str, Optional[str]], Any],
) -> bool | None:
    try:
        response = active_runtime.thread_goal_clear(thread_id)
    except Exception as error:
        if _thread_is_still_displayed(current_displayed_thread_id, thread_id):
            add_error_message(thread_goal_error_message("clear", error))
        return None
    if not _thread_is_still_displayed(current_displayed_thread_id, thread_id):
        return None
    cleared = bool(response.get("cleared", False)) if isinstance(response, dict) else bool(getattr(response, "cleared", response))
    if cleared:
        add_info_message("Goal cleared", None)
    else:
        add_info_message("No goal to clear", "This thread does not currently have a goal.")
    return cleared


def replace_thread_goal_confirmation_view(thread_id: Any, objective: str) -> SelectionViewParams:
    return SelectionViewParams(
        title="Replace goal?",
        subtitle=f"New objective: {objective}",
        footer_hint=standard_popup_hint_line(),
        items=[
            SelectionItem(
                name="Replace current goal",
                description="Set the new objective and start it now",
                actions=[
                    AppEvent.set_thread_goal_objective(
                        thread_id,
                        objective,
                        AppThreadGoalSetMode.replace_existing(),
                    )
                ],
                dismiss_on_select=True,
            ),
            SelectionItem(
                name="Cancel",
                description="Keep the current goal",
                dismiss_on_select=True,
            ),
        ],
    )


def _show_no_thread_goal_to_edit(
    add_error_message: Callable[[str], Any],
    add_info_message: Callable[[str, Optional[str]], Any],
) -> None:
    add_error_message("No goal is currently set.")
    add_info_message("Usage: /goal <objective>", "Create a goal before editing it.")


def _thread_is_still_displayed(current_displayed_thread_id: Callable[[], Any], thread_id: Any) -> bool:
    current = current_displayed_thread_id()
    return current is not None and str(current) == str(thread_id)


def _app_mode_kind(mode: Any) -> str:
    kind = getattr(mode, "kind", None)
    if kind is not None:
        return str(kind)
    text = str(getattr(mode, "value", mode))
    return {
        "confirm_if_exists": AppThreadGoalSetMode.CONFIRM_IF_EXISTS,
        "replace_existing": AppThreadGoalSetMode.REPLACE_EXISTING,
        "update_existing": AppThreadGoalSetMode.UPDATE_EXISTING,
    }.get(text, text)


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
                    "mode": AppThreadGoalSetMode.REPLACE_EXISTING,
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
    if ThreadGoalStatus.parse(goal.status) in {
        ThreadGoalStatus.PAUSED,
        ThreadGoalStatus.BLOCKED,
        ThreadGoalStatus.USAGE_LIMITED,
    }:
        return ThreadGoalActionPlan(
            actions=("show_resume_paused_goal_prompt",),
            thread_id=thread_id,
            objective=goal.objective,
        )
    return ThreadGoalActionPlan(actions=("ignore",), thread_id=thread_id)


def open_thread_goal_editor_plan(thread_id: Any = None, goal: Optional[ThreadGoal] = None, error: Any = None) -> ThreadGoalActionPlan:
    if error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("read", error),
            thread_id=thread_id,
        )
    if thread_id is None or goal is None:
        return show_no_thread_goal_to_edit_plan()
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
    mode_kind = _app_mode_kind(mode)
    if mode_kind == AppThreadGoalSetMode.CONFIRM_IF_EXISTS and read_error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("read", read_error),
            thread_id=thread_id,
        )
    effective_mode = mode
    if mode_kind == AppThreadGoalSetMode.CONFIRM_IF_EXISTS and existing_goal is not None:
        if should_confirm_before_replacing_goal(existing_goal):
            return show_replace_thread_goal_confirmation_plan(thread_id, objective)
        effective_mode = AppThreadGoalSetMode.replace_existing()
    effective_mode_kind = _app_mode_kind(effective_mode)
    replacing_goal = effective_mode_kind == AppThreadGoalSetMode.REPLACE_EXISTING
    if replacing_goal and clear_error is not None:
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message("replace", clear_error),
            thread_id=thread_id,
            server_calls=(("thread_goal_clear", thread_id),),
        )
    status = ThreadGoalStatus.ACTIVE
    token_budget = None
    if effective_mode_kind == AppThreadGoalSetMode.UPDATE_EXISTING:
        status = effective_mode.status
        token_budget = effective_mode.token_budget
    if set_error is not None:
        action = "replace" if replacing_goal else "set"
        return ThreadGoalActionPlan(
            actions=("add_error_message",),
            message=thread_goal_error_message(action, set_error),
            thread_id=thread_id,
        )
    goal = response_goal or _new_thread_goal(
        status=status,
        thread_id=str(thread_id),
        objective=objective,
        token_budget=token_budget,
    )
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
    goal = response_goal or _new_thread_goal(status=status, thread_id=str(thread_id))
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
    "clear_thread_goal",
    "clear_thread_goal_plan",
    "clear_thread_goal_runtime",
    "goal_status_label",
    "goal_usage_summary",
    "is_ephemeral_thread_goal_error",
    "maybe_prompt_resume_paused_goal_after_resume",
    "maybe_prompt_resume_paused_goal_after_resume_plan",
    "open_thread_goal_editor",
    "open_thread_goal_editor_plan",
    "open_thread_goal_editor_runtime",
    "open_thread_goal_menu",
    "open_thread_goal_menu_plan",
    "open_thread_goal_menu_runtime",
    "replace_thread_goal_confirmation_view",
    "set_thread_goal_objective",
    "set_thread_goal_objective_plan",
    "set_thread_goal_objective_runtime",
    "set_thread_goal_status",
    "set_thread_goal_status_plan",
    "set_thread_goal_status_runtime",
    "should_confirm_before_replacing_goal",
    "show_no_thread_goal_to_edit_plan",
    "show_replace_thread_goal_confirmation_plan",
    "test_goal",
    "thread_goal_error_message",
]
