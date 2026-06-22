from __future__ import annotations

import asyncio
from types import SimpleNamespace

from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server.request_processors_thread_lifecycle import (
    EnsureConversationListenerResult,
    ListenerTaskContext,
    ThreadShutdownResult,
    UnloadingState,
    ensure_conversation_listener,
    handle_thread_listener_command,
    merge_turn_history_with_active_turn,
    set_thread_status_and_interrupt_stale_turns,
    unload_thread_without_subscribers,
)
from pycodex.app_server.thread_state import (
    PendingThreadResumeRequest,
    ThreadListenerCommand,
    ThreadState,
    ThreadStateManager,
)
from pycodex.app_server.thread_status import ThreadWatchManager
from pycodex.app_server_protocol import Thread, ThreadStatus, Turn, TurnItemsView, TurnStatus

THREAD_ID = "11111111-1111-4111-8111-111111111111"


def _run(coro):
    return asyncio.run(coro)


def test_unloading_state_uses_latest_idle_and_unsubscribed_timestamp() -> None:
    # Rust source: UnloadingState::unloading_target/should_unload_now.
    state = UnloadingState.new(has_subscribers=False, is_active=False, delay=30, now=100)
    assert state.unloading_target() == 130
    assert state.should_unload_now(now=129) is False
    assert state.should_unload_now(now=130) is True

    state.sync_values(has_subscribers=True, is_active=False, now=140)
    assert state.unloading_target() is None
    state.sync_values(has_subscribers=False, is_active=False, now=150)
    assert state.unloading_target() == 180

    state.note_thread_activity_observed(now=160)
    assert state.unloading_target() == 190


def test_ensure_conversation_listener_maps_missing_and_closed_connection() -> None:
    _run(_ensure_conversation_listener_maps_missing_and_closed_connection())


async def _ensure_conversation_listener_maps_missing_and_closed_connection() -> None:
    manager = ThreadStateManager()
    ctx = _listener_context(thread_manager=FakeThreadManager(thread=None), thread_state_manager=manager)
    try:
        await ensure_conversation_listener(ctx, THREAD_ID, "conn-1", False)
    except Exception as exc:
        assert getattr(exc, "message") == f"thread not found: {THREAD_ID}"
    else:
        raise AssertionError("expected invalid_request")

    ctx = _listener_context(thread_manager=FakeThreadManager(thread=FakeThread()), thread_state_manager=manager)
    result = await ensure_conversation_listener(ctx, THREAD_ID, "conn-closed", False)
    assert result is EnsureConversationListenerResult.CONNECTION_CLOSED


def test_ensure_conversation_listener_attaches_and_marks_raw_events() -> None:
    _run(_ensure_conversation_listener_attaches_and_marks_raw_events())


async def _ensure_conversation_listener_attaches_and_marks_raw_events() -> None:
    manager = ThreadStateManager()
    await manager.connection_initialized("conn-1", SimpleNamespace())
    ctx = _listener_context(thread_manager=FakeThreadManager(thread=FakeThread()), thread_state_manager=manager)

    result = await ensure_conversation_listener(ctx, THREAD_ID, "conn-1", True)

    assert result is EnsureConversationListenerResult.ATTACHED
    state = await manager.thread_state(THREAD_ID)
    assert state.experimental_raw_events is True
    assert state.listener_command_tx is not None


def test_merge_turn_history_with_active_turn_replaces_existing_turn() -> None:
    # Rust source: merge_turn_history_with_active_turn.
    turns = [_turn("old", TurnStatus.COMPLETED), _turn("active", TurnStatus.COMPLETED)]
    active = _turn("active", TurnStatus.IN_PROGRESS)

    merged = merge_turn_history_with_active_turn(turns, active)

    assert [turn.id for turn in merged] == ["old", "active"]
    assert merged[-1].status is TurnStatus.IN_PROGRESS


def test_set_thread_status_interrupts_stale_in_progress_turns_when_inactive() -> None:
    # Rust source: set_thread_status_and_interrupt_stale_turns.
    thread = _thread(turns=(_turn("done", TurnStatus.COMPLETED), _turn("running", TurnStatus.IN_PROGRESS)))

    updated = set_thread_status_and_interrupt_stale_turns(thread, ThreadStatus.idle(), False)

    assert updated.status.type == "idle"
    assert [turn.status for turn in updated.turns] == [TurnStatus.COMPLETED, TurnStatus.INTERRUPTED]

    active = set_thread_status_and_interrupt_stale_turns(thread, ThreadStatus.active(), True)
    assert active.status.type == "active"
    assert active.turns[1].status is TurnStatus.IN_PROGRESS


def test_handle_thread_listener_command_emits_goal_and_resolution_notifications() -> None:
    _run(_handle_thread_listener_command_emits_goal_and_resolution_notifications())


