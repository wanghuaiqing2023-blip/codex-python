"""Pending interactive prompt replay state.

Rust reference: codex-rs/tui/src/app/pending_interactive_replay.rs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::pending_interactive_replay",
    source="codex/codex-rs/tui/src/app/pending_interactive_replay.rs",
    status="complete",
)


@dataclass(frozen=True)
class ElicitationRequestKey:
    server_name: str
    request_id: Any

    @classmethod
    def new(cls, server_name: str, request_id: Any) -> "ElicitationRequestKey":
        return cls(str(server_name), request_id)


class PendingInteractiveRequestKind(str, Enum):
    EXEC_APPROVAL = "ExecApproval"
    PATCH_APPROVAL = "PatchApproval"
    ELICITATION = "Elicitation"
    REQUEST_PERMISSIONS = "RequestPermissions"
    REQUEST_USER_INPUT = "RequestUserInput"


@dataclass(frozen=True)
class PendingInteractiveRequest:
    kind: PendingInteractiveRequestKind
    turn_id: Optional[str] = None
    item_id: Optional[str] = None
    approval_id: Optional[str] = None
    elicitation_key: Optional[ElicitationRequestKey] = None


@dataclass(frozen=True)
class ServerRequest:
    kind: str
    request_id: Any
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ServerNotification:
    kind: str
    request_id: Optional[Any] = None
    turn_id: Optional[str] = None
    item: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class AppCommand:
    kind: str
    id: Optional[str] = None
    turn_id: Optional[str] = None
    server_name: Optional[str] = None
    request_id: Optional[Any] = None


@dataclass
class PendingInteractiveReplayState:
    exec_approval_call_ids: Set[str] = field(default_factory=set)
    exec_approval_call_ids_by_turn_id: Dict[str, List[str]] = field(default_factory=dict)
    patch_approval_call_ids: Set[str] = field(default_factory=set)
    patch_approval_call_ids_by_turn_id: Dict[str, List[str]] = field(default_factory=dict)
    elicitation_requests: Set[ElicitationRequestKey] = field(default_factory=set)
    request_permissions_call_ids: Set[str] = field(default_factory=set)
    request_permissions_call_ids_by_turn_id: Dict[str, List[str]] = field(default_factory=dict)
    request_user_input_call_ids: Set[str] = field(default_factory=set)
    request_user_input_call_ids_by_turn_id: Dict[str, List[str]] = field(default_factory=dict)
    pending_requests_by_request_id: Dict[Any, PendingInteractiveRequest] = field(default_factory=dict)

    @staticmethod
    def op_can_change_state(op: Union[AppCommand, Dict[str, Any], Any]) -> bool:
        return _coerce_op(op).kind in {
            "ExecApproval",
            "PatchApproval",
            "ResolveElicitation",
            "RequestPermissionsResponse",
            "UserInputAnswer",
            "Shutdown",
        }

    def note_outbound_op(self, op: Union[AppCommand, Dict[str, Any], Any]) -> None:
        op = _coerce_op(op)
        if op.kind == "ExecApproval" and op.id is not None:
            self.exec_approval_call_ids.discard(op.id)
            if op.turn_id is not None:
                self.remove_call_id_from_turn_map_entry(self.exec_approval_call_ids_by_turn_id, op.turn_id, op.id)
            self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.EXEC_APPROVAL and p.approval_id == op.id))
        elif op.kind == "PatchApproval" and op.id is not None:
            self.patch_approval_call_ids.discard(op.id)
            self.remove_call_id_from_turn_map(self.patch_approval_call_ids_by_turn_id, op.id)
            self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.PATCH_APPROVAL and p.item_id == op.id))
        elif op.kind == "ResolveElicitation" and op.server_name is not None:
            key = ElicitationRequestKey.new(op.server_name, op.request_id)
            self.elicitation_requests.discard(key)
            self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.ELICITATION and p.elicitation_key == key))
        elif op.kind == "RequestPermissionsResponse" and op.id is not None:
            self.request_permissions_call_ids.discard(op.id)
            self.remove_call_id_from_turn_map(self.request_permissions_call_ids_by_turn_id, op.id)
            self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.REQUEST_PERMISSIONS and p.item_id == op.id))
        elif op.kind == "UserInputAnswer" and op.id is not None:
            call_ids = self.request_user_input_call_ids_by_turn_id.get(op.id)
            if call_ids:
                call_id = call_ids.pop(0)
                self.request_user_input_call_ids.discard(call_id)
                self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.REQUEST_USER_INPUT and p.item_id == call_id))
                if not call_ids:
                    self.request_user_input_call_ids_by_turn_id.pop(op.id, None)
        elif op.kind == "Shutdown":
            self.clear()

    def note_server_request(self, request: Union[ServerRequest, Dict[str, Any], Any]) -> None:
        request = _coerce_request(request)
        p = request.params
        if request.kind == "CommandExecutionRequestApproval":
            approval_id, turn_id = str(p.get("approval_id") or p.get("item_id")), str(p.get("turn_id"))
            self.exec_approval_call_ids.add(approval_id)
            self.exec_approval_call_ids_by_turn_id.setdefault(turn_id, []).append(approval_id)
            self.pending_requests_by_request_id[request.request_id] = PendingInteractiveRequest(PendingInteractiveRequestKind.EXEC_APPROVAL, turn_id=turn_id, approval_id=approval_id)
        elif request.kind == "FileChangeRequestApproval":
            item_id, turn_id = str(p.get("item_id")), str(p.get("turn_id"))
            self.patch_approval_call_ids.add(item_id)
            self.patch_approval_call_ids_by_turn_id.setdefault(turn_id, []).append(item_id)
            self.pending_requests_by_request_id[request.request_id] = PendingInteractiveRequest(PendingInteractiveRequestKind.PATCH_APPROVAL, turn_id=turn_id, item_id=item_id)
        elif request.kind == "McpServerElicitationRequest":
            key = ElicitationRequestKey.new(str(p.get("server_name")), request.request_id)
            self.elicitation_requests.add(key)
            self.pending_requests_by_request_id[request.request_id] = PendingInteractiveRequest(PendingInteractiveRequestKind.ELICITATION, elicitation_key=key)
        elif request.kind == "ToolRequestUserInput":
            item_id, turn_id = str(p.get("item_id")), str(p.get("turn_id"))
            self.request_user_input_call_ids.add(item_id)
            self.request_user_input_call_ids_by_turn_id.setdefault(turn_id, []).append(item_id)
            self.pending_requests_by_request_id[request.request_id] = PendingInteractiveRequest(PendingInteractiveRequestKind.REQUEST_USER_INPUT, turn_id=turn_id, item_id=item_id)
        elif request.kind == "PermissionsRequestApproval":
            item_id, turn_id = str(p.get("item_id")), str(p.get("turn_id"))
            self.request_permissions_call_ids.add(item_id)
            self.request_permissions_call_ids_by_turn_id.setdefault(turn_id, []).append(item_id)
            self.pending_requests_by_request_id[request.request_id] = PendingInteractiveRequest(PendingInteractiveRequestKind.REQUEST_PERMISSIONS, turn_id=turn_id, item_id=item_id)

    def note_server_notification(self, notification: Union[ServerNotification, Dict[str, Any], Any]) -> None:
        notification = _coerce_notification(notification)
        if notification.kind == "ItemStarted" and notification.item:
            item_id = str(notification.item.get("id"))
            if notification.item.get("kind") == "CommandExecution":
                self.exec_approval_call_ids.discard(item_id)
                self.remove_call_id_from_turn_map(self.exec_approval_call_ids_by_turn_id, item_id)
            elif notification.item.get("kind") == "FileChange":
                self.patch_approval_call_ids.discard(item_id)
                self.remove_call_id_from_turn_map(self.patch_approval_call_ids_by_turn_id, item_id)
        elif notification.kind == "TurnCompleted" and notification.turn_id is not None:
            self.clear_exec_approval_turn(notification.turn_id)
            self.clear_patch_approval_turn(notification.turn_id)
            self.clear_request_permissions_turn(notification.turn_id)
            self.clear_request_user_input_turn(notification.turn_id)
        elif notification.kind == "ServerRequestResolved":
            self.remove_request(notification.request_id)
        elif notification.kind == "ThreadClosed":
            self.clear()

    def note_evicted_server_request(self, request: Union[ServerRequest, Dict[str, Any], Any]) -> None:
        request = _coerce_request(request)
        p = request.params
        if request.kind == "CommandExecutionRequestApproval":
            approval_id = str(p.get("approval_id") or p.get("item_id"))
            self.exec_approval_call_ids.discard(approval_id)
            self.remove_call_id_from_turn_map_entry(self.exec_approval_call_ids_by_turn_id, str(p.get("turn_id")), approval_id)
        elif request.kind == "FileChangeRequestApproval":
            self.patch_approval_call_ids.discard(str(p.get("item_id")))
            self.remove_call_id_from_turn_map_entry(self.patch_approval_call_ids_by_turn_id, str(p.get("turn_id")), str(p.get("item_id")))
        elif request.kind == "McpServerElicitationRequest":
            self.elicitation_requests.discard(ElicitationRequestKey.new(str(p.get("server_name")), request.request_id))
        elif request.kind == "ToolRequestUserInput":
            self.request_user_input_call_ids.discard(str(p.get("item_id")))
            self.remove_call_id_from_turn_map_entry(self.request_user_input_call_ids_by_turn_id, str(p.get("turn_id")), str(p.get("item_id")))
        elif request.kind == "PermissionsRequestApproval":
            self.request_permissions_call_ids.discard(str(p.get("item_id")))
            self.remove_call_id_from_turn_map_entry(self.request_permissions_call_ids_by_turn_id, str(p.get("turn_id")), str(p.get("item_id")))
        self._retain_pending(lambda pending: not self.request_matches_server_request(pending, request))

    def should_replay_snapshot_request(self, request: Union[ServerRequest, Dict[str, Any], Any]) -> bool:
        request = _coerce_request(request)
        p = request.params
        if request.kind == "CommandExecutionRequestApproval":
            return str(p.get("approval_id") or p.get("item_id")) in self.exec_approval_call_ids
        if request.kind == "FileChangeRequestApproval":
            return str(p.get("item_id")) in self.patch_approval_call_ids
        if request.kind == "McpServerElicitationRequest":
            return ElicitationRequestKey.new(str(p.get("server_name")), request.request_id) in self.elicitation_requests
        if request.kind == "ToolRequestUserInput":
            return str(p.get("item_id")) in self.request_user_input_call_ids
        if request.kind == "PermissionsRequestApproval":
            return str(p.get("item_id")) in self.request_permissions_call_ids
        return True

    def has_pending_thread_approvals(self) -> bool:
        return bool(self.exec_approval_call_ids or self.patch_approval_call_ids or self.elicitation_requests or self.request_permissions_call_ids)

    def has_pending_thread_user_input(self) -> bool:
        return bool(self.request_user_input_call_ids)

    def clear_request_user_input_turn(self, turn_id: str) -> None:
        for call_id in self.request_user_input_call_ids_by_turn_id.pop(turn_id, []):
            self.request_user_input_call_ids.discard(call_id)
        self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.REQUEST_USER_INPUT and p.turn_id == turn_id))

    def clear_request_permissions_turn(self, turn_id: str) -> None:
        for call_id in self.request_permissions_call_ids_by_turn_id.pop(turn_id, []):
            self.request_permissions_call_ids.discard(call_id)
        self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.REQUEST_PERMISSIONS and p.turn_id == turn_id))

    def clear_exec_approval_turn(self, turn_id: str) -> None:
        for call_id in self.exec_approval_call_ids_by_turn_id.pop(turn_id, []):
            self.exec_approval_call_ids.discard(call_id)
        self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.EXEC_APPROVAL and p.turn_id == turn_id))

    def clear_patch_approval_turn(self, turn_id: str) -> None:
        for call_id in self.patch_approval_call_ids_by_turn_id.pop(turn_id, []):
            self.patch_approval_call_ids.discard(call_id)
        self._retain_pending(lambda p: not (p.kind == PendingInteractiveRequestKind.PATCH_APPROVAL and p.turn_id == turn_id))

    @staticmethod
    def remove_call_id_from_turn_map(call_ids_by_turn_id: Dict[str, List[str]], call_id: str) -> None:
        for turn_id in list(call_ids_by_turn_id):
            call_ids_by_turn_id[turn_id] = [queued for queued in call_ids_by_turn_id[turn_id] if queued != call_id]
            if not call_ids_by_turn_id[turn_id]:
                del call_ids_by_turn_id[turn_id]

    @staticmethod
    def remove_call_id_from_turn_map_entry(call_ids_by_turn_id: Dict[str, List[str]], turn_id: str, call_id: str) -> None:
        if turn_id not in call_ids_by_turn_id:
            return
        call_ids_by_turn_id[turn_id] = [queued for queued in call_ids_by_turn_id[turn_id] if queued != call_id]
        if not call_ids_by_turn_id[turn_id]:
            del call_ids_by_turn_id[turn_id]

    def clear(self) -> None:
        self.exec_approval_call_ids.clear()
        self.exec_approval_call_ids_by_turn_id.clear()
        self.patch_approval_call_ids.clear()
        self.patch_approval_call_ids_by_turn_id.clear()
        self.elicitation_requests.clear()
        self.request_permissions_call_ids.clear()
        self.request_permissions_call_ids_by_turn_id.clear()
        self.request_user_input_call_ids.clear()
        self.request_user_input_call_ids_by_turn_id.clear()
        self.pending_requests_by_request_id.clear()

    def remove_request(self, request_id: Any) -> None:
        pending = self.pending_requests_by_request_id.pop(request_id, None)
        if pending is None:
            return
        if pending.kind == PendingInteractiveRequestKind.EXEC_APPROVAL and pending.approval_id is not None:
            self.exec_approval_call_ids.discard(pending.approval_id)
            self.remove_call_id_from_turn_map_entry(self.exec_approval_call_ids_by_turn_id, pending.turn_id or "", pending.approval_id)
        elif pending.kind == PendingInteractiveRequestKind.PATCH_APPROVAL and pending.item_id is not None:
            self.patch_approval_call_ids.discard(pending.item_id)
            self.remove_call_id_from_turn_map_entry(self.patch_approval_call_ids_by_turn_id, pending.turn_id or "", pending.item_id)
        elif pending.kind == PendingInteractiveRequestKind.ELICITATION and pending.elicitation_key is not None:
            self.elicitation_requests.discard(pending.elicitation_key)
        elif pending.kind == PendingInteractiveRequestKind.REQUEST_PERMISSIONS and pending.item_id is not None:
            self.request_permissions_call_ids.discard(pending.item_id)
            self.remove_call_id_from_turn_map_entry(self.request_permissions_call_ids_by_turn_id, pending.turn_id or "", pending.item_id)
        elif pending.kind == PendingInteractiveRequestKind.REQUEST_USER_INPUT and pending.item_id is not None:
            self.request_user_input_call_ids.discard(pending.item_id)
            self.remove_call_id_from_turn_map_entry(self.request_user_input_call_ids_by_turn_id, pending.turn_id or "", pending.item_id)

    @staticmethod
    def request_matches_server_request(pending: PendingInteractiveRequest, request: Union[ServerRequest, Dict[str, Any], Any]) -> bool:
        request = _coerce_request(request)
        p = request.params
        if pending.kind == PendingInteractiveRequestKind.EXEC_APPROVAL and request.kind == "CommandExecutionRequestApproval":
            return pending.turn_id == str(p.get("turn_id")) and pending.approval_id == str(p.get("approval_id") or p.get("item_id"))
        if pending.kind == PendingInteractiveRequestKind.PATCH_APPROVAL and request.kind == "FileChangeRequestApproval":
            return pending.turn_id == str(p.get("turn_id")) and pending.item_id == str(p.get("item_id"))
        if pending.kind == PendingInteractiveRequestKind.ELICITATION and request.kind == "McpServerElicitationRequest":
            return pending.elicitation_key == ElicitationRequestKey.new(str(p.get("server_name")), request.request_id)
        if pending.kind == PendingInteractiveRequestKind.REQUEST_PERMISSIONS and request.kind == "PermissionsRequestApproval":
            return pending.turn_id == str(p.get("turn_id")) and pending.item_id == str(p.get("item_id"))
        if pending.kind == PendingInteractiveRequestKind.REQUEST_USER_INPUT and request.kind == "ToolRequestUserInput":
            return pending.turn_id == str(p.get("turn_id")) and pending.item_id == str(p.get("item_id"))
        return False

    def _retain_pending(self, predicate: Callable[[PendingInteractiveRequest], bool]) -> None:
        self.pending_requests_by_request_id = {key: pending for key, pending in self.pending_requests_by_request_id.items() if predicate(pending)}


class ThreadEventStore:
    def __init__(self, capacity: int = 8):
        self.capacity = capacity
        self.events: List[Union[ServerRequest, ServerNotification]] = []
        self.pending_interactive_replay = PendingInteractiveReplayState()

    @classmethod
    def new(cls, capacity: int) -> "ThreadEventStore":
        return cls(capacity)

    def push_request(self, request: Union[ServerRequest, Dict[str, Any], Any]) -> None:
        request = _coerce_request(request)
        self.pending_interactive_replay.note_server_request(request)
        self._push(request)

    def push_notification(self, notification: Union[ServerNotification, Dict[str, Any], Any]) -> None:
        notification = _coerce_notification(notification)
        self.pending_interactive_replay.note_server_notification(notification)
        self._push(notification)

    def note_outbound_op(self, op: Union[AppCommand, Dict[str, Any], Any]) -> None:
        self.pending_interactive_replay.note_outbound_op(op)

    def snapshot(self) -> "ThreadEventSnapshot":
        events = [event for event in self.events if not isinstance(event, ServerRequest) or self.pending_interactive_replay.should_replay_snapshot_request(event)]
        return ThreadEventSnapshot(events)

    def has_pending_thread_approvals(self) -> bool:
        return self.pending_interactive_replay.has_pending_thread_approvals()

    def has_pending_thread_user_input(self) -> bool:
        return self.pending_interactive_replay.has_pending_thread_user_input()

    def _push(self, event: Union[ServerRequest, ServerNotification]) -> None:
        self.events.append(event)
        if len(self.events) > self.capacity:
            evicted = self.events.pop(0)
            if isinstance(evicted, ServerRequest):
                self.pending_interactive_replay.note_evicted_server_request(evicted)


@dataclass(frozen=True)
class ThreadEventSnapshot:
    events: List[Union[ServerRequest, ServerNotification]]


def request_user_input_request(call_id: str, turn_id: str, request_id: Any = 1) -> ServerRequest:
    return ServerRequest("ToolRequestUserInput", request_id, {"turn_id": turn_id, "item_id": call_id})


def exec_approval_request(call_id: str, approval_id: Optional[str] = None, turn_id: str = "turn-1", request_id: Any = 2) -> ServerRequest:
    return ServerRequest("CommandExecutionRequestApproval", request_id, {"turn_id": turn_id, "item_id": call_id, "approval_id": approval_id})


def patch_approval_request(call_id: str, turn_id: str, request_id: Any = 3) -> ServerRequest:
    return ServerRequest("FileChangeRequestApproval", request_id, {"turn_id": turn_id, "item_id": call_id})


def permissions_request(call_id: str, turn_id: str, request_id: Any = 4) -> ServerRequest:
    return ServerRequest("PermissionsRequestApproval", request_id, {"turn_id": turn_id, "item_id": call_id})


def elicitation_request(server_name: str, request_id: str, turn_id: str = "turn-1") -> ServerRequest:
    return ServerRequest("McpServerElicitationRequest", request_id, {"turn_id": turn_id, "server_name": server_name})


def turn_completed(turn_id: str) -> ServerNotification:
    return ServerNotification("TurnCompleted", turn_id=turn_id)


def thread_closed() -> ServerNotification:
    return ServerNotification("ThreadClosed")


def request_resolved(request_id: Any) -> ServerNotification:
    return ServerNotification("ServerRequestResolved", request_id=request_id)


def exec_started(item_id: str) -> ServerNotification:
    return ServerNotification("ItemStarted", item={"kind": "CommandExecution", "id": item_id})


def thread_event_snapshot_keeps_pending_request_user_input() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(request_user_input_request("call-1", "turn-1"))
    return len(store.snapshot().events) == 1


def thread_event_snapshot_drops_resolved_request_user_input_after_user_answer() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(request_user_input_request("call-1", "turn-1"))
    store.note_outbound_op(AppCommand("UserInputAnswer", id="turn-1"))
    return store.snapshot().events == []


def thread_event_snapshot_drops_resolved_request_user_input_after_server_resolution() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(request_user_input_request("call-1", "turn-1"))
    store.push_notification(request_resolved(1))
    return all(not (isinstance(event, ServerRequest) and event.kind == "ToolRequestUserInput") for event in store.snapshot().events)


def thread_event_snapshot_drops_resolved_exec_approval_after_outbound_approval_id() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(exec_approval_request("call-1", "approval-1", "turn-1"))
    store.note_outbound_op(AppCommand("ExecApproval", id="approval-1", turn_id="turn-1"))
    return store.snapshot().events == []


def thread_event_snapshot_drops_resolved_exec_approval_after_server_resolution() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(exec_approval_request("call-1", "approval-1", "turn-1"))
    store.push_notification(request_resolved(2))
    return all(not (isinstance(event, ServerRequest) and event.kind == "CommandExecutionRequestApproval") for event in store.snapshot().events)


def thread_event_snapshot_drops_answered_request_user_input_for_multi_prompt_turn() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(request_user_input_request("call-1", "turn-1"))
    store.note_outbound_op(AppCommand("UserInputAnswer", id="turn-1"))
    store.push_request(request_user_input_request("call-2", "turn-1"))
    events = store.snapshot().events
    return len(events) == 1 and isinstance(events[0], ServerRequest) and events[0].params["item_id"] == "call-2"


def thread_event_snapshot_keeps_newer_request_user_input_pending_when_same_turn_has_queue() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(request_user_input_request("call-1", "turn-1"))
    store.push_request(request_user_input_request("call-2", "turn-1"))
    store.note_outbound_op(AppCommand("UserInputAnswer", id="turn-1"))
    events = store.snapshot().events
    return len(events) == 1 and isinstance(events[0], ServerRequest) and events[0].params["item_id"] == "call-2"


def thread_event_snapshot_drops_resolved_patch_approval_after_outbound_approval() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(patch_approval_request("call-1", "turn-1"))
    store.note_outbound_op(AppCommand("PatchApproval", id="call-1"))
    return store.snapshot().events == []


def thread_event_snapshot_drops_pending_approvals_when_turn_completes() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(exec_approval_request("exec-call-1", "approval-1", "turn-1"))
    store.push_request(patch_approval_request("patch-call-1", "turn-1"))
    store.push_notification(turn_completed("turn-1"))
    return all(not (isinstance(event, ServerRequest) and event.kind in {"CommandExecutionRequestApproval", "FileChangeRequestApproval"}) for event in store.snapshot().events)


def thread_event_snapshot_drops_resolved_elicitation_after_outbound_resolution() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(elicitation_request("server-1", "request-1", "turn-1"))
    store.note_outbound_op(AppCommand("ResolveElicitation", server_name="server-1", request_id="request-1"))
    return store.snapshot().events == []


def thread_event_store_reports_pending_thread_approvals() -> bool:
    store = ThreadEventStore.new(8)
    before = store.has_pending_thread_approvals()
    store.push_request(exec_approval_request("call-1", None, "turn-1"))
    during = store.has_pending_thread_approvals()
    store.note_outbound_op(AppCommand("ExecApproval", id="call-1", turn_id="turn-1"))
    return before is False and during is True and store.has_pending_thread_approvals() is False


def request_user_input_does_not_count_as_pending_thread_approval() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(request_user_input_request("call-1", "turn-1"))
    return store.has_pending_thread_approvals() is False and store.has_pending_thread_user_input() is True


def thread_event_snapshot_drops_pending_requests_when_thread_closes() -> bool:
    store = ThreadEventStore.new(8)
    store.push_request(exec_approval_request("call-1", None, "turn-1"))
    store.push_notification(thread_closed())
    return all(not (isinstance(event, ServerRequest) and event.kind == "CommandExecutionRequestApproval") for event in store.snapshot().events)


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
        return ServerNotification(str(notification.get("kind") or notification.get("type")), request_id=notification.get("request_id"), turn_id=notification.get("turn_id"), item=notification.get("item"))
    return ServerNotification(str(getattr(notification, "kind", getattr(notification, "type", notification.__class__.__name__))), request_id=getattr(notification, "request_id", None), turn_id=getattr(notification, "turn_id", None), item=getattr(notification, "item", None))


def _coerce_op(op: Union[AppCommand, Dict[str, Any], Any]) -> AppCommand:
    if isinstance(op, AppCommand):
        return op
    if isinstance(op, dict):
        return AppCommand(str(op.get("kind") or op.get("type")), id=op.get("id"), turn_id=op.get("turn_id"), server_name=op.get("server_name"), request_id=op.get("request_id"))
    return AppCommand(str(getattr(op, "kind", getattr(op, "type", op.__class__.__name__))), id=getattr(op, "id", None), turn_id=getattr(op, "turn_id", None), server_name=getattr(op, "server_name", None), request_id=getattr(op, "request_id", None))


__all__ = [name for name in globals() if not name.startswith("_")]
