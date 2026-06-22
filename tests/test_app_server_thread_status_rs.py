from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pycodex.app_server.thread_status import ThreadWatchManager, resolve_thread_status
from pycodex.app_server_protocol import (
    ServerNotification,
    SessionSource,
    Thread,
    ThreadActiveFlag,
    ThreadStatus,
    ThreadStatusChangedNotification,
)


INTERACTIVE_THREAD_ID = "00000000-0000-0000-0000-000000000001"
NON_INTERACTIVE_THREAD_ID = "00000000-0000-0000-0000-000000000002"


class FakeOutgoing:
    def __init__(self) -> None:
        self.notifications: list[ServerNotification] = []

    async def send_server_notification(self, notification: ServerNotification) -> None:
        self.notifications.append(notification)


def status_mapping(status: ThreadStatus) -> dict[str, object]:
    return status.to_mapping()


def assert_status(actual: ThreadStatus, expected: ThreadStatus) -> None:
    assert status_mapping(actual) == status_mapping(expected)


def notification_mappings(notifications: list[ServerNotification]) -> list[dict[str, object]]:
    return [notification.to_mapping() for notification in notifications]


def make_thread(thread_id: str, source: SessionSource) -> Thread:
    return Thread(
        id=thread_id,
        session_id=thread_id,
        forked_from_id=None,
        preview="",
        ephemeral=False,
        model_provider="mock-provider",
        created_at=0,
        updated_at=0,
        status=ThreadStatus.not_loaded(),
        path=None,
        cwd=Path("/tmp"),
        cli_version="test",
        source=source,
        thread_source=None,
        agent_nickname=None,
        agent_role=None,
        git_info=None,
        name=None,
        turns=(),
    )


@pytest.mark.asyncio
async def test_loaded_status_defaults_to_not_loaded_for_untracked_threads() -> None:
    # Rust source: loaded_status_defaults_to_not_loaded_for_untracked_threads.
    manager = ThreadWatchManager.new()

    assert_status(
        await manager.loaded_status_for_thread("00000000-0000-0000-0000-000000000003"),
        ThreadStatus.not_loaded(),
    )


@pytest.mark.asyncio
async def test_tracks_non_interactive_thread_status() -> None:
    # Rust source: tracks_non_interactive_thread_status.
    manager = ThreadWatchManager.new()
    await manager.upsert_thread(make_thread(NON_INTERACTIVE_THREAD_ID, SessionSource.app_server()))

    await manager.note_turn_started(NON_INTERACTIVE_THREAD_ID)

    assert_status(await manager.loaded_status_for_thread(NON_INTERACTIVE_THREAD_ID), ThreadStatus.active())


@pytest.mark.asyncio
async def test_status_updates_track_single_thread() -> None:
    # Rust source: status_updates_track_single_thread.
    manager = ThreadWatchManager.new()
    await manager.upsert_thread(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))

    await manager.note_turn_started(INTERACTIVE_THREAD_ID)
    assert_status(await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID), ThreadStatus.active())

    permission_guard = await manager.note_permission_requested(INTERACTIVE_THREAD_ID)
    assert_status(
        await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID),
        ThreadStatus.active([ThreadActiveFlag.WAITING_ON_APPROVAL]),
    )

    user_input_guard = await manager.note_user_input_requested(INTERACTIVE_THREAD_ID)
    assert_status(
        await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID),
        ThreadStatus.active([ThreadActiveFlag.WAITING_ON_APPROVAL, ThreadActiveFlag.WAITING_ON_USER_INPUT]),
    )

    await permission_guard.release()
    assert_status(
        await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID),
        ThreadStatus.active([ThreadActiveFlag.WAITING_ON_USER_INPUT]),
    )

    await user_input_guard.release()
    assert_status(await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID), ThreadStatus.active())

    await manager.note_turn_completed(INTERACTIVE_THREAD_ID, False)
    assert_status(await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID), ThreadStatus.idle())


def test_resolves_in_progress_turn_to_active_status() -> None:
    # Rust source: resolves_in_progress_turn_to_active_status.
    assert_status(resolve_thread_status(ThreadStatus.idle(), True), ThreadStatus.active())
    assert_status(resolve_thread_status(ThreadStatus.not_loaded(), True), ThreadStatus.active())


def test_keeps_status_when_no_in_progress_turn() -> None:
    # Rust source: keeps_status_when_no_in_progress_turn.
    assert_status(resolve_thread_status(ThreadStatus.idle(), False), ThreadStatus.idle())
    assert_status(resolve_thread_status(ThreadStatus.system_error(), False), ThreadStatus.system_error())


@pytest.mark.asyncio
async def test_system_error_sets_idle_flag_until_next_turn() -> None:
    # Rust source: system_error_sets_idle_flag_until_next_turn.
    manager = ThreadWatchManager.new()
    await manager.upsert_thread(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))

    await manager.note_turn_started(INTERACTIVE_THREAD_ID)
    await manager.note_system_error(INTERACTIVE_THREAD_ID)

    assert_status(await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID), ThreadStatus.system_error())

    await manager.note_turn_started(INTERACTIVE_THREAD_ID)
    assert_status(await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID), ThreadStatus.active())


