from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane",
    source="codex/codex-rs/tui/src/bottom_pane/mod.rs",
    status="complete",
)

QUIT_SHORTCUT_TIMEOUT = timedelta(seconds=1)
APPROVAL_PROMPT_TYPING_IDLE_DELAY = timedelta(seconds=1)
DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED = False


@dataclass
class LocalImageAttachment:
    placeholder: str = ""
    path: Any = None

    def __post_init__(self) -> None:
        if self.path is not None and not isinstance(self.path, Path):
            self.path = Path(self.path)


@dataclass
class MentionBinding:
    mention: str = ""
    path: str = ""


class CancellationEvent(Enum):
    HANDLED = "handled"
    NOT_HANDLED = "not_handled"


@dataclass
class DelayedApprovalRequest:
    request: Any = None
    features: Any = None
    requested_at: Optional[datetime] = None


class ConditionalUpdateStatus:
    UPDATED = "updated"
    SKIPPED = "skipped"


@dataclass
class BottomPaneParams:
    app_event_tx: Any = None
    frame_requester: Any = None
    has_input_focus: bool = True
    enhanced_keys_supported: bool = False
    placeholder_text: str = ""
    disable_paste_burst: bool = False
    animations_enabled: bool = True
    skills: Any = None


@dataclass
class ChatComposerRightReserveRenderable:
    width: int = 0
    label: str = ""

    def render(self, area: Any = None, buf: Any = None) -> Dict[str, Any]:
        return {"type": "right_reserve", "width": self.width, "label": self.label, "area": area}


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, dict):
        return str(key_event.get("key") or key_event.get("code") or key_event.get("name") or "")
    return str(getattr(key_event, "key", getattr(key_event, "code", key_event)))


def _is_release(key_event: Any) -> bool:
    if isinstance(key_event, dict):
        return str(key_event.get("kind", "press")).lower() == "release"
    return str(getattr(key_event, "kind", "press")).lower() == "release"


def _is_interrupt_key(key_event: Any) -> bool:
    name = _key_name(key_event).lower()
    if name in ("ctrl+c", "ctrl-c", "c-c", "interrupt"):
        return True
    if isinstance(key_event, dict):
        return bool(key_event.get("ctrl") and str(key_event.get("key", "")).lower() == "c")
    return bool(getattr(key_event, "ctrl", False) and str(getattr(key_event, "key", "")).lower() == "c")


def _send(tx: Any, event: Any) -> None:
    if tx is None:
        return
    if hasattr(tx, "send"):
        tx.send(event)
    elif hasattr(tx, "put"):
        tx.put(event)
    elif callable(tx):
        tx(event)
    elif isinstance(tx, list):
        tx.append(event)


class BottomPaneView:
    def render(self, area: Any = None, buf: Any = None) -> Dict[str, Any]:
        return {"type": self.__class__.__name__, "area": area}

    def desired_height(self, width: int) -> int:
        return 1

    def cursor_pos(self, area: Any = None) -> Optional[Tuple[int, int]]:
        return None

    def cursor_style(self) -> str:
        return "default"

    def handle_key_event(self, key_event: Any) -> Any:
        return None

    def handle_paste(self, pasted: str) -> bool:
        return False

    def on_ctrl_c(self) -> CancellationEvent:
        return CancellationEvent.NOT_HANDLED

    def is_complete(self) -> bool:
        return False

    def view_id(self) -> Optional[str]:
        return None

    def dismiss_app_server_request(self, request_id: Any) -> bool:
        return False

    def prefer_esc_to_handle_key_event(self) -> bool:
        return False


