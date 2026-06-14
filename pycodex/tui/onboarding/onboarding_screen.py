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
from typing import Any, Awaitable, Callable, Mapping, Protocol, Sequence

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="onboarding::onboarding_screen",
    source="codex/codex-rs/tui/src/onboarding/onboarding_screen.rs",
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
class OnboardingScreen:
    request_frame: Any = field(default_factory=FrameRequesterModel)
    steps: list[Step] = field(default_factory=list)
    is_done_value: bool = False
    should_exit_value: bool = False

    @classmethod
    async def new(cls, *args: Any, **kwargs: Any) -> "OnboardingScreen":
        return not_ported(RUST_MODULE, "OnboardingScreen.new Tui/config construction")

    def current_steps_mut(self) -> list[Step]:
        return self.current_steps()

    def current_steps(self) -> list[Step]:
        out: list[Step] = []
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

    def auth_widget_mut(self) -> Any | None:
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


def render_ref(screen: OnboardingScreen, area: Any = None, buf: Any = None) -> list[Any]:
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
    last_non_empty: int | None = None
    for index, line in enumerate(lines[:height]):
        if str(line).strip():
            last_non_empty = index
    return 0 if last_non_empty is None else min(height, last_non_empty + 2)


async def run_onboarding_app(*args: Any, **kwargs: Any) -> OnboardingResult:
    return not_ported(RUST_MODULE, "run_onboarding_app async Tui/app-server loop")


async def persist_selected_trust(
    onboarding_screen: OnboardingScreen,
    request_handle: Any = None,
    *,
    write_trusted_project_fn: Callable[[Any, Path], Awaitable[Any]] | None = None,
) -> bool:
    for index, step in enumerate(onboarding_screen.steps):
        if step.kind != "trust":
            continue
        widget = step.widget
        if getattr(widget, "selection", None) != _trust_selection_value("Trust"):
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


def _modifiers(key_event: Any) -> set[str]:
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


__all__ = [
    "ApiKeyEntryContext",
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
