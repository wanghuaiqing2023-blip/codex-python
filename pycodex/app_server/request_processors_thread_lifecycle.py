"""Thread lifecycle helpers ported from ``app-server/src/request_processors/thread_lifecycle.rs``."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Iterable, MutableSet
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from pycodex.app_server.error_code import invalid_request
from pycodex.app_server.request_processors import build_api_turns_from_rollout_items
from pycodex.app_server.request_processors_thread_goal_processor import (
    api_thread_goal_from_state,
)
from pycodex.app_server.thread_state import (
    CancellationSender,
    PendingThreadResumeRequest,
    ThreadListenerCommand,
)
from pycodex.app_server.thread_status import resolve_thread_status
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    ServerNotification,
    ServerRequestResolvedNotification,
    Thread,
    ThreadClosedNotification,
    ThreadGoalClearedNotification,
    ThreadGoalUpdatedNotification,
    ThreadResumeResponse,
    ThreadStatus,
    Turn,
    TurnStatus,
)

THREAD_UNLOADING_DELAY = 30 * 60
THREAD_SHUTDOWN_TIMEOUT = 10


@dataclass
class ThreadLifecycleError(Exception):
    error: JSONRPCErrorError

    def __post_init__(self) -> None:
        Exception.__init__(self, self.error.message)

    @property
    def message(self) -> str:
        return self.error.message


@dataclass
class ListenerTaskContext:
    thread_manager: Any
    thread_state_manager: Any
    outgoing: Any
    pending_thread_unloads: MutableSet[Any]
    thread_watch_manager: Any
    thread_list_state_permit: Any = None
    fallback_model_provider: str = ""
    codex_home: Any = None
    skills_watcher: Any = None


@dataclass
class UnloadingState:
    delay: float
    has_subscribers: tuple[bool, float]
    is_active: tuple[bool, float]

    @classmethod
    def new(
        cls,
        *,
        has_subscribers: bool,
        is_active: bool,
        delay: float = THREAD_UNLOADING_DELAY,
        now: float | None = None,
    ) -> "UnloadingState":
        timestamp = _now(now)
        return cls(delay, (bool(has_subscribers), timestamp), (bool(is_active), timestamp))

    def unloading_target(self) -> float | None:
        if not self.has_subscribers[0] and not self.is_active[0]:
            return max(self.has_subscribers[1], self.is_active[1]) + self.delay
        return None

    def sync_values(self, *, has_subscribers: bool, is_active: bool, now: float | None = None) -> None:
        timestamp = _now(now)
        if self.has_subscribers[0] != bool(has_subscribers):
            self.has_subscribers = (bool(has_subscribers), timestamp)
        if self.is_active[0] != bool(is_active):
            self.is_active = (bool(is_active), timestamp)

    def should_unload_now(self, *, now: float | None = None) -> bool:
        target = self.unloading_target()
        return target is not None and target <= _now(now)

    def note_thread_activity_observed(self, *, now: float | None = None) -> None:
        if not self.is_active[0]:
            self.is_active = (False, _now(now))


class ThreadShutdownResult(str, Enum):
    COMPLETE = "Complete"
    SUBMIT_FAILED = "SubmitFailed"
    TIMED_OUT = "TimedOut"


class EnsureConversationListenerResult(str, Enum):
    ATTACHED = "Attached"
    CONNECTION_CLOSED = "ConnectionClosed"


async def ensure_conversation_listener(
    listener_task_context: ListenerTaskContext,
    conversation_id: Any,
    connection_id: Any,
    raw_events_enabled: bool,
) -> EnsureConversationListenerResult:
    try:
        conversation = await _maybe_await(listener_task_context.thread_manager.get_thread(conversation_id))
    except Exception as exc:
        raise ThreadLifecycleError(invalid_request(f"thread not found: {conversation_id}")) from exc

    if conversation_id in listener_task_context.pending_thread_unloads:
        raise ThreadLifecycleError(invalid_request(f"thread {conversation_id} is closing; retry after the thread is closed"))

    thread_state = await _maybe_await(
        listener_task_context.thread_state_manager.try_ensure_connection_subscribed(
            conversation_id,
            connection_id,
            raw_events_enabled,
        )
    )
    if thread_state is None:
        return EnsureConversationListenerResult.CONNECTION_CLOSED

    try:
        await ensure_listener_task_running(listener_task_context, conversation_id, conversation, thread_state)
    except ThreadLifecycleError:
        await _maybe_await(
            listener_task_context.thread_state_manager.unsubscribe_connection_from_thread(
                conversation_id,
                connection_id,
            )
        )
        raise
    return EnsureConversationListenerResult.ATTACHED


def log_listener_attach_result(
    result: EnsureConversationListenerResult | JSONRPCErrorError | Exception,
    thread_id: Any,
    connection_id: Any,
    thread_kind: str,
) -> dict[str, Any] | None:
    if result == EnsureConversationListenerResult.ATTACHED:
        return None
    if result == EnsureConversationListenerResult.CONNECTION_CLOSED:
        return {"level": "debug", "thread_id": str(thread_id), "connection_id": connection_id}
    message = getattr(result, "message", str(result))
    return {"level": "warn", "thread_id": str(thread_id), "thread_kind": thread_kind, "message": message}


async def ensure_listener_task_running(
    listener_task_context: ListenerTaskContext,
    conversation_id: Any,
    conversation: Any,
    thread_state: Any,
) -> None:
    has_connections = await _maybe_await(listener_task_context.thread_state_manager.subscribe_to_has_connections(conversation_id))
    status_subscription = await _maybe_await(listener_task_context.thread_watch_manager.subscribe(conversation_id))
    if has_connections is None or status_subscription is None:
        raise ThreadLifecycleError(invalid_request(f"thread {conversation_id} is closing; retry after the thread is closed"))

    if _call_or_get(thread_state, "listener_matches", conversation):
        return

    watch_registration = None
    if listener_task_context.skills_watcher is not None:
        registrar = getattr(listener_task_context.skills_watcher, "register_thread_config", None)
        if callable(registrar):
            watch_registration = await _maybe_await(registrar(_call_or_get(conversation, "config"), listener_task_context.thread_manager, ()))

    baseline = _call_or_get(conversation, "config_snapshot")
    setter = getattr(thread_state, "set_listener", None)
    if callable(setter):
        setter(CancellationSender(), conversation, watch_registration, baseline)


async def wait_for_thread_shutdown(thread: Any, timeout: float = THREAD_SHUTDOWN_TIMEOUT) -> ThreadShutdownResult:
    try:
        result = await asyncio.wait_for(_maybe_await(_call_or_get(thread, "shutdown_and_wait")), timeout=timeout)
    except asyncio.TimeoutError:
        return ThreadShutdownResult.TIMED_OUT
    except Exception:
        return ThreadShutdownResult.SUBMIT_FAILED
    return ThreadShutdownResult.COMPLETE if result is None or result is True else ThreadShutdownResult.SUBMIT_FAILED


async def unload_thread_without_subscribers(
    thread_manager: Any,
    outgoing: Any,
    pending_thread_unloads: MutableSet[Any],
    thread_state_manager: Any,
    thread_watch_manager: Any,
    thread_id: Any,
    thread: Any,
    *,
    shutdown_result: ThreadShutdownResult | None = None,
) -> ThreadShutdownResult:
    await _maybe_await(_call_or_get(outgoing, "cancel_requests_for_thread", thread_id, None))
    await _maybe_await(_call_or_get(thread_state_manager, "remove_thread_state", thread_id))
    result = shutdown_result or await wait_for_thread_shutdown(thread)
    if result is ThreadShutdownResult.COMPLETE:
        removed = await _maybe_await(_call_or_get(thread_manager, "remove_thread", thread_id))
        if removed is not None:
            await _maybe_await(_call_or_get(thread_watch_manager, "remove_thread", str(thread_id)))
            await _send_server_notification(
                outgoing,
                ServerNotification("ThreadClosed", ThreadClosedNotification(thread_id=str(thread_id))),
            )
        else:
            await _maybe_await(_call_or_get(thread_watch_manager, "remove_thread", str(thread_id)))
    pending_thread_unloads.discard(thread_id)
    return result


async def handle_thread_listener_command(
    conversation_id: Any,
    conversation: Any,
    codex_home: Any,
    thread_state_manager: Any,
    thread_state: Any,
    thread_watch_manager: Any,
    outgoing: Any,
    pending_thread_unloads: MutableSet[Any],
    listener_command: ThreadListenerCommand,
) -> None:
    del codex_home
    if listener_command.kind == "SendThreadResumeResponse" and listener_command.request is not None:
        await handle_pending_thread_resume_request(
            conversation_id,
            conversation,
            thread_state_manager,
            thread_state,
            thread_watch_manager,
            outgoing,
            pending_thread_unloads,
            listener_command.request,
        )
    elif listener_command.kind == "EmitThreadGoalUpdated":
        await _send_server_notification(
            outgoing,
            ServerNotification(
                "ThreadGoalUpdated",
                ThreadGoalUpdatedNotification(thread_id=str(conversation_id), turn_id=None, goal=listener_command.goal),
            ),
        )
    elif listener_command.kind == "EmitThreadGoalCleared":
        await _send_server_notification(
            outgoing,
            ServerNotification("ThreadGoalCleared", ThreadGoalClearedNotification(thread_id=str(conversation_id))),
        )
    elif listener_command.kind == "EmitThreadGoalSnapshot":
        await send_thread_goal_snapshot_notification(outgoing, conversation_id, listener_command.state_db)
    elif listener_command.kind == "ResolveServerRequest":
        await resolve_pending_server_request(conversation_id, thread_state_manager, outgoing, listener_command.request_id)
        if listener_command.completion is not None and not listener_command.completion.done():
            listener_command.completion.set_result(None)


async def handle_pending_thread_resume_request(
    conversation_id: Any,
    conversation: Any,
    thread_state_manager: Any,
    thread_state: Any,
    thread_watch_manager: Any,
    outgoing: Any,
    pending_thread_unloads: MutableSet[Any],
    pending: PendingThreadResumeRequest,
) -> None:
    active_turn = _call_or_get(thread_state, "active_turn_snapshot")
    agent_status = _call_or_get(conversation, "agent_status")
    has_live_in_progress_turn = _is_running_status(agent_status) or _is_turn_in_progress(active_turn)
    thread = pending.thread_summary
    if pending.include_turns:
        thread = populate_thread_turns_from_history(thread, pending.history_items, active_turn)
    loaded_status = await _maybe_await(thread_watch_manager.loaded_status_for_thread(thread.id))
    thread = set_thread_status_and_interrupt_stale_turns(thread, loaded_status, has_live_in_progress_turn)

    request_id = pending.request_id
    connection_id = getattr(request_id, "connection_id", None)
    if conversation_id in pending_thread_unloads:
        await _send_error(
            outgoing,
            request_id,
            invalid_request(f"thread {conversation_id} is closing; retry thread/resume after the thread is closed"),
        )
        return
    added = await _maybe_await(thread_state_manager.try_add_connection_to_thread(conversation_id, connection_id))
    if not added:
        return

    if pending.emit_thread_goal_update:
        await _maybe_await(_call_or_get(conversation, "apply_goal_resume_runtime_effects"))

    response = _thread_resume_response_from_pending(conversation, pending, thread)
    await _send_response(outgoing, request_id, response)
    if pending.emit_thread_goal_update and pending.thread_goal_state_db is not None:
        await send_thread_goal_snapshot_notification(outgoing, conversation_id, pending.thread_goal_state_db)
    await _maybe_await(_call_or_get(outgoing, "replay_requests_to_connection_for_thread", connection_id, conversation_id))
    if pending.emit_thread_goal_update:
        await _maybe_await(_call_or_get(conversation, "continue_active_goal_if_idle"))


async def send_thread_goal_snapshot_notification(outgoing: Any, thread_id: Any, state_db: Any) -> None:
    try:
        goal = await _maybe_await(_call_or_get(_call_or_get(state_db, "thread_goals"), "get_thread_goal", thread_id))
    except Exception:
        return
    if goal is not None:
        await _send_server_notification(
            outgoing,
            ServerNotification(
                "ThreadGoalUpdated",
                ThreadGoalUpdatedNotification(thread_id=str(thread_id), turn_id=None, goal=api_thread_goal_from_state(goal)),
            ),
        )
    else:
        await _send_server_notification(
            outgoing,
            ServerNotification("ThreadGoalCleared", ThreadGoalClearedNotification(thread_id=str(thread_id))),
        )


def populate_thread_turns_from_history(thread: Thread, items: Iterable[Any], active_turn: Turn | None = None) -> Thread:
    turns = build_api_turns_from_rollout_items(items)
    if active_turn is not None:
        turns = merge_turn_history_with_active_turn(turns, active_turn)
    return _replace_or_set(thread, turns=tuple(turns))


async def resolve_pending_server_request(
    conversation_id: Any,
    thread_state_manager: Any,
    outgoing: Any,
    request_id: Any,
) -> None:
    subscribed_connection_ids = await _maybe_await(thread_state_manager.subscribed_connection_ids(conversation_id))
    notification = ServerNotification(
        "ServerRequestResolved",
        ServerRequestResolvedNotification(thread_id=str(conversation_id), request_id=request_id),
    )
    scoped = getattr(outgoing, "thread_scoped", None)
    if callable(scoped):
        await _send_server_notification(scoped(subscribed_connection_ids, conversation_id), notification)
    else:
        await _send_server_notification(outgoing, notification)


def merge_turn_history_with_active_turn(turns: Iterable[Turn], active_turn: Turn) -> list[Turn]:
    return [turn for turn in turns if turn.id != active_turn.id] + [active_turn]


def set_thread_status_and_interrupt_stale_turns(
    thread: Thread,
    loaded_status: ThreadStatus,
    has_live_in_progress_turn: bool,
) -> Thread:
    status = resolve_thread_status(loaded_status, has_live_in_progress_turn)
    turns = list(getattr(thread, "turns", ()))
    if getattr(status, "type", None) != "active":
        turns = [
            _replace_or_set(turn, status=TurnStatus.INTERRUPTED)
            if _is_turn_in_progress(turn)
            else turn
            for turn in turns
        ]
    return _replace_or_set(thread, status=status, turns=tuple(turns))


def _thread_resume_response_from_pending(conversation: Any, pending: PendingThreadResumeRequest, thread: Thread) -> ThreadResumeResponse:
    snapshot = pending.config_snapshot
    return ThreadResumeResponse(
        thread=_replace_or_set(thread, session_id=str(_call_or_get(_call_or_get(conversation, "session_configured"), "session_id") or getattr(thread, "session_id", ""))),
        model=_get(snapshot, "model"),
        model_provider=_get(snapshot, "model_provider_id"),
        service_tier=_get(snapshot, "service_tier"),
        cwd=_get(snapshot, "cwd"),
        runtime_workspace_roots=_get(snapshot, "workspace_roots", ()),
        instruction_sources=pending.instruction_sources,
        approval_policy=_get(snapshot, "approval_policy"),
        approvals_reviewer=_get(snapshot, "approvals_reviewer"),
        sandbox=None,
        active_permission_profile=_get(snapshot, "active_permission_profile"),
        reasoning_effort=_get(snapshot, "reasoning_effort"),
    )


async def _send_response(outgoing: Any, request_id: Any, response: Any) -> None:
    sender = getattr(outgoing, "send_response", None)
    if callable(sender):
        await _maybe_await(sender(request_id, response))


async def _send_error(outgoing: Any, request_id: Any, error: Any) -> None:
    sender = getattr(outgoing, "send_error", None)
    if callable(sender):
        await _maybe_await(sender(request_id, error))


async def _send_server_notification(outgoing: Any, notification: ServerNotification) -> None:
    sender = getattr(outgoing, "send_server_notification", None)
    if callable(sender):
        await _maybe_await(sender(notification))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _call_or_get(obj: Any, name: str, *args: Any) -> Any:
    value = getattr(obj, name, None)
    if callable(value):
        return value(*args)
    return value


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _now(value: float | None) -> float:
    return time.monotonic() if value is None else float(value)


def _is_running_status(status: Any) -> bool:
    return str(_get(status, "type", status)).lower() == "running"


def _is_turn_in_progress(turn: Any) -> bool:
    return turn is not None and _get(turn, "status") in {TurnStatus.IN_PROGRESS, "inProgress"}


def _replace_or_set(obj: Any, **changes: Any) -> Any:
    try:
        return replace(obj, **changes)
    except Exception:
        for key, value in changes.items():
            setattr(obj, key, value)
        return obj


__all__ = [
    "EnsureConversationListenerResult",
    "ListenerTaskContext",
    "THREAD_SHUTDOWN_TIMEOUT",
    "THREAD_UNLOADING_DELAY",
    "ThreadShutdownResult",
    "ThreadLifecycleError",
    "UnloadingState",
    "ensure_conversation_listener",
    "ensure_listener_task_running",
    "handle_pending_thread_resume_request",
    "handle_thread_listener_command",
    "log_listener_attach_result",
    "merge_turn_history_with_active_turn",
    "populate_thread_turns_from_history",
    "resolve_pending_server_request",
    "send_thread_goal_snapshot_notification",
    "set_thread_status_and_interrupt_stale_turns",
    "unload_thread_without_subscribers",
    "wait_for_thread_shutdown",
]