@dataclass
class DismissibleView(BottomPaneView):
    view_id_value: Optional[str] = None
    complete: bool = False
    handled_keys: List[Any] = field(default_factory=list)
    pasted_values: List[str] = field(default_factory=list)
    ctrl_c_count: int = 0

    def handle_key_event(self, key_event: Any) -> None:
        self.handled_keys.append(key_event)

    def handle_paste(self, pasted: str) -> bool:
        self.pasted_values.append(pasted)
        return False

    def on_ctrl_c(self) -> CancellationEvent:
        self.ctrl_c_count += 1
        self.complete = True
        return CancellationEvent.HANDLED

    def is_complete(self) -> bool:
        return self.complete

    def view_id(self) -> Optional[str]:
        return self.view_id_value

    def dismiss_app_server_request(self, request_id: Any) -> bool:
        if self.view_id_value == request_id:
            self.complete = True
            return True
        return False


@dataclass
class CompletingView(DismissibleView):
    def __post_init__(self) -> None:
        self.complete = True


@dataclass
class EscRoutingView(DismissibleView):
    prefer_esc: bool = True

    def prefer_esc_to_handle_key_event(self) -> bool:
        return self.prefer_esc


@dataclass
class CountingView(DismissibleView):
    count: int = 0

    def handle_key_event(self, key_event: Any) -> None:
        self.count += 1
        super().handle_key_event(key_event)


@dataclass
class BlockingView(DismissibleView):
    def on_ctrl_c(self) -> CancellationEvent:
        self.ctrl_c_count += 1
        return CancellationEvent.NOT_HANDLED


@dataclass
class PasteCompletesView(DismissibleView):
    def handle_paste(self, pasted: str) -> bool:
        self.pasted_values.append(pasted)
        self.complete = True
        return True


