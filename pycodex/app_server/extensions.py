"""Extension wiring projections for ``codex-app-server/src/extensions.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, Callable
from weakref import ReferenceType

from pycodex.app_server_protocol import ServerNotification, ThreadGoalUpdatedNotification
from pycodex.app_server_protocol.thread import ThreadGoal as AppServerThreadGoal
from pycodex.protocol import ThreadGoalUpdatedEvent

JsonValue = Any

THREAD_EXTENSION_INSTALL_ORDER = ("guardian", "memories", "web_search")
THREAD_MANAGER_DROPPED_MESSAGE = "thread manager dropped"


@dataclass(frozen=True)
class ThreadExtensionsProjection:
    event_sink: Any
    auth_manager: Any
    installed_extensions: tuple[str, ...] = THREAD_EXTENSION_INSTALL_ORDER
    otel_provider: str = "global"


@dataclass(frozen=True)
class ExtensionEventSinkProjection:
    action: str
    notification: ServerNotification | None = None
    debug_event_id: str | None = None
    debug_msg: Any = None


@dataclass(frozen=True)
class GuardianAgentSpawnProjection:
    action: str
    result: Any = None
    error: str | None = None


def thread_extensions_projection(
    guardian_agent_spawner: Any,
    event_sink: Any,
    auth_manager: Any,
) -> ThreadExtensionsProjection:
    """Record Rust's extension registry builder install order."""

    return ThreadExtensionsProjection(
        event_sink=event_sink,
        auth_manager=auth_manager,
        installed_extensions=THREAD_EXTENSION_INSTALL_ORDER,
        otel_provider="global",
    )


def app_server_extension_event_sink_projection(event: Any) -> ExtensionEventSinkProjection:
    """Mirror `AppServerExtensionEventSink::emit` for one event."""

    event_id = _field(event, "id")
    msg = _field(event, "msg")
    msg_type = _event_msg_type(msg)
    if msg_type == "thread_goal_updated":
        payload = _event_msg_payload(msg)
        updated = _coerce_thread_goal_updated_event(payload)
        notification = ServerNotification(
            "ThreadGoalUpdated",
            ThreadGoalUpdatedNotification(
                thread_id=str(updated.thread_id),
                turn_id=updated.turn_id,
                goal=app_server_thread_goal_from_core(updated.goal),
            ),
        )
        return ExtensionEventSinkProjection("forward_thread_goal_updated", notification)
    return ExtensionEventSinkProjection(
        "drop_unsupported_extension_event",
        debug_event_id=None if event_id is None else str(event_id),
        debug_msg=msg,
    )


def app_server_thread_goal_from_core(goal: Any) -> AppServerThreadGoal:
    return AppServerThreadGoal(
        thread_id=str(_field(goal, "thread_id")),
        objective=_field(goal, "objective"),
        status=_field(goal, "status"),
        token_budget=_field(goal, "token_budget"),
        tokens_used=_field(goal, "tokens_used"),
        time_used_seconds=_field(goal, "time_used_seconds"),
        created_at=_field(goal, "created_at"),
        updated_at=_field(goal, "updated_at"),
    )


async def guardian_agent_spawn_projection(
    thread_manager_ref: ReferenceType | Callable[[], Any] | Any,
    forked_from_thread_id: Any,
    options: Any,
) -> GuardianAgentSpawnProjection:
    """Project the Rust weak-upgrade and `spawn_subagent` call boundary."""

    thread_manager = _upgrade_weak(thread_manager_ref)
    if thread_manager is None:
        return GuardianAgentSpawnProjection(
            "unsupported_operation",
            error=THREAD_MANAGER_DROPPED_MESSAGE,
        )
    result = _call(thread_manager, "spawn_subagent", forked_from_thread_id, options)
    if isawaitable(result):
        result = await result
    return GuardianAgentSpawnProjection("spawn_subagent", result=result)


def _coerce_thread_goal_updated_event(value: Any) -> ThreadGoalUpdatedEvent:
    if isinstance(value, ThreadGoalUpdatedEvent):
        return value
    if isinstance(value, Mapping):
        return ThreadGoalUpdatedEvent.from_mapping(value)
    thread_id = _field(value, "thread_id")
    goal = _field(value, "goal")
    turn_id = _field(value, "turn_id")
    return ThreadGoalUpdatedEvent(thread_id=thread_id, goal=goal, turn_id=turn_id)


def _event_msg_type(msg: Any) -> str:
    if isinstance(msg, Mapping):
        raw = msg.get("type") or msg.get("kind")
    else:
        raw = getattr(msg, "type", None) or getattr(msg, "kind", None)
    raw = getattr(raw, "value", raw)
    if raw is None and isinstance(msg, ThreadGoalUpdatedEvent):
        return "thread_goal_updated"
    return str(raw or "")


def _event_msg_payload(msg: Any) -> Any:
    if isinstance(msg, ThreadGoalUpdatedEvent):
        return msg
    if isinstance(msg, Mapping):
        return msg.get("payload") or msg.get("value") or msg.get("event") or msg
    return getattr(msg, "payload", msg)


def _upgrade_weak(value: ReferenceType | Callable[[], Any] | Any) -> Any:
    if isinstance(value, ReferenceType):
        return value()
    if callable(value):
        return value()
    return value


def _call(value: Any, name: str, *args: Any) -> Any:
    attr = _field(value, name)
    if not callable(attr):
        raise TypeError(f"{name} is not callable")
    return attr(*args)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        camel = _snake_to_camel(name)
        if camel in value:
            return value[camel]
        return None
    return getattr(value, name, None)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


__all__ = [
    "THREAD_EXTENSION_INSTALL_ORDER",
    "THREAD_MANAGER_DROPPED_MESSAGE",
    "ExtensionEventSinkProjection",
    "GuardianAgentSpawnProjection",
    "ThreadExtensionsProjection",
    "app_server_extension_event_sink_projection",
    "app_server_thread_goal_from_core",
    "guardian_agent_spawn_projection",
    "thread_extensions_projection",
]
