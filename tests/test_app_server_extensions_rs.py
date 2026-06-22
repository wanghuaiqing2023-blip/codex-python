import asyncio
import weakref

from pycodex.app_server.extensions import (
    THREAD_EXTENSION_INSTALL_ORDER,
    THREAD_MANAGER_DROPPED_MESSAGE,
    app_server_extension_event_sink_projection,
    app_server_thread_goal_from_core,
    guardian_agent_spawn_projection,
    thread_extensions_projection,
)
from pycodex.protocol import ThreadGoal, ThreadGoalStatus, ThreadGoalUpdatedEvent, ThreadId


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


def test_thread_extensions_projection_records_rust_install_order() -> None:
    # Rust: thread_extensions installs guardian, memories, then web-search extensions.
    projection = thread_extensions_projection("guardian-spawner", "event-sink", "auth")

    assert projection.installed_extensions == THREAD_EXTENSION_INSTALL_ORDER
    assert projection.installed_extensions == ("guardian", "memories", "web_search")
    assert projection.event_sink == "event-sink"
    assert projection.auth_manager == "auth"
    assert projection.otel_provider == "global"


def test_app_server_thread_goal_from_core_preserves_goal_fields() -> None:
    # Rust: AppServerThreadGoal is built from the core ThreadGoal via Into.
    thread_id = ThreadId.from_string("11111111-1111-1111-1111-111111111111")

    goal = app_server_thread_goal_from_core(_thread_goal(thread_id))

    assert goal.to_camel_mapping() == {
        "threadId": "11111111-1111-1111-1111-111111111111",
        "objective": "wire extension events",
        "status": "active",
        "tokenBudget": 123,
        "tokensUsed": 45,
        "timeUsedSeconds": 6,
        "createdAt": 7,
        "updatedAt": 8,
    }


def test_app_server_event_sink_forwards_thread_goal_updates() -> None:
    # Rust test: app_server_event_sink_forwards_thread_goal_updates.
    thread_id = ThreadId.from_string("11111111-1111-1111-1111-111111111111")
    event = {
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

    projection = app_server_extension_event_sink_projection(event)

    assert projection.action == "forward_thread_goal_updated"
    assert projection.notification is not None
    assert projection.notification.to_mapping() == {
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
    # Rust: non-ThreadGoalUpdated extension events are debug-logged and dropped.
    projection = app_server_extension_event_sink_projection(
        {"id": "call-2", "msg": {"type": "other_extension_event", "payload": {"x": 1}}}
    )

    assert projection.action == "drop_unsupported_extension_event"
    assert projection.notification is None
    assert projection.debug_event_id == "call-2"


def test_guardian_agent_spawn_projection_calls_spawn_subagent_when_manager_alive() -> None:
    # Rust: guardian_agent_spawner upgrades Weak<ThreadManager> and delegates to spawn_subagent.
    class ThreadManager:
        def __init__(self) -> None:
            self.calls = []

        async def spawn_subagent(self, forked_from_thread_id, options):
            self.calls.append((forked_from_thread_id, options))
            return {"thread": "new"}

    manager = ThreadManager()
    ref = weakref.ref(manager)

    projection = asyncio.run(guardian_agent_spawn_projection(ref, "parent-thread", {"model": "codex"}))

    assert projection.action == "spawn_subagent"
    assert projection.result == {"thread": "new"}
    assert manager.calls == [("parent-thread", {"model": "codex"})]


def test_guardian_agent_spawn_projection_reports_dropped_thread_manager() -> None:
    # Rust: failed Weak upgrade maps to UnsupportedOperation("thread manager dropped").
    class ThreadManager:
        async def spawn_subagent(self, forked_from_thread_id, options):
            raise AssertionError("should not be called")

    manager = ThreadManager()
    ref = weakref.ref(manager)
    del manager

    projection = asyncio.run(guardian_agent_spawn_projection(ref, "parent-thread", {}))

    assert projection.action == "unsupported_operation"
    assert projection.error == THREAD_MANAGER_DROPPED_MESSAGE
    assert projection.result is None