async def _handle_thread_listener_command_emits_goal_and_resolution_notifications() -> None:
    outgoing = FakeOutgoing()
    state_manager = ThreadStateManager()
    await state_manager.connection_initialized("conn-1", SimpleNamespace())
    await state_manager.try_add_connection_to_thread(THREAD_ID, "conn-1")
    completion = _completed_future()

    await handle_thread_listener_command(
        THREAD_ID,
        FakeThread(),
        "codex-home",
        state_manager,
        ThreadState(),
        ThreadWatchManager(),
        outgoing,
        set(),
        ThreadListenerCommand.emit_thread_goal_cleared(),
    )
    await handle_thread_listener_command(
        THREAD_ID,
        FakeThread(),
        "codex-home",
        state_manager,
        ThreadState(),
        ThreadWatchManager(),
        outgoing,
        set(),
        ThreadListenerCommand.resolve_server_request("req-1", completion),
    )

    assert [notification.type for notification in outgoing.notifications] == [
        "ThreadGoalCleared",
        "ServerRequestResolved",
    ]
    assert completion.done()


def test_unload_thread_without_subscribers_cancels_removes_and_notifies_on_complete() -> None:
    _run(_unload_thread_without_subscribers_cancels_removes_and_notifies_on_complete())


async def _unload_thread_without_subscribers_cancels_removes_and_notifies_on_complete() -> None:
    outgoing = FakeOutgoing()
    thread_manager = FakeThreadManager(thread=FakeThread())
    pending = {THREAD_ID}
    watch_manager = FakeThreadWatchManager()
    state_manager = FakeThreadStateManager()

    result = await unload_thread_without_subscribers(
        thread_manager,
        outgoing,
        pending,
        state_manager,
        watch_manager,
        THREAD_ID,
        FakeThread(),
        shutdown_result=ThreadShutdownResult.COMPLETE,
    )

    assert result is ThreadShutdownResult.COMPLETE
    assert pending == set()
    assert outgoing.cancelled == [(THREAD_ID, None)]
    assert state_manager.removed == [THREAD_ID]
    assert watch_manager.removed == [THREAD_ID]
    assert [notification.type for notification in outgoing.notifications] == ["ThreadClosed"]


def _thread(*, turns=()):
    return Thread(
        id=THREAD_ID,
        session_id="session-1",
        forked_from_id=None,
        preview="preview",
        ephemeral=False,
        model_provider="mock",
        created_at=1,
        updated_at=2,
        status=ThreadStatus.idle(),
        path="rollout.jsonl",
        cwd=".",
        cli_version="dev",
        turns=turns,
    )


def _turn(turn_id: str, status: TurnStatus) -> Turn:
    return Turn(id=turn_id, items=(), status=status, items_view=TurnItemsView.FULL)


def _listener_context(**overrides):
    return ListenerTaskContext(
        thread_manager=overrides["thread_manager"],
        thread_state_manager=overrides.get("thread_state_manager", ThreadStateManager()),
        outgoing=overrides.get("outgoing", FakeOutgoing()),
        pending_thread_unloads=overrides.get("pending_thread_unloads", set()),
        thread_watch_manager=overrides.get("thread_watch_manager", FakeThreadWatchManager()),
    )


def _completed_future():
    import asyncio

    return asyncio.get_running_loop().create_future()


class FakeThread:
    def config(self):
        return SimpleNamespace()

    def config_snapshot(self):
        return SimpleNamespace()

    def session_configured(self):
        return SimpleNamespace(session_id="session-live")

    def agent_status(self):
        return SimpleNamespace(type="idle")


class FakeThreadManager:
    def __init__(self, thread) -> None:
        self.thread = thread
        self.removed = []

    async def get_thread(self, _thread_id):
        if self.thread is None:
            raise KeyError("missing")
        return self.thread

    async def remove_thread(self, thread_id):
        self.removed.append(thread_id)
        return self.thread


class FakeThreadWatchManager:
    def __init__(self) -> None:
        self.removed = []

    async def subscribe(self, _thread_id):
        return SimpleNamespace(borrow=lambda: ThreadStatus.idle())

    async def loaded_status_for_thread(self, _thread_id):
        return ThreadStatus.idle()

    async def remove_thread(self, thread_id):
        self.removed.append(thread_id)


class FakeThreadStateManager:
    def __init__(self) -> None:
        self.removed = []

    async def remove_thread_state(self, thread_id):
        self.removed.append(thread_id)


class FakeOutgoing:
    def __init__(self) -> None:
        self.responses = []
        self.errors = []
        self.notifications = []
        self.cancelled = []

    async def send_response(self, request_id, response):
        self.responses.append((request_id, response))

    async def send_error(self, request_id, error):
        self.errors.append((request_id, error))

    async def send_server_notification(self, notification):
        self.notifications.append(notification)

    async def cancel_requests_for_thread(self, thread_id, error):
        self.cancelled.append((thread_id, error))

    async def replay_requests_to_connection_for_thread(self, connection_id, thread_id):
        self.notifications.append(SimpleNamespace(type="Replay", connection_id=connection_id, thread_id=thread_id))
