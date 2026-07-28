"""App-server extension wiring aligned with ``codex-app-server::extensions``."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from inspect import isawaitable
from typing import Any
from weakref import ReferenceType

from pycodex.app_server_protocol import ServerNotification, ThreadGoalUpdatedNotification
from pycodex.app_server_protocol.thread import ThreadGoal as AppServerThreadGoal
from pycodex.ext.guardian import install as install_guardian
from pycodex.ext.memories import install as install_memories
from pycodex.ext.web_search import install as install_web_search
from pycodex.extension_api import (
    AgentSpawner,
    ExtensionEventSink,
    ExtensionRegistry,
    ExtensionRegistryBuilder,
)
from pycodex.otel.metrics import global_metrics
from pycodex.protocol import CodexErr, ThreadGoalUpdatedEvent


_LOG = logging.getLogger(__name__)
THREAD_MANAGER_DROPPED_MESSAGE = "thread manager dropped"


def thread_extensions(
    guardian_agent_spawner: AgentSpawner,
    event_sink: ExtensionEventSink,
    auth_manager: Any,
) -> ExtensionRegistry:
    builder = ExtensionRegistryBuilder.with_event_sink(event_sink)
    install_guardian(builder, guardian_agent_spawner)
    install_memories(builder, global_metrics())
    install_web_search(builder, auth_manager)
    return builder.build()


def app_server_extension_event_sink(outgoing: Any) -> ExtensionEventSink:
    return _AppServerExtensionEventSink(outgoing)


class _AppServerExtensionEventSink:
    def __init__(self, outgoing: Any) -> None:
        self.outgoing = outgoing

    def emit(self, event: Any) -> None:
        event_id = _field(event, "id")
        msg = _field(event, "msg")
        if _event_msg_type(msg) != "thread_goal_updated":
            _LOG.debug(
                "dropping unsupported extension event",
                extra={"event_id": event_id, "event_msg": msg},
            )
            return
        updated = _coerce_thread_goal_updated_event(_event_msg_payload(msg))
        self.outgoing.try_send_server_notification(
            ServerNotification(
                "ThreadGoalUpdated",
                ThreadGoalUpdatedNotification(
                    thread_id=str(updated.thread_id),
                    turn_id=updated.turn_id,
                    goal=_app_server_thread_goal_from_core(updated.goal),
                ),
            )
        )


def guardian_agent_spawner(
    thread_manager: ReferenceType[Any],
) -> AgentSpawner:
    return _GuardianAgentSpawner(thread_manager)


class _GuardianAgentSpawner:
    def __init__(self, thread_manager: ReferenceType[Any]) -> None:
        self._thread_manager = thread_manager

    async def spawn_subagent(self, forked_from_thread_id: Any, options: Any) -> Any:
        thread_manager = self._thread_manager()
        if thread_manager is None:
            raise CodexErr.unsupported_operation(THREAD_MANAGER_DROPPED_MESSAGE)
        method = getattr(thread_manager, "spawn_subagent", None)
        if not callable(method):
            raise TypeError("spawn_subagent is not callable")
        result = method(forked_from_thread_id, options)
        return await result if isawaitable(result) else result


def _app_server_thread_goal_from_core(goal: Any) -> AppServerThreadGoal:
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


def _coerce_thread_goal_updated_event(value: Any) -> ThreadGoalUpdatedEvent:
    if isinstance(value, ThreadGoalUpdatedEvent):
        return value
    if isinstance(value, Mapping):
        return ThreadGoalUpdatedEvent.from_mapping(value)
    return ThreadGoalUpdatedEvent(
        thread_id=_field(value, "thread_id"),
        goal=_field(value, "goal"),
        turn_id=_field(value, "turn_id"),
    )


def _event_msg_type(msg: Any) -> str:
    if isinstance(msg, Mapping):
        raw = msg.get("type") or msg.get("kind")
    else:
        raw = getattr(msg, "type", None) or getattr(msg, "kind", None)
    raw = getattr(raw, "value", raw)
    if raw is None and isinstance(msg, ThreadGoalUpdatedEvent):
        return "thread_goal_updated"
    return str(raw or "").lower()


def _event_msg_payload(msg: Any) -> Any:
    if isinstance(msg, ThreadGoalUpdatedEvent):
        return msg
    if isinstance(msg, Mapping):
        return msg.get("payload") or msg.get("value") or msg.get("event") or msg
    return getattr(msg, "payload", msg)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        camel = _snake_to_camel(name)
        return value.get(camel, default)
    return getattr(value, name, default)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


__all__ = [
    "THREAD_MANAGER_DROPPED_MESSAGE",
    "app_server_extension_event_sink",
    "guardian_agent_spawner",
    "thread_extensions",
]
