from __future__ import annotations

from pycodex.tui.key_hint import KeyEvent, MOD_CONTROL, MOD_SHIFT
from pycodex.tui.onboarding.auth import (
    API_KEY_DISABLED_MESSAGE,
    AccountLoginCompletedNotification,
    AccountUpdatedNotification,
    ApiKeyInputState,
    AuthModeWidget,
    ContinueInBrowserState,
    ContinueWithDeviceCodeState,
    SignInOption,
    SignInState,
    StepState,
    cancel_login_attempt,
    mark_underlined_hyperlink,
    mark_url_hyperlink,
    maybe_open_auth_url_in_browser,
)


def test_device_code_state_pending_ready_and_copyable_auth() -> None:
    # Rust: ContinueWithDeviceCodeState::pending/ready/login_id/is_showing_copyable_auth.
    pending = ContinueWithDeviceCodeState.pending("request-1")
    ready = ContinueWithDeviceCodeState.ready("request-1", "login-1", "https://chatgpt.com/device", "ABCD")

    assert pending.login_id() is None
    assert pending.is_showing_copyable_auth() is False
    assert ready.login_id() == "login-1"
    assert ready.is_showing_copyable_auth() is True


def test_forced_chatgpt_disables_api_key_flow_matches_rust_tests() -> None:
    # Rust: api_key_flow_disabled_when_chatgpt_forced and saving_api_key_is_blocked_when_chatgpt_forced.
    widget = AuthModeWidget(forced_login_method="chatgpt")
    widget.start_api_key_entry()

    assert widget.error_message() == API_KEY_DISABLED_MESSAGE
    assert widget.sign_in_state == SignInState.pick_mode()

    widget.save_api_key("sk-test")
    assert widget.error_message() == API_KEY_DISABLED_MESSAGE
    assert widget.sign_in_state == SignInState.pick_mode()
    assert widget.login_status == "not_authenticated"


def test_existing_chatgpt_auth_tokens_counts_as_signed_in_matches_rust() -> None:
    # Rust: existing_chatgpt_auth_tokens_login_counts_as_signed_in.
    widget = AuthModeWidget(forced_login_method="chatgpt", login_status="chatgpt_auth_tokens")

    assert widget.handle_existing_chatgpt_login() is True
    assert widget.sign_in_state == SignInState.chatgpt_success()
    assert widget.request_frame.scheduled == 1


def test_cancel_active_attempt_resets_browser_and_device_code_state() -> None:
    # Rust: cancel_active_attempt_resets_browser_login_state / notifies_device_code_login.
    widget = AuthModeWidget(error="still logging in")
    widget.sign_in_state = SignInState.chatgpt_continue_in_browser(ContinueInBrowserState("login-1", "https://auth.example.com"))
    widget.cancel_active_attempt()

    assert widget.cancelled_login_ids == ["login-1"]
    assert widget.error_message() is None
    assert widget.sign_in_state == SignInState.pick_mode()

    widget.error = "still logging in"
    widget.sign_in_state = SignInState.chatgpt_device_code(ContinueWithDeviceCodeState.ready("request-1", "login-2", "https://chatgpt.com/device", "ABCD"))
    widget.cancel_active_attempt()
    assert widget.cancelled_login_ids[-1] == "login-2"
    assert widget.sign_in_state == SignInState.pick_mode()


def test_option_lists_highlight_and_shortcut_selection_respect_forced_methods() -> None:
    # Rust: displayed/selectable options, move_highlight, select_option_by_index, fixed onboarding keys.
    widget = AuthModeWidget(forced_login_method="api")
    assert widget.displayed_sign_in_options() == [SignInOption.CHATGPT, SignInOption.API_KEY]
    assert widget.selectable_sign_in_options() == [SignInOption.API_KEY]
    widget.move_highlight(1)
    assert widget.highlighted_mode == SignInOption.API_KEY

    widget.select_option_by_index(1)
    assert widget.sign_in_state.kind == "api_key_entry"

    widget = AuthModeWidget()
    widget.handle_key_event(KeyEvent.new("2"))
    assert widget.login_requests == [("device_code", None)]


