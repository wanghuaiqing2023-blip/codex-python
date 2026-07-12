"""Behavior port for Rust ``codex-tui::bottom_pane::bottom_pane_view``.

Rust defines a trait with default no-op behavior for bottom-pane views.  Python
uses a Protocol for structural typing plus a mixin that provides those Rust
trait defaults for semantic view implementations.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .._porting import RustTuiModule
from .selection_popup_common import TerminalPopupLine

RUST_MODULE = RustTuiModule(crate="codex-tui", module="bottom_pane::bottom_pane_view", source="codex/codex-rs/tui/src/bottom_pane/bottom_pane_view.rs")


class ViewCompletion(Enum):
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"


class CancellationEvent(Enum):
    NOT_HANDLED = "not_handled"
    HANDLED = "handled"


@runtime_checkable
class BottomPaneView(Protocol):
    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]: ...
    def handle_key_event(self, key_event: Any) -> None: ...
    def is_complete(self) -> bool: ...
    def completion(self) -> ViewCompletion | None: ...
    def dismiss_after_child_accept(self) -> bool: ...
    def clear_dismiss_after_child_accept(self) -> None: ...
    def view_id(self) -> str | None: ...
    def selected_index(self) -> int | None: ...
    def active_tab_id(self) -> str | None: ...
    def on_ctrl_c(self) -> CancellationEvent: ...
    def prefer_esc_to_handle_key_event(self) -> bool: ...
    def handle_paste(self, pasted: str) -> bool: ...
    def flush_paste_burst_if_due(self) -> bool: ...
    def is_in_paste_burst(self) -> bool: ...
    def try_consume_approval_request(self, request: Any) -> Any | None: ...
    def try_consume_user_input_request(self, request: Any) -> Any | None: ...
    def try_consume_mcp_server_elicitation_request(self, request: Any) -> Any | None: ...
    def dismiss_app_server_request(self, request: Any) -> bool: ...
    def terminal_title_requires_action(self) -> bool: ...
    def next_frame_delay(self) -> float | None: ...


class BottomPaneViewDefaults:
    """Mixin implementing Rust ``BottomPaneView`` default methods."""

    def terminal_lines(self, *, width: int) -> list[TerminalPopupLine]:
        return []

    def handle_key_event(self, _key_event: Any) -> None:
        return None

    def is_complete(self) -> bool:
        return False

    def completion(self) -> ViewCompletion | None:
        return None

    def dismiss_after_child_accept(self) -> bool:
        return False

    def clear_dismiss_after_child_accept(self) -> None:
        return None

    def view_id(self) -> str | None:
        return None

    def selected_index(self) -> int | None:
        return None

    def active_tab_id(self) -> str | None:
        return None

    def on_ctrl_c(self) -> CancellationEvent:
        return CancellationEvent.NOT_HANDLED

    def prefer_esc_to_handle_key_event(self) -> bool:
        return False

    def handle_paste(self, _pasted: str) -> bool:
        return False

    def flush_paste_burst_if_due(self) -> bool:
        return False

    def is_in_paste_burst(self) -> bool:
        return False

    def try_consume_approval_request(self, request: Any) -> Any | None:
        return request

    def try_consume_user_input_request(self, request: Any) -> Any | None:
        return request

    def try_consume_mcp_server_elicitation_request(self, request: Any) -> Any | None:
        return request

    def dismiss_app_server_request(self, _request: Any) -> bool:
        return False

    def terminal_title_requires_action(self) -> bool:
        return False

    def next_frame_delay(self) -> float | None:
        return None


# Free-function helpers mirror calling the Rust trait defaults against a view.
def terminal_lines(view: BottomPaneView, *, width: int) -> list[TerminalPopupLine]:
    return list(view.terminal_lines(width=width))


def handle_key_event(view: BottomPaneView, key_event: Any) -> None:
    return view.handle_key_event(key_event)


def is_complete(view: BottomPaneView) -> bool:
    return view.is_complete()


def completion(view: BottomPaneView) -> ViewCompletion | None:
    return view.completion()


def dismiss_after_child_accept(view: BottomPaneView) -> bool:
    return view.dismiss_after_child_accept()


def clear_dismiss_after_child_accept(view: BottomPaneView) -> None:
    return view.clear_dismiss_after_child_accept()


def view_id(view: BottomPaneView) -> str | None:
    return view.view_id()


def selected_index(view: BottomPaneView) -> int | None:
    return view.selected_index()


def active_tab_id(view: BottomPaneView) -> str | None:
    return view.active_tab_id()


def on_ctrl_c(view: BottomPaneView) -> CancellationEvent:
    return view.on_ctrl_c()


def prefer_esc_to_handle_key_event(view: BottomPaneView) -> bool:
    return view.prefer_esc_to_handle_key_event()


def handle_paste(view: BottomPaneView, pasted: str) -> bool:
    return view.handle_paste(pasted)


def flush_paste_burst_if_due(view: BottomPaneView) -> bool:
    return view.flush_paste_burst_if_due()


def is_in_paste_burst(view: BottomPaneView) -> bool:
    return view.is_in_paste_burst()


def try_consume_approval_request(view: BottomPaneView, request: Any) -> Any | None:
    return view.try_consume_approval_request(request)


def try_consume_user_input_request(view: BottomPaneView, request: Any) -> Any | None:
    return view.try_consume_user_input_request(request)


def try_consume_mcp_server_elicitation_request(view: BottomPaneView, request: Any) -> Any | None:
    return view.try_consume_mcp_server_elicitation_request(request)


def dismiss_app_server_request(view: BottomPaneView, request: Any) -> bool:
    return view.dismiss_app_server_request(request)


def terminal_title_requires_action(view: BottomPaneView) -> bool:
    method = getattr(view, "terminal_title_requires_action", None)
    return bool(method()) if callable(method) else False


def next_frame_delay(view: BottomPaneView) -> float | None:
    return view.next_frame_delay()


__all__ = [
    "BottomPaneView",
    "BottomPaneViewDefaults",
    "CancellationEvent",
    "RUST_MODULE",
    "ViewCompletion",
    "active_tab_id",
    "clear_dismiss_after_child_accept",
    "completion",
    "dismiss_after_child_accept",
    "dismiss_app_server_request",
    "flush_paste_burst_if_due",
    "handle_key_event",
    "handle_paste",
    "is_complete",
    "is_in_paste_burst",
    "next_frame_delay",
    "on_ctrl_c",
    "prefer_esc_to_handle_key_event",
    "selected_index",
    "terminal_lines",
    "terminal_title_requires_action",
    "try_consume_approval_request",
    "try_consume_mcp_server_elicitation_request",
    "try_consume_user_input_request",
    "view_id",
]
