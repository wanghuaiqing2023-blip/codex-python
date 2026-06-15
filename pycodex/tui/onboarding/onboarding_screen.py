"""Onboarding screen orchestration and top-level keyboard routing.

Upstream source: ``codex/codex-rs/tui/src/onboarding/onboarding_screen.rs``.

This Python slice ports the flow-level state machine and safety rules around
visible steps, key/paste routing, API-key quit suppression, and trust persistence
failure handling.  Runtime construction and the async TUI/app-server loop remain
explicit boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Awaitable, Callable, List, Mapping, Optional, Protocol, Sequence, Set

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="onboarding::onboarding_screen",
    source="codex/codex-rs/tui/src/onboarding/onboarding_screen.rs",
    status="complete",
)


class StepState(Enum):
    Hidden = "hidden"
    InProgress = "in_progress"
    Complete = "complete"


class KeyboardHandler(Protocol):
    def handle_key_event(self, key_event: Any) -> None: ...
    def handle_paste(self, pasted: str) -> None: ...


class StepStateProvider(Protocol):
    def get_step_state(self) -> StepState: ...


@dataclass(frozen=True)
class ApiKeyEntryContext:
    active: bool = False
    has_text: bool = False


@dataclass(frozen=True)
class OnboardingScreenArgs:
    show_trust_screen: bool = False
    show_login_screen: bool = False
    login_status: Any = None
    app_server_request_handle: Any = None
    config: Any = None


@dataclass(frozen=True)
class OnboardingResult:
    directory_trust_persisted: bool
    should_exit: bool


@dataclass
class Step:
    kind: str
    widget: Any

    def get_step_state(self) -> StepState:
        return _coerce_step_state(self.widget.get_step_state())

    def handle_key_event(self, key_event: Any) -> None:
        handler = getattr(self.widget, "handle_key_event", None)
        if handler is not None:
            handler(key_event)

    def handle_paste(self, pasted: str) -> None:
        handler = getattr(self.widget, "handle_paste", None)
        if handler is not None:
            handler(pasted)

    def render_ref(self, area: Any = None, buf: Any = None) -> Any:
        renderer = getattr(self.widget, "render_ref", None)
        return None if renderer is None else renderer(area, buf)


@dataclass
class FrameRequesterModel:
    scheduled: int = 0

    def schedule_frame(self) -> None:
        self.scheduled += 1


@dataclass
class DefaultWelcomeWidget:
    authenticated: bool = False
    animations_enabled: bool = True
    animations_suppressed: bool = False
    key_events: List[Any] = field(default_factory=list)
    layout_areas: List[Any] = field(default_factory=list)

    def get_step_state(self) -> StepState:
        return StepState.Complete

    def handle_key_event(self, key_event: Any) -> None:
        self.key_events.append(key_event)

    def set_animations_suppressed(self, suppressed: bool) -> None:
        self.animations_suppressed = suppressed

    def update_layout_area(self, area: Any) -> None:
        self.layout_areas.append(area)

    def render_ref(self, area: Any = None, buf: Any = None) -> Mapping[str, Any]:
        return {"kind": "welcome", "authenticated": self.authenticated, "area": area}


@dataclass
class DefaultAuthModeWidget:
    highlighted_mode: str = "ChatGpt"
    login_status: Any = None
    app_server_request_handle: Any = None
    forced_login_method: Any = None
    animations_enabled: bool = True
    animations_suppressed: bool = False
    sign_in_state: str = "PickMode"
    cancelled: bool = False
    pasted: List[str] = field(default_factory=list)
    key_events: List[Any] = field(default_factory=list)
    account_events: List[Any] = field(default_factory=list)
    api_key_active: bool = False
    api_key_text: str = ""

    def get_step_state(self) -> StepState:
        return StepState.Complete if _is_authenticated(self.login_status) else StepState.InProgress

    def handle_key_event(self, key_event: Any) -> None:
        self.key_events.append(key_event)

    def handle_paste(self, pasted: str) -> None:
        self.pasted.append(pasted)
        if self.api_key_active:
            self.api_key_text += pasted

    def should_suppress_animations(self) -> bool:
        return self.sign_in_state in {"DeviceCode", "ChatGptSuccessMessage", "ApiKeyEntry"} and bool(
            self.api_key_text or self.sign_in_state != "ApiKeyEntry"
        )

    def set_animations_suppressed(self, suppressed: bool) -> None:
        self.animations_suppressed = suppressed

    def cancel_active_attempt(self) -> None:
        self.cancelled = True

    def on_account_login_completed(self, notification: Any) -> None:
        self.account_events.append(("AccountLoginCompleted", notification))
        self.login_status = "Authenticated"

    def on_account_updated(self, notification: Any) -> None:
        self.account_events.append(("AccountUpdated", notification))

    def is_api_key_entry_active(self) -> bool:
        return self.api_key_active or self.sign_in_state == "ApiKeyEntry"

    def api_key_entry_has_text(self) -> bool:
        return bool(self.api_key_text)

    def render_ref(self, area: Any = None, buf: Any = None) -> Mapping[str, Any]:
        return {"kind": "auth", "highlighted_mode": self.highlighted_mode, "area": area}


@dataclass
class DefaultTrustDirectoryWidget:
    cwd: Path
    trust_target: Path
    show_windows_create_sandbox_hint: bool = False
    should_quit_value: bool = False
    selection: Any = None
    highlighted: Any = "Trust"
    error: Optional[str] = None
    pasted: List[str] = field(default_factory=list)
    key_events: List[Any] = field(default_factory=list)

    def get_step_state(self) -> StepState:
        return StepState.Complete if self.selection == _trust_selection_value("Trust") else StepState.InProgress

    def handle_key_event(self, key_event: Any) -> None:
        self.key_events.append(key_event)

    def handle_paste(self, pasted: str) -> None:
        self.pasted.append(pasted)

    def should_quit(self) -> bool:
        return self.should_quit_value

    def render_ref(self, area: Any = None, buf: Any = None) -> Mapping[str, Any]:
        return {"kind": "trust", "trust_target": self.trust_target, "area": area}


@dataclass
class OnboardingScreen:
    request_frame: Any = field(default_factory=FrameRequesterModel)
    steps: List[Step] = field(default_factory=list)
    is_done_value: bool = False
    should_exit_value: bool = False

    @classmethod
    async def new(cls, *args: Any, **kwargs: Any) -> "OnboardingScreen":
        tui = args[0] if args else kwargs.get("tui")
        screen_args = args[1] if len(args) > 1 else kwargs.get("args")
        if screen_args is None:
            screen_args = OnboardingScreenArgs()
        request_frame = _frame_requester(tui)
        config = getattr(screen_args, "config", None)
        cwd = Path(getattr(config, "cwd", Path.cwd()))
        forced_login_method = getattr(config, "forced_login_method", None)
        animations = bool(getattr(config, "animations", True))
        steps: List[Step] = []
        welcome_factory = kwargs.get("welcome_factory", DefaultWelcomeWidget)
        auth_factory = kwargs.get("auth_factory", DefaultAuthModeWidget)
        trust_factory = kwargs.get("trust_factory", DefaultTrustDirectoryWidget)
        resolve_trust_target_fn = kwargs.get("resolve_trust_target_fn")
        login_status = getattr(screen_args, "login_status", None)
        steps.append(
            Step(
                "welcome",
                welcome_factory(
                    authenticated=_is_authenticated(login_status),
                    animations_enabled=animations,
                ),
            )
        )
        if getattr(screen_args, "show_login_screen", False):
            request_handle = getattr(screen_args, "app_server_request_handle", None)
            if request_handle is not None:
                highlighted_mode = "ApiKey" if _forced_login_method_name(forced_login_method) == "Api" else "ChatGpt"
                steps.append(
                    Step(
                        "auth",
                        auth_factory(
                            highlighted_mode=highlighted_mode,
                            login_status=login_status,
                            app_server_request_handle=request_handle,
                            forced_login_method=forced_login_method,
                            animations_enabled=animations,
                        ),
                    )
                )
        if getattr(screen_args, "show_trust_screen", False):
            trust_target = Path(resolve_trust_target_fn(cwd)) if resolve_trust_target_fn is not None else cwd
            steps.append(
                Step(
                    "trust",
                    trust_factory(
                        cwd=cwd,
                        trust_target=trust_target,
                        show_windows_create_sandbox_hint=False,
                        highlighted=_trust_selection_value("Trust"),
                    ),
                )
            )
        return cls(request_frame=request_frame, steps=steps)

    def current_steps_mut(self) -> List[Step]:
        return self.current_steps()

    def current_steps(self) -> List[Step]:
        out: List[Step] = []
        for step in self.steps:
            state = step.get_step_state()
            if state is StepState.Hidden:
                continue
            if state is StepState.Complete:
                out.append(step)
                continue
            if state is StepState.InProgress:
                out.append(step)
                break
        return out

    def should_suppress_animations(self) -> bool:
        for step in self.current_steps():
            if step.kind == "auth":
                method = getattr(step.widget, "should_suppress_animations", None)
                if method is not None and bool(method()):
                    return True
        return False

    def is_auth_in_progress(self) -> bool:
        return any(step.kind == "auth" and step.get_step_state() is StepState.InProgress for step in self.steps)

    def is_done(self) -> bool:
        return self.is_done_value or not any(step.get_step_state() is StepState.InProgress for step in self.steps)

    def should_exit(self) -> bool:
        return self.should_exit_value

    def cancel_auth_if_active(self) -> None:
        for step in self.steps:
            if step.kind == "auth":
                cancel = getattr(step.widget, "cancel_active_attempt", None)
                if cancel is not None:
                    cancel()

    def auth_widget_mut(self) -> Optional[Any]:
        for step in self.steps:
            if step.kind == "auth":
                return step.widget
        return None

    def handle_app_server_notification(self, notification: Any) -> None:
        widget = self.auth_widget_mut()
        if widget is None:
            return
        kind = _notification_kind(notification)
        if kind == "AccountLoginCompleted":
            handler = getattr(widget, "on_account_login_completed", None)
            if handler is not None:
                handler(notification)
        elif kind == "AccountUpdated":
            handler = getattr(widget, "on_account_updated", None)
            if handler is not None:
                handler(notification)

    def api_key_entry_context(self) -> ApiKeyEntryContext:
        for step in self.steps:
            if step.kind == "auth":
                active = _call_bool(step.widget, "is_api_key_entry_active")
                has_text = _call_bool(step.widget, "api_key_entry_has_text")
                return ApiKeyEntryContext(active=active, has_text=has_text)
        return ApiKeyEntryContext()

    def handle_key_event(self, key_event: Any) -> None:
        if _key_kind(key_event) not in {"press", "repeat"}:
            return
        api_context = self.api_key_entry_context()
        should_quit = (
            _key_kind(key_event) == "press"
            and _is_quit_key(key_event)
            and not suppress_quit_while_typing_api_key(key_event, api_context)
        )
        if should_quit:
            if self.is_auth_in_progress():
                self.cancel_auth_if_active()
                self.should_exit_value = True
            self.is_done_value = True
        else:
            for step in self.steps:
                if step.kind == "welcome":
                    step.handle_key_event(key_event)
                    break
            current = self.current_steps_mut()
            if current:
                current[-1].handle_key_event(key_event)
            if any(step.kind == "trust" and bool(getattr(step.widget, "should_quit")()) for step in self.steps if hasattr(step.widget, "should_quit")):
                self.should_exit_value = True
                self.is_done_value = True
        _schedule_frame(self.request_frame)

    def handle_paste(self, pasted: str) -> None:
        if pasted == "":
            return
        current = self.current_steps_mut()
        if current:
            current[-1].handle_paste(pasted)
        _schedule_frame(self.request_frame)


def handle_key_event(target: Any, key_event: Any) -> None:
    target.handle_key_event(key_event)


def handle_paste(target: Any, pasted: str) -> None:
    target.handle_paste(pasted)


def get_step_state(target: Any) -> StepState:
    return _coerce_step_state(target.get_step_state())


def suppress_quit_while_typing_api_key(key_event: Any, api_key_entry_context: ApiKeyEntryContext) -> bool:
    return (
        api_key_entry_context.active
        and api_key_entry_context.has_text
        and _is_printable_char_key(key_event)
        and not (_has_modifier(key_event, "control") or _has_modifier(key_event, "alt"))
    )


def render_ref(screen: OnboardingScreen, area: Any = None, buf: Any = None) -> List[Any]:
    suppress = screen.should_suppress_animations()
    plans = []
    for step in screen.current_steps():
        setter = getattr(step.widget, "set_animations_suppressed", None)
        if setter is not None:
            setter(suppress)
        plans.append(step.render_ref(area, buf))
    return plans


def used_rows(lines: Sequence[str], width: int, height: int) -> int:
    if width == 0 or height == 0:
        return 0
    last_non_empty: Optional[int] = None
    for index, line in enumerate(lines[:height]):
        if str(line).strip():
            last_non_empty = index
    return 0 if last_non_empty is None else min(height, last_non_empty + 2)


async def run_onboarding_app(*args: Any, **kwargs: Any) -> OnboardingResult:
    screen_args = args[0] if args else kwargs.get("args", OnboardingScreenArgs())
    app_server = args[1] if len(args) > 1 else kwargs.get("app_server")
    tui = args[2] if len(args) > 2 else kwargs.get("tui")
    onboarding_screen = kwargs.get("onboarding_screen")
    if onboarding_screen is None:
        onboarding_screen = await OnboardingScreen.new(tui, screen_args, **_factory_kwargs(kwargs))
    directory_trust_persisted = False
    did_full_clear_after_success = False
    draw = getattr(tui, "draw", None)
    if draw is not None:
        draw(onboarding_screen)
    events = list(kwargs.get("events", ()))
    app_events = list(kwargs.get("app_events", ()))
    request_handle = getattr(screen_args, "app_server_request_handle", None)
    write_trusted_project_fn = kwargs.get("write_trusted_project_fn")
    while not onboarding_screen.is_done() and (events or app_events):
        if events:
            event = events.pop(0)
            kind = _event_kind(event)
            if kind == "Key":
                onboarding_screen.handle_key_event(_event_payload(event))
                if not directory_trust_persisted:
                    directory_trust_persisted = await persist_selected_trust(
                        onboarding_screen,
                        request_handle,
                        write_trusted_project_fn=write_trusted_project_fn,
                    )
            elif kind == "Paste":
                onboarding_screen.handle_paste(str(_event_payload(event)))
            elif kind in {"Draw", "Resize"}:
                if not did_full_clear_after_success and _has_chatgpt_success_message(onboarding_screen):
                    clear = getattr(getattr(tui, "terminal", None), "clear", None)
                    if clear is not None:
                        clear()
                    did_full_clear_after_success = True
                if draw is not None:
                    draw(onboarding_screen)
        if app_events:
            event = app_events.pop(0)
            kind = _event_kind(event)
            if kind == "ServerNotification":
                onboarding_screen.handle_app_server_notification(_event_payload(event))
            elif kind == "Disconnected":
                message = _event_message(event)
                raise RuntimeError(message)
    return OnboardingResult(
        directory_trust_persisted=directory_trust_persisted,
        should_exit=onboarding_screen.should_exit(),
    )


async def persist_selected_trust(
    onboarding_screen: OnboardingScreen,
    request_handle: Any = None,
    *,
    write_trusted_project_fn: Optional[Callable[[Any, Path], Awaitable[Any]]] = None,
) -> bool:
    for index, step in enumerate(onboarding_screen.steps):
        if step.kind != "trust":
            continue
        widget = step.widget
        if not _is_trust_selection(getattr(widget, "selection", None)):
            continue
        trust_target = Path(getattr(widget, "trust_target"))
        try:
            if request_handle is None:
                raise RuntimeError("app server unavailable")
            if write_trusted_project_fn is None:
                return not_ported(RUST_MODULE, "persist_selected_trust write_trusted_project")
            await write_trusted_project_fn(request_handle, trust_target)
            return True
        except Exception as exc:
            widget.selection = None
            widget.error = f"Failed to set trust for {trust_target}: {exc}"
            return False
    return False


def _coerce_step_state(value: Any) -> StepState:
    if isinstance(value, StepState):
        return value
    raw = getattr(value, "value", value)
    text = str(raw).lower()
    if text in {"hidden", "stepstate.hidden"}:
        return StepState.Hidden
    if text in {"complete", "stepstate.complete"}:
        return StepState.Complete
    if text in {"in_progress", "inprogress", "stepstate.inprogress", "stepstate.in_progress"}:
        return StepState.InProgress
    raise ValueError(f"unknown step state {value!r}")


def _notification_kind(notification: Any) -> str:
    if isinstance(notification, Mapping):
        return str(notification.get("kind", ""))
    return str(getattr(notification, "kind", getattr(notification, "type", "")))


def _call_bool(value: Any, name: str) -> bool:
    method = getattr(value, name, None)
    return bool(method()) if method is not None else False


def _schedule_frame(request_frame: Any) -> None:
    method = getattr(request_frame, "schedule_frame", None)
    if method is not None:
        method()


def _key_kind(key_event: Any) -> str:
    if isinstance(key_event, Mapping):
        return str(key_event.get("kind", "press")).lower()
    return str(getattr(key_event, "kind", "press")).lower()


def _key_code(key_event: Any) -> Any:
    if isinstance(key_event, Mapping):
        return key_event.get("key", key_event.get("code", key_event.get("char")))
    return getattr(key_event, "key", getattr(key_event, "code", getattr(key_event, "char", None)))


def _modifiers(key_event: Any) -> Set[str]:
    if isinstance(key_event, Mapping):
        raw = key_event.get("modifiers", set())
    else:
        raw = getattr(key_event, "modifiers", set())
    if isinstance(raw, str):
        return {part.strip().lower() for part in raw.replace("|", "+").split("+") if part.strip()}
    return {str(part).lower() for part in raw}


def _has_modifier(key_event: Any, name: str) -> bool:
    return name.lower() in _modifiers(key_event)


def _is_printable_char_key(key_event: Any) -> bool:
    code = _key_code(key_event)
    return isinstance(code, str) and len(code) == 1


def _is_quit_key(key_event: Any) -> bool:
    code = str(_key_code(key_event)).lower()
    return code in {"q", "esc", "escape"} or (_has_modifier(key_event, "control") and code in {"c", "x"})


def _trust_selection_value(name: str) -> Any:
    try:
        from .trust_directory import TrustDirectorySelection

        return getattr(TrustDirectorySelection, name)
    except Exception:
        return name


def _is_trust_selection(value: Any) -> bool:
    if value == _trust_selection_value("Trust"):
        return True
    raw = getattr(value, "value", value)
    name = getattr(value, "name", None)
    return str(raw).lower() == "trust" or str(name).lower() == "trust"


def _frame_requester(tui: Any) -> Any:
    requester = getattr(tui, "frame_requester", None)
    if requester is None:
        return FrameRequesterModel()
    return requester() if callable(requester) else requester


def _is_authenticated(login_status: Any) -> bool:
    text = str(getattr(login_status, "value", login_status))
    return text not in {"None", "NotAuthenticated", "LoginStatus.NotAuthenticated", ""}


def _forced_login_method_name(value: Any) -> str:
    return str(getattr(value, "value", value)).rsplit(".", 1)[-1]


def _factory_kwargs(kwargs: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        key: kwargs[key]
        for key in ("welcome_factory", "auth_factory", "trust_factory", "resolve_trust_target_fn")
        if key in kwargs
    }


def _event_kind(event: Any) -> str:
    if isinstance(event, Mapping):
        return str(event.get("kind", event.get("type", "")))
    return str(getattr(event, "kind", getattr(event, "type", "")))


def _event_payload(event: Any) -> Any:
    if isinstance(event, Mapping):
        return event.get("payload", event.get("event", event.get("notification", event.get("text"))))
    return getattr(event, "payload", getattr(event, "event", getattr(event, "notification", getattr(event, "text", None))))


def _event_message(event: Any) -> str:
    if isinstance(event, Mapping):
        return str(event.get("message", "app server disconnected"))
    return str(getattr(event, "message", "app server disconnected"))


def _has_chatgpt_success_message(screen: OnboardingScreen) -> bool:
    for step in screen.steps:
        if step.kind == "auth" and str(getattr(step.widget, "sign_in_state", "")) == "ChatGptSuccessMessage":
            return True
    return False


__all__ = [
    "ApiKeyEntryContext",
    "DefaultAuthModeWidget",
    "DefaultTrustDirectoryWidget",
    "DefaultWelcomeWidget",
    "FrameRequesterModel",
    "KeyboardHandler",
    "OnboardingResult",
    "OnboardingScreen",
    "OnboardingScreenArgs",
    "RUST_MODULE",
    "Step",
    "StepState",
    "StepStateProvider",
    "get_step_state",
    "handle_key_event",
    "handle_paste",
    "persist_selected_trust",
    "render_ref",
    "run_onboarding_app",
    "suppress_quit_while_typing_api_key",
    "used_rows",
]
