from __future__ import annotations

"""Parity tests for Rust ``codex-tui::bottom_pane::bottom_pane_view``.

Rust source: codex/codex-rs/tui/src/bottom_pane/bottom_pane_view.rs
"""

from pycodex.tui.bottom_pane.bottom_pane_view import (
    BottomPaneView,
    BottomPaneViewDefaults,
    CancellationEvent,
    ViewCompletion,
    active_tab_id,
    clear_dismiss_after_child_accept,
    completion,
    dismiss_after_child_accept,
    dismiss_app_server_request,
    flush_paste_burst_if_due,
    handle_key_event,
    handle_paste,
    is_complete,
    is_in_paste_burst,
    next_frame_delay,
    on_ctrl_c,
    prefer_esc_to_handle_key_event,
    selected_index,
    terminal_lines,
    terminal_title_requires_action,
    try_consume_approval_request,
    try_consume_mcp_server_elicitation_request,
    try_consume_user_input_request,
    view_id,
)


class DefaultView(BottomPaneViewDefaults):
    pass


def test_view_completion_enum_matches_rust_variants() -> None:
    # Rust: ViewCompletion::{Accepted, Cancelled}.
    assert ViewCompletion.ACCEPTED.value == "accepted"
    assert ViewCompletion.CANCELLED.value == "cancelled"


def test_default_bottom_pane_view_completion_and_identity_methods() -> None:
    # Rust: BottomPaneView default completion/selection/view identity methods.
    view = DefaultView()
    assert isinstance(view, BottomPaneView)
    assert is_complete(view) is False
    assert completion(view) is None
    assert dismiss_after_child_accept(view) is False
    assert clear_dismiss_after_child_accept(view) is None
    assert view_id(view) is None
    assert selected_index(view) is None
    assert active_tab_id(view) is None
    assert terminal_lines(view, width=80) == []


def test_default_bottom_pane_view_input_and_paste_methods_are_noops() -> None:
    # Rust: default handle_key_event is no-op; paste/burst hooks return false.
    view = DefaultView()
    assert handle_key_event(view, {"code": "Enter"}) is None
    assert on_ctrl_c(view) is CancellationEvent.NOT_HANDLED
    assert prefer_esc_to_handle_key_event(view) is False
    assert handle_paste(view, "hello") is False
    assert flush_paste_burst_if_due(view) is False
    assert is_in_paste_burst(view) is False


def test_default_request_consumers_return_original_request() -> None:
    # Rust: try_consume_* returns Some(request) when not consumed.
    view = DefaultView()
    approval = {"kind": "approval"}
    user_input = {"kind": "user_input"}
    elicitation = {"kind": "mcp_elicitation"}
    assert try_consume_approval_request(view, approval) is approval
    assert try_consume_user_input_request(view, user_input) is user_input
    assert try_consume_mcp_server_elicitation_request(view, elicitation) is elicitation


def test_default_external_refresh_and_terminal_title_methods() -> None:
    # Rust: dismiss_app_server_request/terminal_title_requires_action/next_frame_delay defaults.
    view = DefaultView()
    assert dismiss_app_server_request(view, {"request_id": "r1"}) is False
    assert terminal_title_requires_action(view) is False
    assert next_frame_delay(view) is None


def test_override_methods_can_express_view_specific_behavior() -> None:
    class CustomView(BottomPaneViewDefaults):
        def is_complete(self) -> bool:
            return True

        def completion(self) -> ViewCompletion | None:
            return ViewCompletion.ACCEPTED

        def try_consume_approval_request(self, request):
            return None

    view = CustomView()
    assert is_complete(view) is True
    assert completion(view) is ViewCompletion.ACCEPTED
    assert try_consume_approval_request(view, object()) is None