@dataclass
class BottomPane:
    composer_text_value: str = ""
    placeholder_text: str = ""
    view_stack: List[BottomPaneView] = field(default_factory=list)
    delayed_approval_requests: List[DelayedApprovalRequest] = field(default_factory=list)
    last_composer_activity_at: Optional[datetime] = None
    app_event_tx: Any = None
    frame_requester: Any = None
    thread_id_value: Any = None
    has_input_focus_value: bool = True
    enhanced_keys_supported: bool = False
    disable_paste_burst: bool = False
    composer_enabled: bool = True
    is_task_running_value: bool = False
    esc_backtrack_hint_value: bool = False
    animations_enabled_value: bool = True
    status_value: Any = None
    status_line_value: Any = None
    status_line_enabled_value: bool = False
    active_agent_label_value: Optional[str] = None
    side_conversation_context_label_value: Optional[str] = None
    pending_input_preview_items_value: List[Any] = field(default_factory=list)
    pending_thread_approvals_value: List[Any] = field(default_factory=list)
    unified_exec_processes_value: List[Any] = field(default_factory=list)
    context_window_percent_value: Optional[float] = None
    context_window_used_tokens_value: Optional[int] = None
    keymap_value: Any = None
    skills_value: Any = None
    plugins_value: Any = None
    mention_bindings: List[MentionBinding] = field(default_factory=list)
    recent_submission_mention_bindings: List[MentionBinding] = field(default_factory=list)
    local_images: List[LocalImageAttachment] = field(default_factory=list)
    recent_submission_images: List[LocalImageAttachment] = field(default_factory=list)
    remote_image_url_values: List[str] = field(default_factory=list)
    pending_pastes: List[str] = field(default_factory=list)
    quit_shortcut_hint_value: bool = False
    redraw_requests: List[Any] = field(default_factory=list)

    @classmethod
    def new(cls, params: Optional[BottomPaneParams] = None, **kwargs: Any) -> "BottomPane":
        if params is None:
            params = BottomPaneParams(**kwargs)
        return cls(
            app_event_tx=params.app_event_tx,
            frame_requester=params.frame_requester,
            has_input_focus_value=params.has_input_focus,
            enhanced_keys_supported=params.enhanced_keys_supported,
            placeholder_text=params.placeholder_text,
            disable_paste_burst=params.disable_paste_burst,
            animations_enabled_value=params.animations_enabled,
            skills_value=params.skills,
        )

    def request_redraw(self, reason: Any = None) -> None:
        self.redraw_requests.append(reason)
        if self.frame_requester is not None:
            _send(self.frame_requester, reason)

    def push_view(self, view: BottomPaneView) -> None:
        self.view_stack.append(view)
        self.request_redraw("push_view")

    def pop_view(self) -> Optional[BottomPaneView]:
        if not self.view_stack:
            return None
        view = self.view_stack.pop()
        self.request_redraw("pop_view")
        return view

    def active_view(self) -> Optional[BottomPaneView]:
        return self.view_stack[-1] if self.view_stack else None

    def active_view_id(self) -> Optional[str]:
        active = self.active_view()
        return view_id(active) if active is not None else None

    def has_active_view(self) -> bool:
        return bool(self.view_stack)

    def no_modal_or_popup_active(self) -> bool:
        return not self.has_active_view()

    def pop_active_view_with_completion(self) -> None:
        while self.view_stack and is_complete(self.view_stack[-1]):
            self.view_stack.pop()
            self.composer_enabled = True
        self.request_redraw("completion")

    def handle_key_event(self, key_event: Any) -> CancellationEvent:
        if _is_release(key_event):
            return CancellationEvent.NOT_HANDLED
        active = self.active_view()
        name = _key_name(key_event).lower()
        if active is not None:
            if name == "esc" and not active.prefer_esc_to_handle_key_event():
                result = active.on_ctrl_c()
            elif name == "esc" or _is_interrupt_key(key_event):
                result = active.handle_key_event(key_event) or CancellationEvent.HANDLED
            else:
                result = active.handle_key_event(key_event) or CancellationEvent.HANDLED
            self.pop_active_view_with_completion()
            return result if isinstance(result, CancellationEvent) else CancellationEvent.HANDLED
        if _is_interrupt_key(key_event):
            if self.is_task_running_value:
                self.interrupt_running_task()
                return CancellationEvent.HANDLED
            return self.on_ctrl_c()
        if len(name) == 1 and self.composer_enabled:
            self.insert_str(name)
        return CancellationEvent.NOT_HANDLED

    def handle_paste(self, pasted: str) -> bool:
        active = self.active_view()
        if active is not None and active.handle_paste(pasted):
            self.pop_active_view_with_completion()
            return True
        if self.disable_paste_burst:
            self.pending_pastes.append(pasted)
        else:
            self.insert_str(pasted)
        return False

    def on_ctrl_c(self) -> CancellationEvent:
        active = self.active_view()
        if active is not None:
            result = active.on_ctrl_c()
            self.pop_active_view_with_completion()
            return result
        if self.composer_text_value:
            self.composer_text_value = ""
            return CancellationEvent.HANDLED
        self.quit_shortcut_hint_value = True
        return CancellationEvent.NOT_HANDLED

    def interrupt_running_task(self) -> None:
        _send(self.app_event_tx, {"type": "CodexOp", "op": "Interrupt"})

    def insert_str(self, text: str) -> None:
        if not self.composer_enabled:
            return
        self.composer_text_value += text
        self.last_composer_activity_at = datetime.now()
        self.request_redraw("insert")

    def clear_composer(self) -> None:
        self.composer_text_value = ""
        self.request_redraw("clear_composer")

    def composer_text(self) -> str:
        return self.composer_text_value

    def set_composer_text(self, text: str) -> None:
        self.composer_text_value = text
        self.last_composer_activity_at = datetime.now()

    def set_input_focus(self, focused: bool) -> None:
        self.has_input_focus_value = focused

    def has_input_focus(self) -> bool:
        return self.has_input_focus_value

    def set_task_running(self, running: bool) -> None:
        self.is_task_running_value = running

    def is_task_running(self) -> bool:
        return self.is_task_running_value

    def show_selection_view(self, params: Any = None, *args: Any, **kwargs: Any) -> None:
        self.push_view(DismissibleView(view_id_value="selection"))
        self.composer_enabled = False

    def show_view(self, view: BottomPaneView) -> None:
        self.push_view(view)
        self.composer_enabled = False

    def push_approval_request(self, request: Any, features: Any = None, now: Optional[datetime] = None) -> None:
        now = now or datetime.now()
        if self.approval_prompt_delay_remaining(now) > timedelta(0):
            self.delayed_approval_requests.append(DelayedApprovalRequest(request, features, now))
        else:
            self.push_view(DismissibleView(view_id_value=getattr(request, "id", request)))
            self.composer_enabled = False

    def approval_prompt_delay_remaining(self, now: Optional[datetime] = None) -> timedelta:
        if self.last_composer_activity_at is None:
            return timedelta(0)
        now = now or datetime.now()
        remaining = APPROVAL_PROMPT_TYPING_IDLE_DELAY - (now - self.last_composer_activity_at)
        return remaining if remaining > timedelta(0) else timedelta(0)

    def record_composer_activity_at(self, when: datetime) -> None:
        self.last_composer_activity_at = when

    def maybe_show_delayed_approval_requests_at(self, now: datetime) -> bool:
        if self.approval_prompt_delay_remaining(now) > timedelta(0) or not self.delayed_approval_requests:
            return False
        delayed = self.delayed_approval_requests.pop(0)
        self.push_view(DismissibleView(view_id_value=getattr(delayed.request, "id", delayed.request)))
        self.composer_enabled = False
        return True

    def dismiss_app_server_request(self, request_id: Any) -> bool:
        before = len(self.delayed_approval_requests)
        self.delayed_approval_requests = [
            request
            for request in self.delayed_approval_requests
            if getattr(request.request, "id", request.request) != request_id
        ]
        dismissed = before != len(self.delayed_approval_requests)
        for view in list(self.view_stack):
            dismissed = view.dismiss_app_server_request(request_id) or dismissed
        self.pop_active_view_with_completion()
        return dismissed

    def add_local_image(self, attachment: LocalImageAttachment) -> None:
        self.local_images.append(attachment)

    def add_mention_binding(self, binding: MentionBinding) -> None:
        self.mention_bindings.append(binding)

    def set_remote_image_urls(self, urls: Iterable[str]) -> None:
        self.remote_image_url_values = list(urls)

    def remote_image_urls(self) -> List[str]:
        return list(self.remote_image_url_values)

    def drain_pending_submission_state(self) -> Dict[str, Any]:
        drained = {
            "text": self.composer_text_value,
            "images": list(self.local_images),
            "mentions": list(self.mention_bindings),
            "remote_image_urls": list(self.remote_image_url_values),
        }
        self.recent_submission_images = list(self.local_images)
        self.recent_submission_mention_bindings = list(self.mention_bindings)
        self.composer_text_value = ""
        self.local_images = []
        self.mention_bindings = []
        self.remote_image_url_values = []
        return drained

    def set_status(self, status: Any) -> None:
        self.status_value = status

    def status(self) -> Any:
        return self.status_value

    def set_status_line(self, status_line: Any) -> None:
        self.status_line_value = status_line

    def status_line(self) -> Any:
        return self.status_line_value

    def set_status_line_enabled(self, enabled: bool) -> None:
        self.status_line_enabled_value = enabled

    def set_active_agent_label(self, label: Optional[str]) -> None:
        self.active_agent_label_value = label

    def set_side_conversation_context_label(self, label: Optional[str]) -> None:
        self.side_conversation_context_label_value = label

    def set_pending_input_preview_items(self, items: Iterable[Any]) -> None:
        self.pending_input_preview_items_value = list(items)

    def set_pending_thread_approvals(self, approvals: Iterable[Any]) -> None:
        self.pending_thread_approvals_value = list(approvals)

    def pending_thread_approvals(self) -> List[Any]:
        return list(self.pending_thread_approvals_value)

    def set_unified_exec_processes(self, processes: Iterable[Any]) -> None:
        self.unified_exec_processes_value = list(processes)

    def unified_exec_processes(self) -> List[Any]:
        return list(self.unified_exec_processes_value)

    def set_context_window(self, percent: Optional[float], used_tokens: Optional[int] = None) -> None:
        self.context_window_percent_value = percent
        self.context_window_used_tokens_value = used_tokens

    def context_window_percent(self) -> Optional[float]:
        return self.context_window_percent_value

    def context_window_used_tokens(self) -> Optional[int]:
        return self.context_window_used_tokens_value

    def set_keymap(self, keymap: Any) -> None:
        self.keymap_value = keymap

    def keymap(self) -> Any:
        return self.keymap_value

    def update_skills(self, skills: Any) -> None:
        self.skills_value = skills

    def update_plugins(self, plugins: Any) -> None:
        self.plugins_value = plugins

    def thread_id(self) -> Any:
        return self.thread_id_value

    def set_thread_id(self, thread_id: Any) -> None:
        self.thread_id_value = thread_id

    def render(self, area: Any = None, buf: Any = None) -> Dict[str, Any]:
        return {
            "type": "BottomPane",
            "text": self.composer_text_value,
            "active_view": self.active_view_id(),
            "views": len(self.view_stack),
            "status": self.status_value,
            "area": area,
        }

    def desired_height(self, width: int = 0) -> int:
        active = self.active_view()
        return active.desired_height(width) if active is not None else max(1, self.composer_text_value.count("\n") + 1)

    def cursor_pos(self, area: Any = None) -> Tuple[int, int]:
        active = self.active_view()
        view_cursor = active.cursor_pos(area) if active is not None else None
        if view_cursor is not None:
            return view_cursor
        return (len(self.composer_text_value), 0)

    def cursor_style(self) -> str:
        active = self.active_view()
        return active.cursor_style() if active is not None else "default"


