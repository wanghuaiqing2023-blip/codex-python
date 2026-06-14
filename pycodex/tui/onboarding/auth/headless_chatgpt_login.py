"""Behavior port for Rust ``onboarding::auth::headless_chatgpt_login``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ..._porting import RustTuiModule
from . import AuthModeWidget, ContinueWithDeviceCodeState, SignInState, mark_url_hyperlink

RUST_MODULE = RustTuiModule(crate="codex-tui", module="onboarding::auth::headless_chatgpt_login", source="codex/codex-rs/tui/src/onboarding/auth/headless_chatgpt_login.rs")


@dataclass(frozen=True)
class LoginAccountRequest:
    request_id: str
    params: str = "ChatgptDeviceCode"


def start_headless_chatgpt_login(widget: AuthModeWidget, request_id: str | None = None) -> LoginAccountRequest:
    request_id = request_id or str(uuid4())
    widget.sign_in_state = SignInState.chatgpt_device_code(ContinueWithDeviceCodeState.pending(request_id))
    widget.request_frame.schedule_frame()
    request = LoginAccountRequest(request_id=request_id)
    if hasattr(widget.app_server_request_handle, "requests"):
        widget.app_server_request_handle.requests.append(request)
    return request


def render_device_code_login(widget: AuthModeWidget, area: Any, buf: Any, state: ContinueWithDeviceCodeState) -> list[str]:
    banner = "Finish signing in via your browser" if state.is_showing_copyable_auth() else "Preparing device code login"
    if widget.animations_enabled and not widget.animations_suppressed:
        widget.request_frame.schedule_frame_in(0.1)
    lines = [banner, ""]
    verification_url = None
    if state.verification_url is not None and state.user_code is not None:
        verification_url = state.verification_url
        lines.extend([
            "1. Open this link in your browser and sign in",
            verification_url,
            "2. Enter this one-time code after you are signed in (expires in 15 minutes)",
            state.user_code,
            "Device codes are a common phishing target. Never share this code.",
            "",
        ])
    else:
        lines.extend(["Requesting a one-time code...", ""])
    lines.append("Press Esc to cancel")
    if isinstance(buf, list):
        buf.extend(lines)
    if verification_url is not None:
        mark_url_hyperlink(buf, area, verification_url)
    return lines


def device_code_attempt_matches(state: SignInState, request_id: str) -> bool:
    return state.kind == "chatgpt_device_code" and state.payload.request_id == request_id


def set_device_code_state_for_active_attempt(
    sign_in_state: SignInState,
    request_frame: Any,
    request_id: str,
    next_state: ContinueWithDeviceCodeState,
) -> tuple[bool, SignInState]:
    if not device_code_attempt_matches(sign_in_state, request_id):
        return False, sign_in_state
    if hasattr(request_frame, "schedule_frame"):
        request_frame.schedule_frame()
    return True, SignInState.chatgpt_device_code(next_state)


def set_device_code_error_for_active_attempt(
    sign_in_state: SignInState,
    request_frame: Any,
    error: dict[str, str | None] | Any,
    request_id: str,
    message: str,
) -> tuple[bool, SignInState]:
    if not device_code_attempt_matches(sign_in_state, request_id):
        return False, sign_in_state
    if isinstance(error, dict):
        error["message"] = message
    elif hasattr(error, "message"):
        error.message = message
    if hasattr(request_frame, "schedule_frame"):
        request_frame.schedule_frame()
    return True, SignInState.pick_mode()


def apply_device_code_response(widget: AuthModeWidget, request_id: str, response: Any) -> bool:
    """Synchronous semantic helper for Rust's spawned LoginAccount response branch."""

    ready = ContinueWithDeviceCodeState.ready(
        request_id,
        _get(response, "login_id"),
        _get(response, "verification_url"),
        _get(response, "user_code"),
    )
    updated, next_state = set_device_code_state_for_active_attempt(widget.sign_in_state, widget.request_frame, request_id, ready)
    if updated:
        widget.sign_in_state = next_state
        widget.error = None
    else:
        login_id = ready.login_id()
        if login_id:
            widget.cancelled_login_ids.append(login_id)
    return updated


def apply_device_code_error(widget: AuthModeWidget, request_id: str, message: str) -> bool:
    error: dict[str, str | None] = {"message": widget.error}
    updated, next_state = set_device_code_error_for_active_attempt(widget.sign_in_state, widget.request_frame, error, request_id, message)
    if updated:
        widget.sign_in_state = next_state
        widget.error = error["message"]
    return updated


def pending_device_code_state(request_id: str) -> SignInState:
    return SignInState.chatgpt_device_code(ContinueWithDeviceCodeState.pending(request_id))


def _get(value: Any, key: str) -> str:
    if isinstance(value, dict):
        return str(value[key])
    return str(getattr(value, key))


__all__ = [
    "LoginAccountRequest",
    "RUST_MODULE",
    "apply_device_code_error",
    "apply_device_code_response",
    "device_code_attempt_matches",
    "pending_device_code_state",
    "render_device_code_login",
    "set_device_code_error_for_active_attempt",
    "set_device_code_state_for_active_attempt",
    "start_headless_chatgpt_login",
]
