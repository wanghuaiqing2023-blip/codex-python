"""Semantic helpers for Rust ``codex-tui::app::input``.

Rust owns global key dispatch, external editor launch, raw-output toggles, and
status-line refresh in this module. Python models process/TUI/app-server side
effects as deterministic input action plans while preserving pure predicates and
state transitions directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::input",
    source="codex/codex-rs/tui/src/app/input.rs",
    status="complete",
)

SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE = "Editing previous prompts is unavailable in side conversations."
EXTERNAL_EDITOR_HINT = "Editing in external editor"
MISSING_EDITOR_MESSAGE = "Cannot open external editor: set $VISUAL or $EDITOR before starting Codex."


@dataclass(eq=True)
class AppInputState:
    """Minimal App/ChatWidget state touched by input helpers."""

    overlay_active: bool = False
    modal_or_popup_active: bool = False
    side_conversation_active: bool = False
    normal_backtrack_mode: bool = True
    composer_empty: bool = True
    vim_insert_escape_handled: bool = False
    backtrack_primed: bool = False
    backtrack_nth_user_message: Optional[int] = None
    external_editor_state: str = "Closed"
    footer_hint_override: Optional[List[Tuple[str, str]]] = None
    frame_requested: bool = False
    errors: Optional[List[str]] = None
    infos: Optional[List[str]] = None
    raw_output_mode: bool = False
    can_toggle_fast_mode: bool = True
    can_launch_external_editor: bool = True
    can_clear_terminal: bool = True
    enhanced_keys_supported: bool = True
    status_line_refreshed: bool = False

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []
        if self.infos is None:
            self.infos = []


@dataclass(frozen=True, eq=True)
class KeyEvent:
    code: str
    kind: str = "press"
    modifiers: Tuple[str, ...] = ()


@dataclass(frozen=True, eq=True)
class InputActionPlan:
    action: str
    updates: Tuple[Tuple[str, Any], ...] = ()
    message: Optional[str] = None
    schedule_frame: bool = False
    forward_to_chat_widget: bool = False


def app_keymap_shortcuts_available(state: AppInputState) -> bool:
    return not state.overlay_active and not state.modal_or_popup_active


def should_handle_backtrack_esc(state: AppInputState, vim_insert_escape_handled: Optional[bool] = None) -> bool:
    vim_escape = state.vim_insert_escape_handled if vim_insert_escape_handled is None else vim_insert_escape_handled
    return (not state.side_conversation_active and state.normal_backtrack_mode and state.composer_empty and not vim_escape)


def should_reject_side_backtrack_esc(state: AppInputState, vim_insert_escape_handled: Optional[bool] = None) -> bool:
    vim_escape = state.vim_insert_escape_handled if vim_insert_escape_handled is None else vim_insert_escape_handled
    return (state.side_conversation_active and state.normal_backtrack_mode and state.composer_empty and not vim_escape)


def reject_side_backtrack_esc(state: AppInputState) -> InputActionPlan:
    state.backtrack_primed = False
    assert state.errors is not None
    state.errors.append(SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE)
    return InputActionPlan(
        action="reject_side_backtrack_esc",
        updates=(("backtrack.primed", False),),
        message=SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE,
    )


def request_external_editor_launch(state: AppInputState) -> InputActionPlan:
    state.external_editor_state = "Requested"
    state.footer_hint_override = [(EXTERNAL_EDITOR_HINT, "")]
    state.frame_requested = True
    return InputActionPlan(
        action="request_external_editor_launch",
        updates=(("external_editor_state", "Requested"), ("footer_hint_override", [(EXTERNAL_EDITOR_HINT, "")])),
        schedule_frame=True,
    )


def reset_external_editor_state(state: AppInputState) -> InputActionPlan:
    state.external_editor_state = "Closed"
    state.footer_hint_override = None
    state.frame_requested = True
    return InputActionPlan(
        action="reset_external_editor_state",
        updates=(("external_editor_state", "Closed"), ("footer_hint_override", None)),
        schedule_frame=True,
    )


async def launch_external_editor(state: AppInputState, editor_result: Any = None, editor_error: Any = None, missing_editor: bool = False) -> InputActionPlan:
    reset_external_editor_state(state)
    if missing_editor:
        assert state.errors is not None
        state.errors.append(MISSING_EDITOR_MESSAGE)
        return InputActionPlan(action="external_editor_missing", message=MISSING_EDITOR_MESSAGE, schedule_frame=True)
    if editor_error is not None:
        message = "Failed to open editor: %s" % editor_error
        assert state.errors is not None
        state.errors.append(message)
        return InputActionPlan(action="external_editor_failed", message=message, schedule_frame=True)
    cleaned = "" if editor_result is None else str(editor_result).rstrip()
    return InputActionPlan(action="external_editor_apply", updates=(("composer.external_edit", cleaned),), schedule_frame=True)


def apply_raw_output_mode(state: AppInputState, enabled: bool, notify: bool = False, reflow_error: Any = None) -> InputActionPlan:
    state.raw_output_mode = bool(enabled)
    state.frame_requested = True
    updates = (("raw_output_mode", bool(enabled)), ("notify", bool(notify)))
    if reflow_error is not None:
        message = "Failed to redraw transcript: %s" % reflow_error
        assert state.errors is not None
        state.errors.append(message)
        return InputActionPlan(action="apply_raw_output_mode", updates=updates, message=message, schedule_frame=True)
    return InputActionPlan(action="apply_raw_output_mode", updates=updates, schedule_frame=True)


def refresh_status_line(state: AppInputState) -> InputActionPlan:
    state.status_line_refreshed = True
    return InputActionPlan(action="refresh_status_line", updates=(("status_line_refreshed", True),))


def _key_code(key_event: Any) -> str:
    if isinstance(key_event, dict):
        return str(key_event.get("code", ""))
    return str(getattr(key_event, "code", key_event))


def _key_kind(key_event: Any) -> str:
    if isinstance(key_event, dict):
        return str(key_event.get("kind", "press")).lower()
    return str(getattr(key_event, "kind", "press")).lower()


async def handle_key_event(state: AppInputState, key_event: Any, command: Optional[str] = None) -> InputActionPlan:
    code = _key_code(key_event).lower()
    kind = _key_kind(key_event)
    shortcuts = app_keymap_shortcuts_available(state)
    if command == "toggle_vim_mode" and shortcuts:
        return InputActionPlan(action="toggle_vim_mode")
    if command == "toggle_fast_mode" and shortcuts and state.can_toggle_fast_mode:
        return InputActionPlan(action="toggle_fast_mode")
    if command == "toggle_raw_output" and shortcuts:
        return apply_raw_output_mode(state, not state.raw_output_mode, notify=False)
    if command == "open_transcript" and shortcuts:
        state.overlay_active = True
        state.frame_requested = True
        return InputActionPlan(action="open_transcript_overlay", updates=(("overlay", "transcript"),), schedule_frame=True)
    if command == "open_external_editor" and shortcuts:
        if (not state.overlay_active and state.can_launch_external_editor and state.external_editor_state == "Closed"):
            return request_external_editor_launch(state)
        return InputActionPlan(action="ignore_external_editor_shortcut")
    if command == "clear_terminal" and shortcuts:
        if not state.can_clear_terminal:
            return InputActionPlan(action="ignore_clear_terminal")
        state.frame_requested = True
        return InputActionPlan(action="clear_terminal_ui", updates=(("reset_app_ui_state_after_clear", True), ("queue_clear_ui_header", True)), schedule_frame=True)
    if code == "esc" and kind in {"press", "repeat"}:
        if should_handle_backtrack_esc(state):
            state.backtrack_primed = True
            return InputActionPlan(action="handle_backtrack_esc", updates=(("backtrack.primed", True),))
        if should_reject_side_backtrack_esc(state):
            return reject_side_backtrack_esc(state)
        return InputActionPlan(action="forward_escape_to_chat_widget", forward_to_chat_widget=True)
    if code == "enter" and kind == "press" and state.backtrack_primed and state.backtrack_nth_user_message is not None and state.composer_empty:
        return InputActionPlan(action="confirm_backtrack", updates=(("apply_backtrack_selection", True),))
    if kind in {"press", "repeat"}:
        updates = ()
        if code != "esc" and state.backtrack_primed:
            state.backtrack_primed = False
            updates = (("backtrack.primed", False),)
        return InputActionPlan(action="forward_key_to_chat_widget", updates=updates, forward_to_chat_widget=True)
    return InputActionPlan(action="forward_key_to_chat_widget", forward_to_chat_widget=True)


async def app_keymap_shortcuts_are_disabled_while_keymap_view_is_active(state: Optional[AppInputState] = None) -> bool:
    state = state or AppInputState(modal_or_popup_active=True)
    return not app_keymap_shortcuts_available(state)


__all__ = [
    "EXTERNAL_EDITOR_HINT",
    "InputActionPlan",
    "KeyEvent",
    "MISSING_EDITOR_MESSAGE",
    "RUST_MODULE",
    "SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE",
    "AppInputState",
    "app_keymap_shortcuts_are_disabled_while_keymap_view_is_active",
    "app_keymap_shortcuts_available",
    "apply_raw_output_mode",
    "handle_key_event",
    "launch_external_editor",
    "refresh_status_line",
    "reject_side_backtrack_esc",
    "request_external_editor_launch",
    "reset_external_editor_state",
    "should_handle_backtrack_esc",
    "should_reject_side_backtrack_esc",
]