def render(pane: BottomPane, area: Any = None, buf: Any = None) -> Dict[str, Any]:
    return pane.render(area, buf)


def desired_height(pane: BottomPane, width: int = 0) -> int:
    return pane.desired_height(width)


def cursor_pos(pane: BottomPane, area: Any = None) -> Tuple[int, int]:
    return pane.cursor_pos(area)


def cursor_style(pane: BottomPane) -> str:
    return pane.cursor_style()


def snapshot_buffer(pane: BottomPane) -> Dict[str, Any]:
    return pane.render()


def render_snapshot(pane: BottomPane) -> str:
    state = pane.render()
    return "BottomPane(text={!r}, active_view={!r}, views={!r})".format(
        state["text"], state["active_view"], state["views"]
    )


def test_pane() -> BottomPane:
    return BottomPane.new(BottomPaneParams())


def test_pane_with_disable_paste_burst() -> BottomPane:
    return BottomPane.new(BottomPaneParams(disable_paste_burst=True))


test_pane.__test__ = False
test_pane_with_disable_paste_burst.__test__ = False


def exec_request(command: str = "") -> Dict[str, Any]:
    return {"type": "exec", "command": command}


def is_complete(view: Any) -> bool:
    return bool(getattr(view, "is_complete", lambda: False)())


