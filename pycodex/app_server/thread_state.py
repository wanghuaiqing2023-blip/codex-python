"""Thread state bookkeeping ported from ``app-server/src/thread_state.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from weakref import ref

from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server_protocol import RequestId, ThreadHistoryBuilder, Turn, TurnError


@dataclass(frozen=True)
class PendingThreadResumeRequest:
    request_id: ConnectionRequestId
    history_items: tuple[Any, ...]
    config_snapshot: Any
    instruction_sources: tuple[Any, ...]
    thread_summary: Any
    emit_thread_goal_update: bool
    thread_goal_state_db: Any = None
    include_turns: bool = False
    redact_resume_payloads: bool = False


@dataclass(frozen=True)
class ThreadListenerCommand:
    kind: str
    request: PendingThreadResumeRequest | None = None
    goal: Any = None
    state_db: Any = None
    request_id: RequestId | None = None
    completion: asyncio.Future[None] | None = None

    @classmethod
    def send_thread_resume_response(cls, request: PendingThreadResumeRequest) -> "ThreadListenerCommand":
        return cls("SendThreadResumeResponse", request=request)

    @classmethod
    def emit_thread_goal_updated(cls, goal: Any) -> "ThreadListenerCommand":
        return cls("EmitThreadGoalUpdated", goal=goal)

    @classmethod
    def emit_thread_goal_cleared(cls) -> "ThreadListenerCommand":
        return cls("EmitThreadGoalCleared")

    @classmethod
    def emit_thread_goal_snapshot(cls, state_db: Any) -> "ThreadListenerCommand":
        return cls("EmitThreadGoalSnapshot", state_db=state_db)

    @classmethod
    def resolve_server_request(cls, request_id: RequestId | str | int, completion: asyncio.Future[None]) -> "ThreadListenerCommand":
        return cls("ResolveServerRequest", request_id=RequestId.from_value(request_id), completion=completion)


@dataclass
class ListenerCommandSink:
    commands: list[ThreadListenerCommand] = field(default_factory=list)
    closed: bool = False
    auto_complete_resolutions: bool = True

    def send(self, command: ThreadListenerCommand) -> bool:
        if self.closed:
            return False
        self.commands.append(command)
        if self.auto_complete_resolutions and command.completion is not None and not command.completion.done():
            command.completion.set_result(None)
        return True

    def close(self) -> None:
        self.closed = True


@dataclass
class CancellationSender:
    canceled: bool = False

    def send(self, value: Any = None) -> bool:
        del value
        if self.canceled:
            return False
        self.canceled = True
        return True


@dataclass
class TurnSummary:
    started_at: int | None = None
    command_execution_started: set[str] = field(default_factory=set)
    last_error: TurnError | None = None


@dataclass
class ThreadState:
    pending_interrupts: list[ConnectionRequestId] = field(default_factory=list)
    pending_rollbacks: ConnectionRequestId | None = None
    turn_summary: TurnSummary = field(default_factory=TurnSummary)
    last_terminal_turn_id: str | None = None
    cancel_tx: CancellationSender | None = None
    experimental_raw_events: bool = False
    listener_generation: int = 0
    last_thread_settings: Any = None
    listener_command_tx: ListenerCommandSink | None = None
    current_turn_history: ThreadHistoryBuilder = field(default_factory=ThreadHistoryBuilder)
    listener_thread: Any = None
    watch_registration: Any = None

    def listener_matches(self, conversation: Any) -> bool:
        existing = self.listener_thread() if callable(self.listener_thread) else self.listener_thread
        return existing is conversation

    def set_listener(
        self,
        cancel_tx: CancellationSender,
        conversation: Any,
        watch_registration: Any,
        thread_settings_baseline: Any,
    ) -> tuple[ListenerCommandSink, int]:
        if self.cancel_tx is not None:
            self.cancel_tx.send(())
        self.cancel_tx = cancel_tx
        self.listener_generation = (self.listener_generation + 1) % (2**64)
        self.last_thread_settings = thread_settings_baseline
        listener_command_tx = ListenerCommandSink()
        self.listener_command_tx = listener_command_tx
        try:
            self.listener_thread = ref(conversation)
        except TypeError:
            self.listener_thread = conversation
        self.watch_registration = watch_registration
        return listener_command_tx, self.listener_generation

    def clear_listener(self) -> None:
        if self.cancel_tx is not None:
            self.cancel_tx.send(())
        self.cancel_tx = None
        if self.listener_command_tx is not None:
            self.listener_command_tx.close()
        self.listener_command_tx = None
        self.current_turn_history.reset()
        self.listener_thread = None
        self.watch_registration = None

    def set_experimental_raw_events(self, enabled: bool) -> None:
        self.experimental_raw_events = bool(enabled)

    def listener_command_sender(self) -> ListenerCommandSink | None:
        return self.listener_command_tx

    def active_turn_snapshot(self) -> Turn | None:
        return self.current_turn_history.active_turn_snapshot()

    def track_current_turn_event(self, event_turn_id: str, event: Any) -> None:
        event_type, payload = _event_parts(event)
        if event_type in {"turn_started", "task_started"}:
            self.turn_summary.started_at = _get(payload, "started_at", "startedAt")
        self.current_turn_history.handle_event(event)
        if event_type in {"turn_aborted", "task_complete", "turn_complete"} and not self.current_turn_history.has_active_turn():
            self.last_terminal_turn_id = str(event_turn_id)
            self.current_turn_history.reset()

    def note_thread_settings(self, thread_settings: Any) -> bool:
        changed = self.last_thread_settings != thread_settings
        self.last_thread_settings = thread_settings
        return changed


@dataclass
class ConnectionCapabilities:
    request_attestation: bool = False


@dataclass
class HasConnectionsWatcher:
    current: bool = False
    history: list[bool] = field(default_factory=list)

    def send_if_modified(self, value: bool) -> bool:
        if self.current == value:
            return False
        self.current = value
        self.history.append(value)
        return True

    def subscribe(self) -> "HasConnectionsWatcher":
        return self


@dataclass
class ThreadEntry:
    state: ThreadState = field(default_factory=ThreadState)
    connection_ids: set[Any] = field(default_factory=set)
    has_connections_watcher: HasConnectionsWatcher = field(default_factory=HasConnectionsWatcher)

    def update_has_connections(self) -> None:
        self.has_connections_watcher.send_if_modified(bool(self.connection_ids))


class ThreadStateManager:
    def __init__(self) -> None:
        self.live_connections: dict[Any, ConnectionCapabilities] = {}
        self.threads: dict[Any, ThreadEntry] = {}
        self.thread_ids_by_connection: dict[Any, set[Any]] = {}

    @classmethod
    def new(cls) -> "ThreadStateManager":
        return cls()

    async def connection_initialized(self, connection_id: Any, capabilities: ConnectionCapabilities) -> None:
        self.live_connections[connection_id] = capabilities

    async def first_attestation_capable_connection_for_thread(self, thread_id: Any) -> Any | None:
        entry = self.threads.get(thread_id)
        if entry is None:
            return None
        capable = [
            connection_id
            for connection_id in entry.connection_ids
            if self.live_connections.get(connection_id, ConnectionCapabilities()).request_attestation
        ]
        return min(capable, key=_connection_sort_key) if capable else None

    async def subscribed_connection_ids(self, thread_id: Any) -> list[Any]:
        entry = self.threads.get(thread_id)
        return list(entry.connection_ids) if entry is not None else []

    async def thread_state(self, thread_id: Any) -> ThreadState:
        return self.threads.setdefault(thread_id, ThreadEntry()).state

    async def remove_thread_state(self, thread_id: Any) -> None:
        entry = self.threads.pop(thread_id, None)
        for connection_id, thread_ids in list(self.thread_ids_by_connection.items()):
            thread_ids.discard(thread_id)
            if not thread_ids:
                self.thread_ids_by_connection.pop(connection_id, None)
        if entry is not None:
            entry.state.clear_listener()

    async def clear_all_listeners(self) -> None:
        for entry in self.threads.values():
            entry.state.clear_listener()

    async def unsubscribe_connection_from_thread(self, thread_id: Any, connection_id: Any) -> bool:
        if thread_id not in self.threads:
            return False
        if thread_id not in self.thread_ids_by_connection.get(connection_id, set()):
            return False
        thread_ids = self.thread_ids_by_connection.get(connection_id)
        if thread_ids is not None:
            thread_ids.discard(thread_id)
            if not thread_ids:
                self.thread_ids_by_connection.pop(connection_id, None)
        entry = self.threads[thread_id]
        entry.connection_ids.discard(connection_id)
        entry.update_has_connections()
        return True

    async def has_subscribers(self, thread_id: Any) -> bool:
        entry = self.threads.get(thread_id)
        return entry is not None and bool(entry.connection_ids)

    async def try_ensure_connection_subscribed(
        self,
        thread_id: Any,
        connection_id: Any,
        experimental_raw_events: bool,
    ) -> ThreadState | None:
        if connection_id not in self.live_connections:
            return None
        self.thread_ids_by_connection.setdefault(connection_id, set()).add(thread_id)
        entry = self.threads.setdefault(thread_id, ThreadEntry())
        entry.connection_ids.add(connection_id)
        entry.update_has_connections()
        if experimental_raw_events:
            entry.state.set_experimental_raw_events(True)
        return entry.state

    async def try_add_connection_to_thread(self, thread_id: Any, connection_id: Any) -> bool:
        if connection_id not in self.live_connections:
            return False
        self.thread_ids_by_connection.setdefault(connection_id, set()).add(thread_id)
        entry = self.threads.setdefault(thread_id, ThreadEntry())
        entry.connection_ids.add(connection_id)
        entry.update_has_connections()
        return True

    async def remove_connection(self, connection_id: Any) -> list[Any]:
        self.live_connections.pop(connection_id, None)
        thread_ids = self.thread_ids_by_connection.pop(connection_id, set())
        empty_threads: list[Any] = []
        for thread_id in thread_ids:
            entry = self.threads.get(thread_id)
            if entry is None:
                continue
            entry.connection_ids.discard(connection_id)
            entry.update_has_connections()
            if not entry.connection_ids:
                empty_threads.append(thread_id)
        return empty_threads

    async def subscribe_to_has_connections(self, thread_id: Any) -> HasConnectionsWatcher | None:
        entry = self.threads.get(thread_id)
        return entry.has_connections_watcher.subscribe() if entry is not None else None


async def resolve_server_request_on_thread_listener(thread_state: ThreadState, request_id: RequestId | str | int) -> None:
    completion: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    listener_command_tx = thread_state.listener_command_sender()
    if listener_command_tx is None:
        return
    ok = listener_command_tx.send(ThreadListenerCommand.resolve_server_request(request_id, completion))
    if not ok:
        return
    await completion


def _event_parts(event: Any) -> tuple[str, Any]:
    event_type = getattr(event, "type", None) or getattr(event, "kind", None)
    payload = getattr(event, "payload", None)
    if event_type is not None:
        return str(event_type), payload
    if isinstance(event, dict):
        event_type = event.get("type") or event.get("kind")
        payload = event.get("payload", event)
        return str(event_type), payload
    return str(event), None


def _get(value: Any, *names: str) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        attr = getattr(value, name, None)
        if attr is not None:
            return attr
    return None


def _connection_sort_key(connection_id: Any) -> Any:
    return getattr(connection_id, "value", getattr(connection_id, "id", connection_id))


__all__ = [
    "CancellationSender",
    "ConnectionCapabilities",
    "HasConnectionsWatcher",
    "ListenerCommandSink",
    "PendingThreadResumeRequest",
    "ThreadEntry",
    "ThreadListenerCommand",
    "ThreadState",
    "ThreadStateManager",
    "TurnSummary",
    "resolve_server_request_on_thread_listener",
]
