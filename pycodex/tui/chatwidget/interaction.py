"""Key routing and composer-adjacent interaction helpers for chat widgets.

This module ports the local semantic behavior of Rust
``codex-tui::chatwidget::interaction``.  Terminal keymap integration and OS
clipboard/paste-image backends are represented as injectable callbacks and
simple DTOs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, List, Optional, Protocol, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::interaction",
    source="codex/codex-rs/tui/src/chatwidget/interaction.rs",
    status="complete",
)

__all__ = [
    "AppCommand",
    "CancellationEvent",
    "ExternalEditorState",
    "FrameRequester",
    "KeyBinding",
    "KeyEvent",
    "copy_last_agent_markdown_with",
    "apply_external_edit",
    "arm_quit_shortcut",
    "attach_image",
    "can_launch_external_editor",
    "can_run_ctrl_l_clear_now",
    "composer_text_with_pending",
    "ensure_thread_rename_allowed",
    "handle_paste",
    "handle_paste_burst_tick",
    "handle_key_event",
    "is_cancellable_work_active",
    "no_modal_or_popup_active",
    "on_ctrl_c",
    "on_ctrl_d",
    "RUST_MODULE",
    "set_external_editor_state",
    "set_footer_hint_override",
    "show_rename_prompt",
    "show_selection_view",
    "truncate_agent_copy_history_to_user_turn_count",
]


DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED = False
QUIT_SHORTCUT_TIMEOUT_TICKS = 1
MAX_AGENT_COPY_HISTORY = 20


class CancellationEvent(str, Enum):
    HANDLED = "Handled"
    IGNORED = "Ignored"


class ExternalEditorState(str, Enum):
    IDLE = "Idle"
    OPEN = "Open"
    ERROR = "Error"


@dataclass(frozen=True)
class KeyBinding:
    key: str

    def is_pressed(self, key_event: "KeyEvent") -> bool:
        return key_event.kind == "Press" and key_event.binding_name() == self.key


@dataclass(frozen=True)
class KeyEvent:
    """Semantic crossterm KeyEvent used by the Python port.

    ``code`` is one of ``"char"``, ``"esc"``, ``"backtab"`` or a named key.
    Modifiers are lowercase strings such as ``"control"`` and ``"alt"``.
    """

    code: str
    char: Optional[str] = None
    modifiers: Tuple[str, ...] = ()
    kind: str = "Press"

    def binding_name(self) -> str:
        if self.code == "char" and self.char:
            parts = []
            if "control" in self.modifiers:
                parts.append("ctrl")
            if "alt" in self.modifiers:
                parts.append("alt")
            parts.append(self.char.lower())
            return "-".join(parts)
        return self.code.lower()


@dataclass(frozen=True)
class AppCommand:
    kind: str

    @classmethod
    def interrupt(cls) -> "AppCommand":
        return cls("Interrupt")


@dataclass
class FrameRequester:
    scheduled_delays: List[Any]

    def schedule_frame_in(self, delay: Any) -> None:
        self.scheduled_delays.append(delay)


class InteractionWidget(Protocol):
    bottom_pane: Any
    transcript: Any


def attach_image(widget: Any, path: str) -> None:
    if not widget.current_model_supports_images():
        widget.add_to_history({"kind": "warning", "message": widget.image_inputs_not_supported_message()})
        widget.request_redraw()
        return
    widget.bottom_pane.attach_image(path)
    widget.request_redraw()


def composer_text_with_pending(widget: Any) -> str:
    return widget.bottom_pane.composer_text_with_pending()


def apply_external_edit(widget: Any, text: str) -> None:
    widget.bottom_pane.apply_external_edit(text)
    widget.refresh_plan_mode_nudge()
    widget.request_redraw()


def set_external_editor_state(widget: Any, state: Any) -> None:
    widget.external_editor_state = state


def set_footer_hint_override(widget: Any, items: Optional[List[Tuple[str, str]]]) -> None:
    widget.bottom_pane.set_footer_hint_override(items)


def show_selection_view(widget: Any, params: Any) -> None:
    widget.bottom_pane.show_selection_view(params)
    widget.refresh_plan_mode_nudge()
    widget.request_redraw()


def no_modal_or_popup_active(widget: Any) -> bool:
    return bool(widget.bottom_pane.no_modal_or_popup_active())


def can_launch_external_editor(widget: Any) -> bool:
    return bool(widget.bottom_pane.can_launch_external_editor())


def can_run_ctrl_l_clear_now(widget: Any) -> bool:
    if not widget.bottom_pane.is_task_running():
        return True
    widget.add_to_history({"kind": "error", "message": "Ctrl+L is disabled while a task is in progress."})
    widget.request_redraw()
    return False


def truncate_agent_copy_history_to_user_turn_count(widget: Any, user_turn_count: int) -> None:
    widget.transcript.truncate_copy_history_to_user_turn_count(user_turn_count)


def copy_last_agent_markdown_with(
    widget: Any,
    copy_fn: Callable[[str], Any],
) -> None:
    markdown = getattr(widget.transcript, "last_agent_markdown", None)
    if markdown:
        try:
            widget.clipboard_lease = copy_fn(markdown)
            widget.add_to_history({"kind": "info", "message": "Copied last message to clipboard", "hint": None})
        except Exception as error:  # mirrors Rust's error-string branch
            widget.add_to_history({"kind": "error", "message": f"Copy failed: {error}"})
    elif getattr(widget.transcript, "copy_history_evicted_by_rollback", False):
        widget.add_to_history(
            {
                "kind": "error",
                "message": (
                    "Cannot copy that response after rewinding. Only the most recent "
                    f"{MAX_AGENT_COPY_HISTORY} responses are available to /copy."
                ),
            }
        )
    else:
        widget.add_to_history({"kind": "error", "message": "No agent response to copy"})
    widget.request_redraw()


def ensure_thread_rename_allowed(widget: Any) -> bool:
    message = getattr(widget, "thread_rename_block_message", None)
    if message is not None:
        widget.add_error_message(message)
        return False
    return True


def show_rename_prompt(widget: Any) -> None:
    if not ensure_thread_rename_allowed(widget):
        return
    existing_name = getattr(widget, "thread_name", None) or ""
    title = "Rename thread" if existing_name else "Name thread"
    view = {
        "kind": "CustomPromptView",
        "title": title,
        "description": "Type a name and press Enter",
        "initial_text": existing_name,
        "context_label": None,
    }
    widget.bottom_pane.show_view(view)


def handle_paste(widget: Any, text: str) -> None:
    widget.bottom_pane.handle_paste(text)
    widget.refresh_plan_mode_nudge()


def handle_paste_burst_tick(widget: Any, frame_requester: FrameRequester) -> bool:
    if widget.bottom_pane.flush_paste_burst_if_due():
        widget.refresh_plan_mode_nudge()
        widget.request_redraw()
        return True
    if widget.bottom_pane.is_in_paste_burst():
        delay = widget.bottom_pane.recommended_paste_flush_delay()
        frame_requester.schedule_frame_in(delay)
        return True
    return False


def handle_key_event(widget: Any, key_event: KeyEvent, paste_image_fn: Optional[Callable[[], Tuple[str, Any]]] = None) -> None:
    if _bottom_pane_has_active_view(widget) and not _is_ctrl_char(key_event, "c") and not _is_ctrl_char(key_event, "r") and not _is_ctrl_char(key_event, "u"):
        widget.bottom_pane.handle_key_event(key_event)
        if widget.bottom_pane.no_modal_or_popup_active():
            widget.maybe_send_next_queued_input()
        return

    if _call_bool(widget, "handle_reasoning_shortcut", key_event):
        _clear_quit_shortcut(widget)
        return

    binding = getattr(widget, "copy_last_response_binding", None)
    if binding is not None and binding.is_pressed(key_event):
        _clear_quit_shortcut(widget)
        widget.copy_last_agent_markdown()
        return

    if _is_ctrl_char(key_event, "c"):
        on_ctrl_c(widget)
        return

    if _is_ctrl_char(key_event, "d"):
        if on_ctrl_d(widget):
            return
        _clear_quit_shortcut(widget)
    elif _is_ctrl_or_alt_char(key_event, "v"):
        try:
            if paste_image_fn is None:
                paste_image_fn = widget.paste_image_to_temp_png
            path, _info = paste_image_fn()
            attach_image(widget, path)
        except Exception as error:
            widget.add_to_history({"kind": "error", "message": f"Failed to paste image: {error}"})
        return
    elif key_event.kind == "Press":
        _clear_quit_shortcut(widget)

    keymap = getattr(widget, "chat_keymap", None)
    edit_queued = getattr(keymap, "edit_queued_message", None)
    if (
        edit_queued is not None
        and edit_queued.is_pressed(key_event)
        and widget.has_queued_follow_up_messages()
        and widget.bottom_pane.no_modal_or_popup_active()
    ):
        user_message = widget.pop_latest_queued_user_message()
        if user_message is not None:
            widget.restore_user_message_to_composer(user_message)
            widget.refresh_pending_input_preview()
            widget.request_redraw()
        return

    interrupt_turn = getattr(keymap, "interrupt_turn", None)
    if (
        interrupt_turn is not None
        and interrupt_turn.is_pressed(key_event)
        and getattr(widget.input_queue, "pending_steers", None)
        and widget.bottom_pane.is_task_running()
        and widget.bottom_pane.no_modal_or_popup_active()
        and not _call_bool(widget, "should_handle_vim_insert_escape", key_event)
    ):
        widget.input_queue.submit_pending_steers_after_interrupt = True
        if not widget.submit_op(AppCommand.interrupt()):
            widget.input_queue.submit_pending_steers_after_interrupt = False
        return

    if key_event.code == "esc" and key_event.kind == "Press" and widget.should_show_plan_mode_nudge():
        widget.dismiss_plan_mode_nudge()
        return

    if _call_bool(widget, "handle_plugins_popup_key_event", key_event):
        return

    if (
        key_event.code == "backtab"
        and key_event.kind == "Press"
        and widget.collaboration_modes_enabled()
        and not widget.bottom_pane.is_task_running()
        and widget.bottom_pane.no_modal_or_popup_active()
    ):
        widget.cycle_collaboration_mode()
        widget.refresh_plan_mode_nudge()
        return

    had_modal_or_popup = not widget.bottom_pane.no_modal_or_popup_active()
    input_result = widget.bottom_pane.handle_key_event(key_event)
    widget.handle_composer_input_result(input_result, had_modal_or_popup)


def on_ctrl_c(widget: Any) -> None:
    key = KeyBinding("ctrl-c")
    if widget.realtime_conversation.is_live():
        _clear_quit_shortcut(widget)
        widget.stop_realtime_conversation_from_ui()
        return

    modal_or_popup_active = not widget.bottom_pane.no_modal_or_popup_active()
    if widget.bottom_pane.on_ctrl_c() == CancellationEvent.HANDLED:
        if DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED:
            if modal_or_popup_active:
                _clear_quit_shortcut(widget)
            else:
                arm_quit_shortcut(widget, key)
        return

    if not DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED:
        if is_cancellable_work_active(widget):
            _clear_quit_shortcut(widget)
            pause_active_goal_for_interrupt(widget)
            widget.submit_op(AppCommand.interrupt())
        else:
            widget.request_quit_without_confirmation()
        return

    if quit_shortcut_active_for(widget, key):
        _clear_quit_shortcut(widget)
        widget.request_quit_without_confirmation()
        return

    arm_quit_shortcut(widget, key)
    if is_cancellable_work_active(widget):
        pause_active_goal_for_interrupt(widget)
        widget.submit_op(AppCommand.interrupt())


def on_ctrl_d(widget: Any) -> bool:
    key = KeyBinding("ctrl-d")
    if not DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED:
        if not widget.bottom_pane.composer_is_empty() or not widget.bottom_pane.no_modal_or_popup_active():
            return False
        widget.request_quit_without_confirmation()
        return True

    if quit_shortcut_active_for(widget, key):
        _clear_quit_shortcut(widget)
        widget.request_quit_without_confirmation()
        return True

    if not widget.bottom_pane.composer_is_empty() or not widget.bottom_pane.no_modal_or_popup_active():
        return False

    arm_quit_shortcut(widget, key)
    return True


def quit_shortcut_active_for(widget: Any, key: KeyBinding) -> bool:
    return getattr(widget, "quit_shortcut_key", None) == key and bool(getattr(widget, "quit_shortcut_expires_at", None))


def arm_quit_shortcut(widget: Any, key: KeyBinding) -> None:
    widget.quit_shortcut_expires_at = QUIT_SHORTCUT_TIMEOUT_TICKS
    widget.quit_shortcut_key = key
    widget.bottom_pane.show_quit_shortcut_hint(key)


def is_cancellable_work_active(widget: Any) -> bool:
    return bool(widget.bottom_pane.is_task_running() or widget.review.is_review_mode)


def pause_active_goal_for_interrupt(widget: Any) -> None:
    if not widget.turn_lifecycle.agent_turn_running:
        return
    goal = getattr(widget, "current_goal_status", None)
    if goal is None or not goal.is_active():
        return
    thread_id = getattr(widget, "thread_id", None)
    if thread_id is None:
        return
    widget.app_event_tx.send({"kind": "SetThreadGoalStatus", "thread_id": thread_id, "status": "Paused"})


def _clear_quit_shortcut(widget: Any) -> None:
    widget.quit_shortcut_expires_at = None
    widget.quit_shortcut_key = None
    widget.bottom_pane.clear_quit_shortcut_hint()


def _bottom_pane_has_active_view(widget: Any) -> bool:
    method = getattr(widget.bottom_pane, "has_active_view", None)
    return bool(method()) if callable(method) else False


def _is_ctrl_char(key_event: KeyEvent, char: str) -> bool:
    return key_event.kind == "Press" and key_event.code == "char" and (key_event.char or "").lower() == char and "control" in key_event.modifiers


def _is_ctrl_or_alt_char(key_event: KeyEvent, char: str) -> bool:
    return key_event.kind == "Press" and key_event.code == "char" and (key_event.char or "").lower() == char and ("control" in key_event.modifiers or "alt" in key_event.modifiers)


def _call_bool(widget: Any, method_name: str, *args: Any) -> bool:
    method = getattr(widget, method_name, None)
    return bool(method(*args)) if callable(method) else False
