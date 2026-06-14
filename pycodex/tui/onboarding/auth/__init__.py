"""Semantic slice for Rust ``codex-tui::onboarding::auth``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..._porting import RustTuiModule
from ...key_hint import KeyEvent, is_pressed
from .. import keys

RUST_MODULE = RustTuiModule(crate="codex-tui", module="onboarding::auth", source="codex/codex-rs/tui/src/onboarding/auth.rs")

API_KEY_DISABLED_MESSAGE = "API key login is disabled."


class SignInOption(Enum):
    CHATGPT = "chatgpt"
    DEVICE_CODE = "device_code"
    API_KEY = "api_key"


class StepState(Enum):
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"


@dataclass(frozen=True)
class ApiKeyInputState:
    value: str = ""
    prepopulated_from_env: bool = False


@dataclass(frozen=True)
class ContinueInBrowserState:
    login_id: str
    auth_url: str


@dataclass(frozen=True)
class ContinueWithDeviceCodeState:
    request_id: str
    login_id_value: str | None = None
    verification_url: str | None = None
    user_code: str | None = None

    @classmethod
    def pending(cls, request_id: str) -> "ContinueWithDeviceCodeState":
        return cls(request_id=str(request_id))

    @classmethod
    def ready(cls, request_id: str, login_id: str, verification_url: str, user_code: str) -> "ContinueWithDeviceCodeState":
        return cls(str(request_id), str(login_id), str(verification_url), str(user_code))

    def login_id(self) -> str | None:
        return self.login_id_value

    def is_showing_copyable_auth(self) -> bool:
        return bool(self.verification_url) and bool(self.user_code)


@dataclass(frozen=True)
class SignInState:
    kind: str
    payload: Any = None

    @classmethod
    def pick_mode(cls) -> "SignInState":
        return cls("pick_mode")

    @classmethod
    def chatgpt_continue_in_browser(cls, state: ContinueInBrowserState) -> "SignInState":
        return cls("chatgpt_continue_in_browser", state)

    @classmethod
    def chatgpt_device_code(cls, state: ContinueWithDeviceCodeState) -> "SignInState":
        return cls("chatgpt_device_code", state)

    @classmethod
    def chatgpt_success_message(cls) -> "SignInState":
        return cls("chatgpt_success_message")

    @classmethod
    def chatgpt_success(cls) -> "SignInState":
        return cls("chatgpt_success")

    @classmethod
    def api_key_entry(cls, state: ApiKeyInputState | None = None) -> "SignInState":
        return cls("api_key_entry", state or ApiKeyInputState())

    @classmethod
    def api_key_configured(cls) -> "SignInState":
        return cls("api_key_configured")


@dataclass(frozen=True)
class AccountLoginCompletedNotification:
    login_id: str | None
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class AccountUpdatedNotification:
    auth_mode: str | None = None


@dataclass
class FrameRequester:
    scheduled: int = 0

    def schedule_frame(self) -> None:
        self.scheduled += 1

    def schedule_frame_in(self, _delay: float) -> None:
        self.scheduled += 1


@dataclass
class AuthModeWidget:
    request_frame: FrameRequester = field(default_factory=FrameRequester)
    highlighted_mode: SignInOption = SignInOption.CHATGPT
    error: str | None = None
    sign_in_state: SignInState = field(default_factory=SignInState.pick_mode)
    login_status: str = "not_authenticated"
    app_server_request_handle: Any = None
    forced_login_method: str | None = None
    animations_enabled: bool = True
    animations_suppressed: bool = False
    cancelled_login_ids: list[str] = field(default_factory=list)
    login_requests: list[tuple[str, Any]] = field(default_factory=list)

    def set_animations_suppressed(self, suppressed: bool) -> None:
        self.animations_suppressed = bool(suppressed)

    def should_suppress_animations(self) -> bool:
        return self.sign_in_state.kind in {"chatgpt_continue_in_browser", "chatgpt_device_code"}

    def cancel_active_attempt(self) -> None:
        state = self.sign_in_state
        login_id = None
        if state.kind == "chatgpt_continue_in_browser":
            login_id = state.payload.login_id
        elif state.kind == "chatgpt_device_code":
            login_id = state.payload.login_id()
        else:
            return
        if login_id:
            self.cancelled_login_ids.append(login_id)
        self.sign_in_state = SignInState.pick_mode()
        self.set_error(None)
        self.request_frame.schedule_frame()

    def set_error(self, message: str | None) -> None:
        self.error = message

    def error_message(self) -> str | None:
        return self.error

    def is_api_key_entry_active(self) -> bool:
        return self.sign_in_state.kind == "api_key_entry"

    def api_key_entry_has_text(self) -> bool:
        return self.sign_in_state.kind == "api_key_entry" and bool(self.sign_in_state.payload.value)

    def is_api_login_allowed(self) -> bool:
        return self.forced_login_method != "chatgpt"

    def is_chatgpt_login_allowed(self) -> bool:
        return self.forced_login_method != "api"

    def displayed_sign_in_options(self) -> list[SignInOption]:
        options = [SignInOption.CHATGPT]
        if self.is_chatgpt_login_allowed():
            options.append(SignInOption.DEVICE_CODE)
        if self.is_api_login_allowed():
            options.append(SignInOption.API_KEY)
        return options

    def selectable_sign_in_options(self) -> list[SignInOption]:
        options: list[SignInOption] = []
        if self.is_chatgpt_login_allowed():
            options.extend([SignInOption.CHATGPT, SignInOption.DEVICE_CODE])
        if self.is_api_login_allowed():
            options.append(SignInOption.API_KEY)
        return options

    def move_highlight(self, delta: int) -> None:
        options = self.selectable_sign_in_options()
        if not options:
            return
        current = options.index(self.highlighted_mode) if self.highlighted_mode in options else 0
        self.highlighted_mode = options[(current + int(delta)) % len(options)]

    def select_option_by_index(self, index: int) -> None:
        options = self.displayed_sign_in_options()
        if 0 <= int(index) < len(options):
            self.handle_sign_in_option(options[int(index)])

    def handle_sign_in_option(self, option: SignInOption) -> None:
        if option is SignInOption.CHATGPT:
            if self.is_chatgpt_login_allowed():
                self.start_chatgpt_login()
        elif option is SignInOption.DEVICE_CODE:
            if self.is_chatgpt_login_allowed():
                self.start_device_code_login()
        elif option is SignInOption.API_KEY:
            if self.is_api_login_allowed():
                self.start_api_key_entry()
            else:
                self.disallow_api_login()

    def disallow_api_login(self) -> None:
        self.highlighted_mode = SignInOption.CHATGPT
        self.set_error(API_KEY_DISABLED_MESSAGE)
        self.sign_in_state = SignInState.pick_mode()
        self.request_frame.schedule_frame()

    def start_api_key_entry(self, initial: str = "", prepopulated_from_env: bool = False) -> None:
        if not self.is_api_login_allowed():
            self.disallow_api_login()
            return
        self.set_error(None)
        self.sign_in_state = SignInState.api_key_entry(ApiKeyInputState(initial, prepopulated_from_env))
        self.request_frame.schedule_frame()

    def save_api_key(self, api_key: str) -> None:
        if not self.is_api_login_allowed():
            self.disallow_api_login()
            return
        self.set_error(None)
        self.login_requests.append(("api_key", api_key))
        self.sign_in_state = SignInState.api_key_configured()
        self.request_frame.schedule_frame()

    def handle_existing_chatgpt_login(self) -> bool:
        if self.login_status in {"chatgpt", "chatgpt_auth_tokens"}:
            self.sign_in_state = SignInState.chatgpt_success()
            self.request_frame.schedule_frame()
            return True
        return False

    def start_chatgpt_login(self) -> None:
        if self.handle_existing_chatgpt_login():
            return
        self.set_error(None)
        self.login_requests.append(("chatgpt", None))
        self.sign_in_state = SignInState.chatgpt_continue_in_browser(ContinueInBrowserState("pending", ""))
        self.request_frame.schedule_frame()

    def start_device_code_login(self) -> None:
        if self.handle_existing_chatgpt_login():
            return
        self.set_error(None)
        self.login_requests.append(("device_code", None))
        self.sign_in_state = SignInState.chatgpt_device_code(ContinueWithDeviceCodeState.pending("pending"))
        self.request_frame.schedule_frame()

    def handle_api_key_entry_key_event(self, key_event: Any) -> bool:
        if self.sign_in_state.kind != "api_key_entry":
            return False
        code = _event_code(key_event)
        state = self.sign_in_state.payload
        if code == "Enter":
            self.save_api_key(state.value)
        elif code == "Esc":
            self.sign_in_state = SignInState.pick_mode()
            self.request_frame.schedule_frame()
        elif code == "Backspace":
            self.sign_in_state = SignInState.api_key_entry(ApiKeyInputState(state.value[:-1], False))
        elif len(code) == 1 and "control" not in _event_modifiers(key_event):
            self.sign_in_state = SignInState.api_key_entry(ApiKeyInputState(state.value + code, False))
        else:
            return True
        return True

    def handle_api_key_entry_paste(self, pasted: str) -> bool:
        if self.sign_in_state.kind != "api_key_entry":
            return False
        state = self.sign_in_state.payload
        self.sign_in_state = SignInState.api_key_entry(ApiKeyInputState(state.value + str(pasted), False))
        return True

    def handle_key_event(self, key_event: Any) -> None:
        if self.handle_api_key_entry_key_event(key_event):
            return
        if is_pressed(keys.MOVE_UP, key_event):
            self.move_highlight(-1)
        elif is_pressed(keys.MOVE_DOWN, key_event):
            self.move_highlight(1)
        elif is_pressed(keys.SELECT_FIRST, key_event):
            self.select_option_by_index(0)
        elif is_pressed(keys.SELECT_SECOND, key_event):
            self.select_option_by_index(1)
        elif is_pressed(keys.SELECT_THIRD, key_event):
            self.select_option_by_index(2)
        elif is_pressed(keys.CONFIRM, key_event):
            if self.sign_in_state.kind == "pick_mode":
                self.handle_sign_in_option(self.highlighted_mode)
            elif self.sign_in_state.kind == "chatgpt_success_message":
                self.sign_in_state = SignInState.chatgpt_success()
        elif is_pressed(keys.CANCEL, key_event):
            self.cancel_active_attempt()

    def handle_paste(self, pasted: str) -> None:
        self.handle_api_key_entry_paste(pasted)

    def on_account_login_completed(self, notification: AccountLoginCompletedNotification) -> None:
        if notification.login_id is None:
            return
        state = self.sign_in_state
        matching = (
            state.kind == "chatgpt_continue_in_browser" and state.payload.login_id == notification.login_id
        ) or (
            state.kind == "chatgpt_device_code" and state.payload.login_id() == notification.login_id
        )
        if not matching:
            return
        if notification.success:
            self.set_error(None)
            self.sign_in_state = SignInState.chatgpt_success_message()
        else:
            self.set_error(notification.error)
            self.sign_in_state = SignInState.pick_mode()
        self.request_frame.schedule_frame()

    def on_account_updated(self, notification: AccountUpdatedNotification) -> None:
        self.login_status = notification.auth_mode or "not_authenticated"

    def get_step_state(self) -> StepState:
        return StepState.COMPLETE if self.sign_in_state.kind in {"chatgpt_success", "api_key_configured"} else StepState.IN_PROGRESS

    def render_ref(self, _area: Any = None, _buf: Any = None) -> list[str]:
        state = self.sign_in_state.kind
        if state == "pick_mode":
            return self.render_pick_mode()
        if state == "chatgpt_continue_in_browser":
            return self.render_continue_in_browser()
        if state == "chatgpt_device_code":
            return ["Sign in with Device Code"]
        if state == "chatgpt_success_message":
            return ["Signed in with your ChatGPT account", "Press Enter to continue"]
        if state == "chatgpt_success":
            return ["Signed in with ChatGPT"]
        if state == "api_key_entry":
            return ["Enter API key", "*" * len(self.sign_in_state.payload.value)]
        return ["API key configured"]

    def render_pick_mode(self) -> list[str]:
        lines = ["Sign in with ChatGPT to use Codex as part of your paid plan", "or connect an API key for usage-based billing"]
        for index, option in enumerate(self.displayed_sign_in_options(), start=1):
            marker = ">" if option is self.highlighted_mode else " "
            lines.append(f"{marker} {index}. {option.value}")
        if not self.is_api_login_allowed():
            lines.append("API key login is disabled by this workspace. Sign in with ChatGPT to continue.")
        if self.error:
            lines.append(self.error)
        return lines

    def render_continue_in_browser(self) -> list[str]:
        state = self.sign_in_state.payload
        lines = ["Finish signing in via your browser"]
        if state.auth_url:
            lines.append(state.auth_url)
            lines.append("On a remote or headless machine? Press Esc and choose Sign in with Device Code.")
        lines.append("Press Esc to cancel")
        return lines


def cancel_login_attempt(request_handle: Any, login_id: str) -> dict[str, Any]:
    request = {"method": "CancelLoginAccount", "params": {"login_id": str(login_id)}}
    if hasattr(request_handle, "requests"):
        request_handle.requests.append(request)
    return request


def mark_url_hyperlink(buf: Any, area: Any, url: str) -> Any:
    return _mark_hyperlink(buf, area, url, require_cyan_underlined=True)


def mark_underlined_hyperlink(buf: Any, area: Any, url: str) -> Any:
    return _mark_hyperlink(buf, area, url, require_cyan_underlined=False)


def maybe_open_auth_url_in_browser(request_handle: Any, url: str) -> bool:
    if getattr(request_handle, "kind", None) != "in_process" and request_handle != "in_process":
        return False
    opened = getattr(request_handle, "opened_urls", None)
    if isinstance(opened, list):
        opened.append(url)
    return True


def _mark_hyperlink(buf: Any, _area: Any, url: str, require_cyan_underlined: bool) -> Any:
    sanitized = "".join(ch for ch in str(url) if ord(ch) >= 0x20 and ch != "\x7f")
    if isinstance(buf, list):
        for cell in buf:
            underlined = bool(cell.get("underlined") or cell.get("underline"))
            cyan = str(cell.get("fg", "")).lower() == "cyan"
            if underlined and (cyan or not require_cyan_underlined):
                cell["hyperlink"] = sanitized
        return buf
    return {"url": sanitized, "area": _area, "require_cyan_underlined": require_cyan_underlined}


def _event_code(event: Any) -> str:
    if isinstance(event, KeyEvent):
        return event.code
    if isinstance(event, dict):
        code = str(event.get("code", event.get("key", "")))
    else:
        code = str(getattr(event, "code", event))
    mapping = {"enter": "Enter", "esc": "Esc", "escape": "Esc", "backspace": "Backspace"}
    return mapping.get(code.lower(), code)


def _event_modifiers(event: Any) -> frozenset[str]:
    if isinstance(event, KeyEvent):
        return event.modifiers
    if isinstance(event, dict):
        modifiers = event.get("modifiers") or ()
    else:
        modifiers = getattr(event, "modifiers", ())
    return frozenset(str(modifier).lower().replace("ctrl", "control") for modifier in modifiers)


__all__ = [
    "API_KEY_DISABLED_MESSAGE",
    "AccountLoginCompletedNotification",
    "AccountUpdatedNotification",
    "ApiKeyInputState",
    "AuthModeWidget",
    "ContinueInBrowserState",
    "ContinueWithDeviceCodeState",
    "FrameRequester",
    "RUST_MODULE",
    "SignInOption",
    "SignInState",
    "StepState",
    "cancel_login_attempt",
    "mark_underlined_hyperlink",
    "mark_url_hyperlink",
    "maybe_open_auth_url_in_browser",
]
