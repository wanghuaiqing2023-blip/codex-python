import asyncio
import weakref

import pytest

from pycodex.analytics import AnalyticsEventsClient
from pycodex.app_server.extensions import (
    app_server_extension_event_sink,
    guardian_agent_spawner,
    thread_extensions,
)
from pycodex.app_server.outgoing_message import OutgoingMessageSender
from pycodex.ext.extension_api import ExtensionRegistry, NoopExtensionEventSink
from pycodex.protocol import CodexErr, ThreadGoal, ThreadGoalStatus, ThreadGoalUpdatedEvent, ThreadId


def _thread_goal(thread_id: ThreadId) -> ThreadGoal:
    return ThreadGoal(
        thread_id=thread_id,
        objective="wire extension events",
        status=ThreadGoalStatus.ACTIVE,
        token_budget=123,
        tokens_used=45,
        time_used_seconds=6,
        created_at=7,
        updated_at=8,
    )


def test_thread_extensions_returns_real_registry_with_rust_install_order() -> None:
    class GuardianSpawner:
        async def spawn_subagent(self, forked_from_thread_id, options):
            return forked_from_thread_id, options

    event_sink = NoopExtensionEventSink()
    registry = thread_extensions(GuardianSpawner(), event_sink, "auth")

    assert isinstance(registry, ExtensionRegistry)
    assert registry.event_sink() is event_sink
    assert [type(item).__name__ for item in registry.thread_lifecycle_contributors()] == [
        "GuardianExtension",
        "MemoriesExtension",
        "WebSearchExtension",
    ]
    assert [type(item).__name__ for item in registry.config_contributors()] == [
        "MemoriesExtension",
        "WebSearchExtension",
    ]
    assert [type(item).__name__ for item in registry.context_contributors()] == [
        "MemoriesExtension"
    ]
    assert [type(item).__name__ for item in registry.tool_contributors()] == [
        "MemoriesExtension",
        "WebSearchExtension",
    ]


def test_app_server_event_sink_forwards_thread_goal_updates_to_outgoing_queue() -> None:
    outgoing = OutgoingMessageSender(analytics_events_client=AnalyticsEventsClient.disabled())
    sink = app_server_extension_event_sink(outgoing)
    thread_id = ThreadId.from_string("11111111-1111-1111-1111-111111111111")

    sink.emit(
        {
            "id": "call-1",
            "msg": {
                "type": "thread_goal_updated",
                "payload": ThreadGoalUpdatedEvent(
                    thread_id=thread_id,
                    turn_id="turn-1",
                    goal=_thread_goal(thread_id),
                ),
            },
        }
    )

    envelope = outgoing.sender.get_nowait()
    assert envelope.kind == "Broadcast"
    assert envelope.message.payload.to_mapping() == {
        "type": "ThreadGoalUpdated",
        "method": "thread/goal/updated",
        "params": {
            "threadId": "11111111-1111-1111-1111-111111111111",
            "turnId": "turn-1",
            "goal": {
                "threadId": "11111111-1111-1111-1111-111111111111",
                "objective": "wire extension events",
                "status": "active",
                "tokenBudget": 123,
                "tokensUsed": 45,
                "timeUsedSeconds": 6,
                "createdAt": 7,
                "updatedAt": 8,
            },
        },
    }


def test_app_server_event_sink_drops_unsupported_extension_events() -> None:
    outgoing = OutgoingMessageSender()
    sink = app_server_extension_event_sink(outgoing)

    sink.emit({"id": "call-2", "msg": {"type": "other_extension_event"}})

    assert outgoing.sender.empty()


def test_guardian_agent_spawner_delegates_to_live_thread_manager() -> None:
    class ThreadManager:
        def __init__(self) -> None:
            self.calls = []

        async def spawn_subagent(self, forked_from_thread_id, options):
            self.calls.append((forked_from_thread_id, options))
            return {"thread": "new"}

    manager = ThreadManager()
    spawner = guardian_agent_spawner(weakref.ref(manager))

    result = asyncio.run(spawner.spawn_subagent("parent-thread", {"model": "codex"}))

    assert result == {"thread": "new"}
    assert manager.calls == [("parent-thread", {"model": "codex"})]


def test_guardian_agent_spawner_maps_failed_weak_upgrade_to_codex_error() -> None:
    class ThreadManager:
        async def spawn_subagent(self, forked_from_thread_id, options):
            raise AssertionError("should not be called")

    manager = ThreadManager()
    spawner = guardian_agent_spawner(weakref.ref(manager))
    del manager

    with pytest.raises(CodexErr) as exc_info:
        asyncio.run(spawner.spawn_subagent("parent-thread", {}))

    assert exc_info.value.kind == "unsupported_operation"
    assert exc_info.value.message == "thread manager dropped"
