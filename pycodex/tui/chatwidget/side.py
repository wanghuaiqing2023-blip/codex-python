"""Semantic port of codex-rs/tui/src/chatwidget/side.rs.

Rust implements these methods on ``ChatWidget``.  Python keeps them as
widget-like helpers so this module owns only the side-conversation chat-surface
contract, not the full ChatWidget implementation.
"""

from __future__ import annotations

from typing import Any

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::side",
    source="codex/codex-rs/tui/src/chatwidget/side.rs",
)

SHELL_ESCAPE_POLICY_DISALLOW = "Disallow"


def submit_user_message_as_plain_user_turn(widget: Any, user_message: Any) -> Any:
    """Submit a user message with shell escapes explicitly disallowed."""

    submit = getattr(widget, "submit_user_message_with_shell_escape_policy", None)
    if submit is None:
        raise AttributeError(
            "widget must provide submit_user_message_with_shell_escape_policy"
        )
    return submit(user_message, SHELL_ESCAPE_POLICY_DISALLOW)


def set_side_conversation_active(widget: Any, active: bool) -> None:
    """Toggle side-conversation chat-surface state and placeholder text."""

    is_active = bool(active)
    setattr(widget, "active_side_conversation", is_active)
    placeholder_attr = "side_placeholder_text" if is_active else "normal_placeholder_text"
    placeholder = getattr(widget, placeholder_attr)
    bottom_pane = getattr(widget, "bottom_pane")
    bottom_pane.set_placeholder_text(placeholder)
    bottom_pane.set_side_conversation_active(is_active)


def side_conversation_active(widget: Any) -> bool:
    return bool(getattr(widget, "active_side_conversation", False))


def set_side_conversation_context_label(widget: Any, label: str | None) -> None:
    bottom_pane = getattr(widget, "bottom_pane")
    bottom_pane.set_side_conversation_context_label(label)


class SideConversationMixin:
    """Mixin shape matching the Rust ``impl ChatWidget`` methods."""

    def submit_user_message_as_plain_user_turn(self, user_message: Any) -> Any:
        return submit_user_message_as_plain_user_turn(self, user_message)

    def set_side_conversation_active(self, active: bool) -> None:
        set_side_conversation_active(self, active)

    def side_conversation_active(self) -> bool:
        return side_conversation_active(self)

    def set_side_conversation_context_label(self, label: str | None) -> None:
        set_side_conversation_context_label(self, label)


__all__ = [
    "RUST_MODULE",
    "SHELL_ESCAPE_POLICY_DISALLOW",
    "SideConversationMixin",
    "set_side_conversation_active",
    "set_side_conversation_context_label",
    "side_conversation_active",
    "submit_user_message_as_plain_user_turn",
]
