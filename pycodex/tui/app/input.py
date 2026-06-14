"""Semantic helpers for Rust ``codex-tui::app::input``.

The full module owns keyboard dispatch and external-editor runtime behavior.
This Python port captures the small state predicates and transitions that are
independent of ratatui, app-server, and process-launching objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._porting import RustTuiModule, not_ported


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::input",
    source="codex/codex-rs/tui/src/app/input.rs",
    status="complete_slice",
)

SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE = (
    "Editing previous prompts is unavailable in side conversations."
)
EXTERNAL_EDITOR_HINT = "Editing in external editor"


@dataclass(eq=True)
class AppInputState:
    """Minimal App/ChatWidget state touched by pure input helpers."""

    overlay_active: bool = False
    modal_or_popup_active: bool = False
    side_conversation_active: bool = False
    normal_backtrack_mode: bool = True
    composer_empty: bool = True
    vim_insert_escape_handled: bool = False
    backtrack_primed: bool = False
    external_editor_state: str = "Closed"
    footer_hint_override: list[tuple[str, str]] | None = None
    frame_requested: bool = False
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def app_keymap_shortcuts_available(state: AppInputState) -> bool:
    """Rust ``App::app_keymap_shortcuts_available`` predicate."""

    return not state.overlay_active and not state.modal_or_popup_active


def should_handle_backtrack_esc(state: AppInputState, *, vim_insert_escape_handled: bool | None = None) -> bool:
    """Rust ``App::should_handle_backtrack_esc`` predicate."""

    vim_escape = state.vim_insert_escape_handled if vim_insert_escape_handled is None else vim_insert_escape_handled
    return (
        not state.side_conversation_active
        and state.normal_backtrack_mode
        and state.composer_empty
        and not vim_escape
    )


def should_reject_side_backtrack_esc(state: AppInputState, *, vim_insert_escape_handled: bool | None = None) -> bool:
    """Rust ``App::should_reject_side_backtrack_esc`` predicate."""

    vim_escape = state.vim_insert_escape_handled if vim_insert_escape_handled is None else vim_insert_escape_handled
    return (
        state.side_conversation_active
        and state.normal_backtrack_mode
        and state.composer_empty
        and not vim_escape
    )


def reject_side_backtrack_esc(state: AppInputState) -> None:
    """Rust ``App::reject_side_backtrack_esc`` semantic transition."""

    state.backtrack_primed = False
    assert state.errors is not None
    state.errors.append(SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE)


def request_external_editor_launch(state: AppInputState) -> None:
    """Rust ``App::request_external_editor_launch`` semantic transition."""

    state.external_editor_state = "Requested"
    state.footer_hint_override = [(EXTERNAL_EDITOR_HINT, "")]
    state.frame_requested = True


def reset_external_editor_state(state: AppInputState) -> None:
    """Rust ``App::reset_external_editor_state`` semantic transition."""

    state.external_editor_state = "Closed"
    state.footer_hint_override = None
    state.frame_requested = True


async def launch_external_editor(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("app::input::launch_external_editor requires editor process and TUI restore runtime")


async def handle_key_event(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("app::input::handle_key_event requires full App, TUI, keymap, and AppServer runtime")


async def app_keymap_shortcuts_are_disabled_while_keymap_view_is_active(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("Rust async test harness boundary; use app_keymap_shortcuts_available")


__all__ = [
    "EXTERNAL_EDITOR_HINT",
    "RUST_MODULE",
    "SIDE_EDIT_PREVIOUS_UNAVAILABLE_MESSAGE",
    "AppInputState",
    "app_keymap_shortcuts_are_disabled_while_keymap_view_is_active",
    "app_keymap_shortcuts_available",
    "handle_key_event",
    "launch_external_editor",
    "reject_side_backtrack_esc",
    "request_external_editor_launch",
    "reset_external_editor_state",
    "should_handle_backtrack_esc",
    "should_reject_side_backtrack_esc",
]