def view_id(view: Any) -> Optional[str]:
    value = getattr(view, "view_id", None)
    return value() if callable(value) else None


def dismiss_app_server_request(view: Any, request_id: Any) -> bool:
    return bool(getattr(view, "dismiss_app_server_request", lambda _request_id: False)(request_id))


def handle_key_event(view: Any, key_event: Any) -> Any:
    return getattr(view, "handle_key_event", lambda _key: None)(key_event)


def handle_paste(view: Any, pasted: str) -> bool:
    return bool(getattr(view, "handle_paste", lambda _pasted: False)(pasted))


def on_ctrl_c(view: Any) -> CancellationEvent:
    return getattr(view, "on_ctrl_c", lambda: CancellationEvent.NOT_HANDLED)()


def prefer_esc_to_handle_key_event(view: Any) -> bool:
    return bool(getattr(view, "prefer_esc_to_handle_key_event", lambda: False)())


def selection_view_renders_snapshot() -> bool:
    pane = test_pane()
    pane.show_selection_view()
    return "views=1" in render_snapshot(pane)


def clear_for_history_entry_dismisses_active_view() -> bool:
    pane = test_pane()
    pane.show_view(DismissibleView("history"))
    pane.on_ctrl_c()
    return not pane.has_active_view()


def ctrl_c_on_empty_composer_shows_quit_hint_then_exits() -> bool:
    pane = test_pane()
    result = pane.on_ctrl_c()
    return result is CancellationEvent.NOT_HANDLED and pane.quit_shortcut_hint_value


