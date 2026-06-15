"""Thread event buffering and replay state for the TUI app.

Rust reference: codex-rs/tui/src/app/thread_events.rs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from .._porting import RustTuiModule
from .pending_interactive_replay import (
    AppCommand,
    PendingInteractiveReplayState,
    ServerNotification,
    ServerRequest,
)

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_events",
    source="codex/codex-rs/tui/src/app/thread_events.rs",
    status="complete",
)


class SideParentStatus(str, Enum):
    NEEDS_INPUT = "NeedsInput"
    NEEDS_APPROVAL = "NeedsApproval"


@dataclass(frozen=True)
class Turn:
    id: str
    status: str
    items: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ThreadEventSnapshot:
    session: Optional[Any] = None
    turns: List[Turn] = field(default_factory=list)
    events: List["ThreadBufferedEvent"] = field(default_factory=list)
    input_state: Optional[Any] = None


@dataclass(frozen=True)
class ThreadBufferedEvent:
    kind: str
    payload: Any

    @classmethod
    def notification(cls, notification: Any) -> "ThreadBufferedEvent":
        return cls("Notification", notification)

    @classmethod
    def request(cls, request: Any) -> "ThreadBufferedEvent":
        return cls("Request", request)

    @classmethod
    def history_entry_response(cls, response: Any) -> "ThreadBufferedEvent":
        return cls("HistoryEntryResponse", response)

    @classmethod
    def feedback_submission(cls, event: Any) -> "ThreadBufferedEvent":
        return cls("FeedbackSubmission", event)


@dataclass(frozen=True)
class FeedbackThreadEvent:
    category: Any
    include_logs: bool
    feedback_audience: Any
    result: Any


@dataclass
class ThreadEventStore:
    capacity: int
    session: Optional[Any] = None
    turns: List[Turn] = field(default_factory=list)
    buffer: List[ThreadBufferedEvent] = field(default_factory=list)
    pending_interactive_replay: PendingInteractiveReplayState = field(default_factory=PendingInteractiveReplayState)
    _active_turn_id: Optional[str] = None
    input_state: Optional[Any] = None
    active: bool = False

    @staticmethod
    def event_survives_session_refresh(event: Union[ThreadBufferedEvent, Dict[str, Any], Any]) -> bool:
        event = _coerce_event(event)
        if event.kind == "Request":
            return True
        if event.kind == "FeedbackSubmission":
            return True
        if event.kind == "Notification":
            return _variant_name(event.payload) in {"HookStarted", "HookCompleted"}
        return False

    @classmethod
    def new(cls, capacity: int) -> "ThreadEventStore":
        return cls(capacity=int(capacity))

    @classmethod
    def new_with_session(cls, capacity: int, session: Any, turns: List[Any]) -> "ThreadEventStore":
        store = cls.new(capacity)
        store.set_session(session, turns)
        return store

    def set_session(self, session: Any, turns: List[Any]) -> None:
        self.session = session
        self.set_turns(turns)

    def rebase_buffer_after_session_refresh(self) -> None:
        self.buffer = [event for event in self.buffer if self.event_survives_session_refresh(event)]

    def set_turns(self, turns: List[Any]) -> None:
        coerced = [_coerce_turn(turn) for turn in turns]
        self._active_turn_id = next((turn.id for turn in reversed(coerced) if turn.status == "InProgress"), None)
        self.turns = coerced

    def push_notification(self, notification: Union[ServerNotification, Dict[str, Any], Any]) -> None:
        notification = _coerce_notification(notification)
        self.pending_interactive_replay.note_server_notification(notification)
        if notification.kind == "TurnStarted":
            self._active_turn_id = _turn_id_from_notification(notification)
        elif notification.kind == "TurnCompleted" and self._active_turn_id == _turn_id_from_notification(notification):
            self._active_turn_id = None
        elif notification.kind == "ThreadClosed":
            self._active_turn_id = None
        self._push(ThreadBufferedEvent.notification(notification))

    def push_request(self, request: Union[ServerRequest, Dict[str, Any], Any]) -> None:
        request = _coerce_request(request)
        self.pending_interactive_replay.note_server_request(request)
        self._push(ThreadBufferedEvent.request(request))

    def pending_replay_requests(self) -> List[ServerRequest]:
        return [
            event.payload
            for event in self.buffer
            if event.kind == "Request" and self.pending_interactive_replay.should_replay_snapshot_request(event.payload)
        ]

    def file_change_changes(self, turn_id: str, item_id: str) -> Optional[List[Any]]:
        for event in reversed(self.buffer):
            if event.kind == "Notification" and _variant_name(event.payload) in {"ItemStarted", "ItemCompleted"}:
                if turn_id_matches(turn_id, _notification_turn_id(event.payload)):
                    changes = file_change_item_changes(_notification_item(event.payload), item_id)
                    if changes is not None:
                        return changes
        for turn in reversed(self.turns):
            if turn_id_matches(turn_id, turn.id):
                for item in reversed(turn.items):
                    changes = file_change_item_changes(item, item_id)
                    if changes is not None:
                        return changes
        return None

    def apply_thread_rollback(self, response: Any) -> None:
        thread = response.get("thread") if isinstance(response, dict) else getattr(response, "thread", response)
        turns = thread.get("turns", []) if isinstance(thread, dict) else getattr(thread, "turns", [])
        self.turns = [_coerce_turn(turn) for turn in turns]
        self.buffer.clear()
        self.pending_interactive_replay = PendingInteractiveReplayState()
        self._active_turn_id = None

    def snapshot(self) -> ThreadEventSnapshot:
        events = [
            event
            for event in self.buffer
            if event.kind != "Request" or self.pending_interactive_replay.should_replay_snapshot_request(event.payload)
        ]
        return ThreadEventSnapshot(self.session, list(self.turns), events, self.input_state)

    def note_outbound_op(self, op: Union[AppCommand, Dict[str, Any], Any]) -> None:
        self.pending_interactive_replay.note_outbound_op(op)

    @staticmethod
    def op_can_change_pending_replay_state(op: Union[AppCommand, Dict[str, Any], Any]) -> bool:
        return PendingInteractiveReplayState.op_can_change_state(op)

    def has_pending_thread_approvals(self) -> bool:
        return self.pending_interactive_replay.has_pending_thread_approvals()

    def side_parent_pending_status(self) -> Optional[SideParentStatus]:
        if self.pending_interactive_replay.has_pending_thread_user_input():
            return SideParentStatus.NEEDS_INPUT
        if self.pending_interactive_replay.has_pending_thread_approvals():
            return SideParentStatus.NEEDS_APPROVAL
        return None

    def active_turn_id(self) -> Optional[str]:
        return self._active_turn_id

    def clear_active_turn_id(self) -> None:
        self._active_turn_id = None

    def _push(self, event: ThreadBufferedEvent) -> None:
        self.buffer.append(event)
        if len(self.buffer) > self.capacity:
            removed = self.buffer.pop(0)
            if removed.kind == "Request":
                self.pending_interactive_replay.note_evicted_server_request(removed.payload)


def turn_id_matches(request_turn_id: str, candidate_turn_id: str) -> bool:
    return request_turn_id == "" or request_turn_id == candidate_turn_id


def file_change_item_changes(item: Any, item_id: str) -> Optional[List[Any]]:
    if item is None:
        return None
    if isinstance(item, dict):
        if item.get("kind") == "FileChange" and item.get("id") == item_id:
            return list(item.get("changes", []))
        return None
    if _variant_name(item) == "FileChange" and getattr(item, "id", None) == item_id:
        return list(getattr(item, "changes", []))
    return None


@dataclass
class ThreadEventChannel:
    sender: List[ThreadBufferedEvent]
    receiver: Optional[List[ThreadBufferedEvent]]
    store: ThreadEventStore

    @classmethod
    def new(cls, capacity: int) -> "ThreadEventChannel":
        queue: List[ThreadBufferedEvent] = []
        return cls(queue, queue, ThreadEventStore.new(capacity))

    @classmethod
    def new_with_session(cls, capacity: int, session: Any, turns: List[Any]) -> "ThreadEventChannel":
        queue: List[ThreadBufferedEvent] = []
        return cls(queue, queue, ThreadEventStore.new_with_session(capacity, session, turns))


def test_thread_session(thread_id: str = "thread-1", cwd: str = "/tmp/project") -> dict[str, Any]:
    return {"thread_id": thread_id, "cwd": cwd}


def test_turn(turn_id: str, status: str, items: List[Any] | None = None) -> Turn:
    return Turn(turn_id, status, list(items or []))


test_turn.__test__ = False


def turn_started_notification(thread_id: str, turn_id: str) -> ServerNotification:
    return ServerNotification("TurnStarted", turn_id=turn_id, item={"thread_id": thread_id})


def turn_completed_notification(thread_id: str, turn_id: str, status: str = "Completed") -> ServerNotification:
    return ServerNotification("TurnCompleted", turn_id=turn_id, item={"thread_id": thread_id, "status": status})


def hook_started_notification(thread_id: str, turn_id: str) -> ServerNotification:
    return ServerNotification("HookStarted", turn_id=turn_id, item={"thread_id": thread_id})


def hook_completed_notification(thread_id: str, turn_id: str) -> ServerNotification:
    return ServerNotification("HookCompleted", turn_id=turn_id, item={"thread_id": thread_id})


def exec_approval_request(thread_id: str, turn_id: str, item_id: str, approval_id: Optional[str] = None) -> ServerRequest:
    return ServerRequest("CommandExecutionRequestApproval", 1, {"thread_id": thread_id, "turn_id": turn_id, "item_id": item_id, "approval_id": approval_id})


def thread_event_store_tracks_active_turn_lifecycle() -> bool:
    store = ThreadEventStore.new(8)
    store.push_notification(turn_started_notification("thread-1", "turn-1"))
    active = store.active_turn_id() == "turn-1"
    store.push_notification(turn_completed_notification("thread-1", "turn-2"))
    unchanged = store.active_turn_id() == "turn-1"
    store.push_notification(turn_completed_notification("thread-1", "turn-1", "Interrupted"))
    cleared = store.active_turn_id() is None
    return active and unchanged and cleared


def thread_event_store_restores_active_turn_from_snapshot_turns() -> bool:
    turns = [test_turn("turn-1", "Completed"), test_turn("turn-2", "InProgress")]
    store = ThreadEventStore.new_with_session(8, test_thread_session(), turns)
    refreshed = ThreadEventStore.new(8)
    refreshed.set_session(test_thread_session(), turns)
    return store.active_turn_id() == "turn-2" and refreshed.active_turn_id() == "turn-2"


def thread_event_store_clear_active_turn_id_resets_cached_turn() -> bool:
    store = ThreadEventStore.new(8)
    store.push_notification(turn_started_notification("thread-1", "turn-1"))
    store.clear_active_turn_id()
    return store.active_turn_id() is None


def thread_event_store_rebase_preserves_resolved_request_state() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(exec_approval_request("thread-1", "turn-approval", "call-approval"))
    store.push_notification(ServerNotification("ServerRequestResolved", request_id=1))
    store.rebase_buffer_after_session_refresh()
    return store.snapshot().events == [] and store.has_pending_thread_approvals() is False


def thread_event_store_rebase_preserves_hook_notifications() -> bool:
    store = ThreadEventStore.new(8)
    started = hook_started_notification("thread-1", "turn-hook")
    completed = hook_completed_notification("thread-1", "turn-hook")
    store.push_notification(started)
    store.push_notification(completed)
    store.rebase_buffer_after_session_refresh()
    return [event.payload for event in store.snapshot().events] == [started, completed]


def _coerce_event(event: Union[ThreadBufferedEvent, Dict[str, Any], Any]) -> ThreadBufferedEvent:
    if isinstance(event, ThreadBufferedEvent):
        return event
    if isinstance(event, dict):
        return ThreadBufferedEvent(str(event.get("kind") or event.get("type")), event.get("payload"))
    return ThreadBufferedEvent(str(getattr(event, "kind", getattr(event, "type", event.__class__.__name__))), getattr(event, "payload", None))


def _coerce_request(request: Union[ServerRequest, Dict[str, Any], Any]) -> ServerRequest:
    if isinstance(request, ServerRequest):
        return request
    if isinstance(request, dict):
        return ServerRequest(str(request.get("kind") or request.get("type")), request.get("request_id"), dict(request.get("params") or {}))
    return ServerRequest(str(getattr(request, "kind", getattr(request, "type", request.__class__.__name__))), getattr(request, "request_id"), dict(getattr(request, "params", {}) or {}))


def _coerce_notification(notification: Union[ServerNotification, Dict[str, Any], Any]) -> ServerNotification:
    if isinstance(notification, ServerNotification):
        return notification
    if isinstance(notification, dict):
        return ServerNotification(str(notification.get("kind") or notification.get("type")), notification.get("request_id"), notification.get("turn_id"), notification.get("item"))
    return ServerNotification(str(getattr(notification, "kind", getattr(notification, "type", notification.__class__.__name__))), getattr(notification, "request_id", None), getattr(notification, "turn_id", None), getattr(notification, "item", None))


def _coerce_turn(turn: Union[Turn, Dict[str, Any], Any]) -> Turn:
    if isinstance(turn, Turn):
        return turn
    if isinstance(turn, dict):
        return Turn(str(turn.get("id")), str(turn.get("status")), list(turn.get("items", [])))
    return Turn(str(getattr(turn, "id")), str(getattr(turn, "status")), list(getattr(turn, "items", [])))


def _variant_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("kind") or value.get("type") or value.get("variant") or "")
    return str(getattr(value, "kind", getattr(value, "type", getattr(value, "variant", value.__class__.__name__))))


def _turn_id_from_notification(notification: ServerNotification) -> Optional[str]:
    return notification.turn_id


def _notification_turn_id(notification: ServerNotification) -> str:
    return str(notification.turn_id or "")


def _notification_item(notification: ServerNotification) -> Any:
    return notification.item


__all__ = [name for name in globals() if not name.startswith("_")]