@pytest.mark.asyncio
async def test_shutdown_marks_thread_not_loaded() -> None:
    # Rust source: shutdown_marks_thread_not_loaded.
    manager = ThreadWatchManager.new()
    await manager.upsert_thread(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))

    await manager.note_turn_started(INTERACTIVE_THREAD_ID)
    await manager.note_thread_shutdown(INTERACTIVE_THREAD_ID)

    assert_status(await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID), ThreadStatus.not_loaded())


@pytest.mark.asyncio
async def test_loaded_statuses_default_to_not_loaded_for_untracked_threads() -> None:
    # Rust source: loaded_statuses_default_to_not_loaded_for_untracked_threads.
    manager = ThreadWatchManager.new()
    await manager.upsert_thread(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))
    await manager.note_turn_started(INTERACTIVE_THREAD_ID)

    statuses = await manager.loaded_statuses_for_threads([INTERACTIVE_THREAD_ID, NON_INTERACTIVE_THREAD_ID])

    assert_status(statuses[INTERACTIVE_THREAD_ID], ThreadStatus.active())
    assert_status(statuses[NON_INTERACTIVE_THREAD_ID], ThreadStatus.not_loaded())


@pytest.mark.asyncio
async def test_has_running_turns_tracks_runtime_running_flag_only() -> None:
    # Rust source: has_running_turns_tracks_runtime_running_flag_only.
    manager = ThreadWatchManager.new()
    await manager.upsert_thread(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))

    assert await manager.running_turn_count() == 0

    _permission_guard = await manager.note_permission_requested(INTERACTIVE_THREAD_ID)
    assert await manager.running_turn_count() == 0

    await manager.note_turn_started(INTERACTIVE_THREAD_ID)
    assert await manager.running_turn_count() == 1

    await manager.note_turn_completed(INTERACTIVE_THREAD_ID, False)
    assert await manager.running_turn_count() == 0


@pytest.mark.asyncio
async def test_status_change_emits_notification() -> None:
    # Rust source: status_change_emits_notification.
    outgoing = FakeOutgoing()
    manager = ThreadWatchManager.new_with_outgoing(outgoing)

    await manager.upsert_thread(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))
    await manager.note_turn_started(INTERACTIVE_THREAD_ID)
    await manager.remove_thread(INTERACTIVE_THREAD_ID)

    assert notification_mappings(outgoing.notifications) == notification_mappings([
        ServerNotification(
            "ThreadStatusChanged",
            ThreadStatusChangedNotification(thread_id=INTERACTIVE_THREAD_ID, status=ThreadStatus.idle()),
        ),
        ServerNotification(
            "ThreadStatusChanged",
            ThreadStatusChangedNotification(thread_id=INTERACTIVE_THREAD_ID, status=ThreadStatus.active()),
        ),
        ServerNotification(
            "ThreadStatusChanged",
            ThreadStatusChangedNotification(thread_id=INTERACTIVE_THREAD_ID, status=ThreadStatus.not_loaded()),
        ),
    ])


@pytest.mark.asyncio
async def test_silent_upsert_skips_initial_notification() -> None:
    # Rust source: silent_upsert_skips_initial_notification.
    outgoing = FakeOutgoing()
    manager = ThreadWatchManager.new_with_outgoing(outgoing)

    await manager.upsert_thread_silently(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))

    assert_status(await manager.loaded_status_for_thread(INTERACTIVE_THREAD_ID), ThreadStatus.idle())
    assert outgoing.notifications == []

    await manager.note_turn_started(INTERACTIVE_THREAD_ID)

    assert notification_mappings(outgoing.notifications) == notification_mappings([
        ServerNotification(
            "ThreadStatusChanged",
            ThreadStatusChangedNotification(thread_id=INTERACTIVE_THREAD_ID, status=ThreadStatus.active()),
        )
    ])


@pytest.mark.asyncio
async def test_status_watchers_receive_only_their_thread_updates() -> None:
    # Rust source: status_watchers_receive_only_their_thread_updates.
    manager = ThreadWatchManager.new()
    await manager.upsert_thread(make_thread(INTERACTIVE_THREAD_ID, SessionSource.cli()))
    await manager.upsert_thread(make_thread(NON_INTERACTIVE_THREAD_ID, SessionSource.app_server()))

    interactive_rx = await manager.subscribe(INTERACTIVE_THREAD_ID)
    non_interactive_rx = await manager.subscribe(NON_INTERACTIVE_THREAD_ID)

    await manager.note_turn_started(INTERACTIVE_THREAD_ID)

    assert await interactive_rx.changed(timeout=1.0)
    assert_status(interactive_rx.borrow(), ThreadStatus.active())
    with pytest.raises(asyncio.TimeoutError):
        await non_interactive_rx.changed(timeout=0.01)
    assert_status(non_interactive_rx.borrow(), ThreadStatus.idle())