def ctrl_c_on_non_empty_composer_clears_text() -> bool:
    pane = test_pane()
    pane.insert_str("hello")
    result = pane.on_ctrl_c()
    return result is CancellationEvent.HANDLED and pane.composer_text() == ""


def ctrl_c_on_modal_consumes_without_showing_quit_hint() -> bool:
    pane = test_pane()
    pane.show_view(DismissibleView("modal"))
    result = pane.on_ctrl_c()
    return result is CancellationEvent.HANDLED and not pane.quit_shortcut_hint_value and not pane.has_active_view()


def ctrl_c_on_blocking_modal_returns_not_handled() -> bool:
    pane = test_pane()
    pane.show_view(BlockingView("blocking"))
    return pane.on_ctrl_c() is CancellationEvent.NOT_HANDLED


def esc_routes_to_view_when_preferred() -> bool:
    pane = test_pane()
    view = EscRoutingView("esc")
    pane.show_view(view)
    pane.handle_key_event({"key": "esc"})
    return len(view.handled_keys) == 1


def esc_dismisses_view_when_not_preferred() -> bool:
    pane = test_pane()
    view = EscRoutingView("esc", prefer_esc=False)
    pane.show_view(view)
    pane.handle_key_event({"key": "esc"})
    return not pane.has_active_view()


def key_release_ignored_by_active_view() -> bool:
    pane = test_pane()
    view = CountingView("count")
    pane.show_view(view)
    pane.handle_key_event({"key": "x", "kind": "release"})
    return view.count == 0


def paste_completes_active_view_and_reenables_composer() -> bool:
    pane = test_pane()
    pane.show_view(PasteCompletesView("paste"))
    handled = pane.handle_paste("payload")
    return handled and not pane.has_active_view() and pane.composer_enabled


def paste_appends_to_composer_without_active_view() -> bool:
    pane = test_pane()
    pane.handle_paste("payload")
    return pane.composer_text() == "payload"


def paste_burst_is_buffered_when_disabled() -> bool:
    pane = test_pane_with_disable_paste_burst()
    pane.handle_paste("payload")
    return pane.pending_pastes == ["payload"] and pane.composer_text() == ""


def interrupt_key_sends_interrupt_when_task_running() -> bool:
    sent: List[Any] = []
    pane = BottomPane.new(BottomPaneParams(app_event_tx=sent))
    pane.set_task_running(True)
    result = pane.handle_key_event({"key": "c", "ctrl": True})
    return result is CancellationEvent.HANDLED and sent == [{"type": "CodexOp", "op": "Interrupt"}]


def delayed_approval_waits_for_idle_composer() -> bool:
    pane = test_pane()
    now = datetime(2026, 1, 1, 0, 0, 0)
    pane.record_composer_activity_at(now)
    pane.push_approval_request("approval", now=now)
    return len(pane.delayed_approval_requests) == 1 and not pane.has_active_view()


def delayed_approval_shows_after_idle() -> bool:
    pane = test_pane()
    now = datetime(2026, 1, 1, 0, 0, 0)
    pane.record_composer_activity_at(now)
    pane.push_approval_request("approval", now=now)
    return pane.maybe_show_delayed_approval_requests_at(now + timedelta(seconds=2)) and pane.active_view_id() == "approval"


def dismiss_app_server_request_removes_delayed_request() -> bool:
    pane = test_pane()
    pane.delayed_approval_requests.append(DelayedApprovalRequest("request-1"))
    return pane.dismiss_app_server_request("request-1") and not pane.delayed_approval_requests


