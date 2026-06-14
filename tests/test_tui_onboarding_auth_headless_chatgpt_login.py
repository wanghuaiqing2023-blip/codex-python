from __future__ import annotations

from pycodex.tui.onboarding.auth import AuthModeWidget, ContinueWithDeviceCodeState, FrameRequester, SignInState
from pycodex.tui.onboarding.auth.headless_chatgpt_login import (
    LoginAccountRequest,
    apply_device_code_error,
    apply_device_code_response,
    device_code_attempt_matches,
    pending_device_code_state,
    render_device_code_login,
    set_device_code_error_for_active_attempt,
    set_device_code_state_for_active_attempt,
    start_headless_chatgpt_login,
)


def test_device_code_attempt_matches_only_for_matching_request_id() -> None:
    # Rust: device_code_attempt_matches_only_for_matching_request_id.
    state = pending_device_code_state("request-1")

    assert device_code_attempt_matches(state, "request-1") is True
    assert device_code_attempt_matches(state, "request-2") is False
    assert device_code_attempt_matches(SignInState.pick_mode(), "request-1") is False


def test_set_device_code_state_for_active_attempt_updates_only_when_active() -> None:
    # Rust: set_device_code_state_for_active_attempt_updates_only_when_active.
    frame = FrameRequester()
    state = pending_device_code_state("request-1")
    ready = ContinueWithDeviceCodeState.ready("request-1", "login-1", "https://example.com/device", "ABCD-EFGH")

    updated, next_state = set_device_code_state_for_active_attempt(state, frame, "request-1", ready)

    assert updated is True
    assert next_state.kind == "chatgpt_device_code"
    assert next_state.payload.login_id() == "login-1"
    assert frame.scheduled == 1

    other_state = pending_device_code_state("request-2")
    updated, unchanged = set_device_code_state_for_active_attempt(other_state, frame, "request-1", ready)
    assert updated is False
    assert unchanged == other_state
    assert unchanged.payload.login_id() is None


def test_set_device_code_error_for_active_attempt_updates_only_when_active() -> None:
    # Rust: set_device_code_error_for_active_attempt_updates_only_when_active.
    frame = FrameRequester()
    error = {"message": None}
    state = pending_device_code_state("request-1")

    updated, next_state = set_device_code_error_for_active_attempt(state, frame, error, "request-1", "device code unavailable")

    assert updated is True
    assert next_state == SignInState.pick_mode()
    assert error["message"] == "device code unavailable"

    error = {"message": None}
    other_state = pending_device_code_state("request-2")
    updated, unchanged = set_device_code_error_for_active_attempt(other_state, frame, error, "request-1", "device code unavailable")
    assert updated is False
    assert unchanged == other_state
    assert error["message"] is None


def test_start_headless_chatgpt_login_sets_pending_and_records_request() -> None:
    # Rust: start_headless_chatgpt_login sets pending state and sends LoginAccount ChatgptDeviceCode.
    class Handle:
        def __init__(self) -> None:
            self.requests = []

    handle = Handle()
    widget = AuthModeWidget(app_server_request_handle=handle)
    request = start_headless_chatgpt_login(widget, request_id="request-1")

    assert request == LoginAccountRequest("request-1")
    assert handle.requests == [request]
    assert widget.sign_in_state == pending_device_code_state("request-1")
    assert widget.request_frame.scheduled == 1


def test_apply_device_code_response_updates_or_cancels_stale_attempt() -> None:
    # Rust spawned response branch updates matching attempt, otherwise cancels returned login id.
    widget = AuthModeWidget()
    widget.sign_in_state = pending_device_code_state("request-1")
    response = {"login_id": "login-1", "verification_url": "https://example.com/device", "user_code": "ABCD"}

    assert apply_device_code_response(widget, "request-1", response) is True
    assert widget.error is None
    assert widget.sign_in_state.payload.login_id() == "login-1"

    stale = AuthModeWidget()
    stale.sign_in_state = pending_device_code_state("request-2")
    assert apply_device_code_response(stale, "request-1", response) is False
    assert stale.cancelled_login_ids == ["login-1"]


def test_apply_device_code_error_sets_pick_mode_only_for_active_attempt() -> None:
    widget = AuthModeWidget()
    widget.sign_in_state = pending_device_code_state("request-1")
    assert apply_device_code_error(widget, "request-1", "boom") is True
    assert widget.sign_in_state == SignInState.pick_mode()
    assert widget.error == "boom"

    stale = AuthModeWidget()
    stale.sign_in_state = pending_device_code_state("request-2")
    assert apply_device_code_error(stale, "request-1", "boom") is False
    assert stale.sign_in_state == pending_device_code_state("request-2")
    assert stale.error is None


def test_render_device_code_login_pending_and_ready_semantics() -> None:
    # Rust: render_device_code_login switches banner/content and marks ready verification URL as hyperlink.
    widget = AuthModeWidget(animations_enabled=True)
    pending_buf: list[object] = []
    pending_lines = render_device_code_login(widget, None, pending_buf, ContinueWithDeviceCodeState.pending("request-1"))
    assert pending_lines[0] == "Preparing device code login"
    assert "Requesting a one-time code..." in pending_lines
    assert widget.request_frame.scheduled == 1

    ready_state = ContinueWithDeviceCodeState.ready("request-1", "login-1", "https://example.com/device", "ABCD-EFGH")
    cells = [{"symbol": "x", "fg": "cyan", "underlined": True}]
    ready_lines = render_device_code_login(widget, None, cells, ready_state)
    assert ready_lines[0] == "Finish signing in via your browser"
    assert "https://example.com/device" in ready_lines
    assert "ABCD-EFGH" in ready_lines
    assert cells[0]["hyperlink"] == "https://example.com/device"


def test_render_device_code_login_suppressed_animation_does_not_schedule_frame() -> None:
    widget = AuthModeWidget(animations_enabled=True, animations_suppressed=True)
    render_device_code_login(widget, None, [], ContinueWithDeviceCodeState.pending("request-1"))
    assert widget.request_frame.scheduled == 0