def test_api_key_entry_key_and_paste_semantics() -> None:
    # Rust: API-key entry mode consumes text/backspace/paste and Enter saves.
    widget = AuthModeWidget()
    widget.start_api_key_entry("sk-")
    assert widget.is_api_key_entry_active() is True
    assert widget.api_key_entry_has_text() is True

    widget.handle_key_event(KeyEvent.new("t"))
    widget.handle_key_event(KeyEvent.new("x", {MOD_CONTROL}))
    widget.handle_paste("est")
    widget.handle_key_event(KeyEvent.new("Backspace"))
    assert widget.sign_in_state.payload == ApiKeyInputState("sk-tes", False)
    widget.handle_key_event(KeyEvent.new("Enter"))
    assert widget.login_requests == [("api_key", "sk-tes")]
    assert widget.sign_in_state == SignInState.api_key_configured()


def test_login_completion_and_account_updates_match_current_state_only() -> None:
    # Rust: on_account_login_completed ignores non-matching login ids and advances matching successes/errors.
    widget = AuthModeWidget()
    widget.sign_in_state = SignInState.chatgpt_device_code(ContinueWithDeviceCodeState.ready("request-1", "login-1", "url", "code"))
    widget.on_account_login_completed(AccountLoginCompletedNotification("other", True))
    assert widget.sign_in_state.kind == "chatgpt_device_code"

    widget.on_account_login_completed(AccountLoginCompletedNotification("login-1", True))
    assert widget.sign_in_state == SignInState.chatgpt_success_message()
    widget.handle_key_event(KeyEvent.new("Enter"))
    assert widget.sign_in_state == SignInState.chatgpt_success()

    widget.on_account_updated(AccountUpdatedNotification("chatgpt"))
    assert widget.login_status == "chatgpt"


def test_step_state_and_animation_suppression() -> None:
    # Rust: StepStateProvider and should_suppress_animations while browser/device-code flow is visible.
    widget = AuthModeWidget()
    assert widget.get_step_state() == StepState.IN_PROGRESS
    widget.sign_in_state = SignInState.chatgpt_device_code(ContinueWithDeviceCodeState.pending("request-1"))
    assert widget.should_suppress_animations() is True
    widget.sign_in_state = SignInState.api_key_configured()
    assert widget.get_step_state() == StepState.COMPLETE


def test_hyperlink_marking_and_sanitization_semantics() -> None:
    # Rust: mark_url_hyperlink marks cyan+underlined URL cells and strips OSC-breaking controls.
    cells = [
        {"symbol": "a", "fg": "cyan", "underlined": True},
        {"symbol": "b", "fg": "white", "underlined": True},
        {"symbol": "c", "fg": "cyan", "underlined": False},
    ]
    mark_url_hyperlink(cells, None, "https://evil.com/\x1b]8;;\x07injected")
    assert cells[0]["hyperlink"] == "https://evil.com/]8;;injected"
    assert "hyperlink" not in cells[1]
    assert "hyperlink" not in cells[2]

    mark_underlined_hyperlink(cells, None, "https://example.com")
    assert cells[1]["hyperlink"] == "https://example.com"


def test_cancel_request_and_browser_open_boundaries_are_explicit() -> None:
    class Handle:
        kind = "in_process"
        def __init__(self) -> None:
            self.requests = []
            self.opened_urls = []

    handle = Handle()
    assert cancel_login_attempt(handle, "login-1") == {"method": "CancelLoginAccount", "params": {"login_id": "login-1"}}
    assert handle.requests[-1]["params"]["login_id"] == "login-1"
    assert maybe_open_auth_url_in_browser(handle, "https://auth.example.com") is True
    assert handle.opened_urls == ["https://auth.example.com"]
    assert maybe_open_auth_url_in_browser("remote", "https://auth.example.com") is False