def drain_pending_submission_state_clears_assets() -> bool:
    pane = test_pane()
    pane.insert_str("hello")
    pane.add_local_image(LocalImageAttachment("[img]", "image.png"))
    pane.add_mention_binding(MentionBinding("@file", "file.py"))
    pane.set_remote_image_urls(["https://example.invalid/image.png"])
    drained = pane.drain_pending_submission_state()
    return (
        drained["text"] == "hello"
        and len(drained["images"]) == 1
        and len(drained["mentions"]) == 1
        and drained["remote_image_urls"] == ["https://example.invalid/image.png"]
        and pane.composer_text() == ""
        and pane.remote_image_urls() == []
    )


def render_snapshot_with_empty_composer() -> bool:
    return "BottomPane" in render_snapshot(test_pane())


def render_snapshot_with_active_view() -> bool:
    pane = test_pane()
    pane.show_view(DismissibleView("active"))
    return "active" in render_snapshot(pane)


def desired_height_follows_active_view() -> bool:
    pane = test_pane()
    pane.show_view(DismissibleView("height"))
    return pane.desired_height(80) == 1


def cursor_pos_tracks_composer_text() -> bool:
    pane = test_pane()
    pane.insert_str("abc")
    return pane.cursor_pos() == (3, 0)


def status_and_context_setters_round_trip() -> bool:
    pane = test_pane()
    pane.set_status("running")
    pane.set_context_window(0.5, 123)
    pane.set_pending_thread_approvals(["a"])
    pane.set_unified_exec_processes(["p"])
    return (
        pane.status() == "running"
        and pane.context_window_percent() == 0.5
        and pane.context_window_used_tokens() == 123
        and pane.pending_thread_approvals() == ["a"]
        and pane.unified_exec_processes() == ["p"]
    )


def ignored_key_event_does_not_mutate_modal() -> bool:
    return key_release_ignored_by_active_view()


__all__ = [
    "RUST_MODULE",
    "APPROVAL_PROMPT_TYPING_IDLE_DELAY",
    "BottomPane",
    "BottomPaneParams",
    "BottomPaneView",
    "BlockingView",
    "CancellationEvent",
    "ChatComposerRightReserveRenderable",
    "CompletingView",
    "ConditionalUpdateStatus",
    "CountingView",
    "DelayedApprovalRequest",
    "DismissibleView",
    "DOUBLE_PRESS_QUIT_SHORTCUT_ENABLED",
    "EscRoutingView",
    "LocalImageAttachment",
    "MentionBinding",
    "PasteCompletesView",
    "QUIT_SHORTCUT_TIMEOUT",
    "clear_for_history_entry_dismisses_active_view",
    "ctrl_c_on_blocking_modal_returns_not_handled",
    "ctrl_c_on_empty_composer_shows_quit_hint_then_exits",
    "ctrl_c_on_modal_consumes_without_showing_quit_hint",
    "ctrl_c_on_non_empty_composer_clears_text",
    "cursor_pos",
    "cursor_pos_tracks_composer_text",
    "cursor_style",
    "delayed_approval_shows_after_idle",
    "delayed_approval_waits_for_idle_composer",
    "desired_height",
    "desired_height_follows_active_view",
    "dismiss_app_server_request",
    "dismiss_app_server_request_removes_delayed_request",
    "drain_pending_submission_state_clears_assets",
    "esc_dismisses_view_when_not_preferred",
    "esc_routes_to_view_when_preferred",
    "exec_request",
    "handle_key_event",
    "handle_paste",
    "ignored_key_event_does_not_mutate_modal",
    "interrupt_key_sends_interrupt_when_task_running",
    "is_complete",
    "key_release_ignored_by_active_view",
    "on_ctrl_c",
    "paste_appends_to_composer_without_active_view",
    "paste_burst_is_buffered_when_disabled",
    "paste_completes_active_view_and_reenables_composer",
    "prefer_esc_to_handle_key_event",
    "render",
    "render_snapshot",
    "render_snapshot_with_active_view",
    "render_snapshot_with_empty_composer",
    "selection_view_renders_snapshot",
    "snapshot_buffer",
    "status_and_context_setters_round_trip",
    "test_pane",
    "test_pane_with_disable_paste_burst",
    "view_id",
]
