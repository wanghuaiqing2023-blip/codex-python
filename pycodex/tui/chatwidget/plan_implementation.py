"""Plan-implementation confirmation prompt for ``chatwidget::plan_implementation``."""

from __future__ import annotations

from typing import Any

from .._porting import RustTuiModule
from ..app_event import AppEvent
from ..bottom_pane.list_selection_view import SelectionItem, SelectionViewParams
from ..bottom_pane.popup_consts import standard_popup_hint_line

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::plan_implementation", source="codex/codex-rs/tui/src/chatwidget/plan_implementation.rs")

PLAN_IMPLEMENTATION_TITLE = "Implement this plan?"
PLAN_IMPLEMENTATION_YES = "Yes, implement this plan"
PLAN_IMPLEMENTATION_CLEAR_CONTEXT = "Yes, clear context and implement"
PLAN_IMPLEMENTATION_NO = "No, stay in Plan mode"
PLAN_IMPLEMENTATION_CODING_MESSAGE = "Implement the plan."
PLAN_IMPLEMENTATION_CLEAR_CONTEXT_PREFIX = (
    "A previous agent produced the plan below to accomplish the user's task. "
    "Implement the plan in a fresh context. Treat the plan as the source of "
    "user intent, re-read files as needed, and carry the work through "
    "implementation and verification."
)
PLAN_IMPLEMENTATION_DEFAULT_UNAVAILABLE = "Default mode unavailable"
PLAN_IMPLEMENTATION_NO_APPROVED_PLAN = "No approved plan available"

def _emit(tx: Any, event: AppEvent) -> None:
    send = getattr(tx, "send", None)
    if callable(send):
        send(event)
    elif callable(tx):
        tx(event)
    elif hasattr(tx, "append"):
        tx.append(event)


def selection_view_params(
    default_mask: Any | None,
    plan_markdown: str | None,
    clear_context_usage_label: str | None,
) -> SelectionViewParams:
    if default_mask is not None:
        implement_actions = [
            lambda tx, mask=default_mask: _emit(
                tx,
                AppEvent.submit_user_message_with_mode(
                    PLAN_IMPLEMENTATION_CODING_MESSAGE,
                    mask,
                ),
            )
        ]
        implement_disabled_reason = None
    else:
        implement_actions = []
        implement_disabled_reason = PLAN_IMPLEMENTATION_DEFAULT_UNAVAILABLE

    if default_mask is None:
        clear_context_actions = []
        clear_context_disabled_reason = PLAN_IMPLEMENTATION_DEFAULT_UNAVAILABLE
    elif plan_markdown is not None and plan_markdown.strip() != "":
        clear_text = f"{PLAN_IMPLEMENTATION_CLEAR_CONTEXT_PREFIX}\n\n{plan_markdown}"
        clear_context_actions = [
            lambda tx, text=clear_text: _emit(
                tx,
                AppEvent.clear_ui_and_submit_user_message(text),
            )
        ]
        clear_context_disabled_reason = None
    else:
        clear_context_actions = []
        clear_context_disabled_reason = PLAN_IMPLEMENTATION_NO_APPROVED_PLAN

    clear_context_description = (
        "Fresh thread with this plan."
        if clear_context_usage_label is None
        else f"Fresh thread. Context: {clear_context_usage_label}."
    )

    return SelectionViewParams(
        title=PLAN_IMPLEMENTATION_TITLE,
        subtitle=None,
        footer_hint=standard_popup_hint_line(),
        items=[
            SelectionItem(
                name=PLAN_IMPLEMENTATION_YES,
                description="Switch to Default and start coding.",
                actions=implement_actions,
                disabled_reason=implement_disabled_reason,
                dismiss_on_select=True,
            ),
            SelectionItem(
                name=PLAN_IMPLEMENTATION_CLEAR_CONTEXT,
                description=clear_context_description,
                actions=clear_context_actions,
                disabled_reason=clear_context_disabled_reason,
                dismiss_on_select=True,
            ),
            SelectionItem(
                name=PLAN_IMPLEMENTATION_NO,
                description="Continue planning with the model.",
                actions=[],
                disabled_reason=None,
                dismiss_on_select=True,
            ),
        ],
    )


__all__ = [
    "PLAN_IMPLEMENTATION_CLEAR_CONTEXT",
    "PLAN_IMPLEMENTATION_CLEAR_CONTEXT_PREFIX",
    "PLAN_IMPLEMENTATION_CODING_MESSAGE",
    "PLAN_IMPLEMENTATION_DEFAULT_UNAVAILABLE",
    "PLAN_IMPLEMENTATION_NO",
    "PLAN_IMPLEMENTATION_NO_APPROVED_PLAN",
    "PLAN_IMPLEMENTATION_TITLE",
    "PLAN_IMPLEMENTATION_YES",
    "RUST_MODULE",
    "selection_view_params",
    "standard_popup_hint_line",
]
