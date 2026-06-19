"""Thread status watch state ported from ``app-server/src/thread_status.rs``."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from pycodex.app_server_protocol import (
    ServerNotification,
    Thread,
    ThreadActiveFlag,
    ThreadStatus,
    ThreadStatusChangedNotification,
)


class ThreadWatchActiveGuardType(Enum):
    PERMISSION = "permission"
    USER_INPUT = "user_input"


@dataclass
class RuntimeFacts:
    is_loaded: bool = False
    running: bool = False
    pending_permission_requests: int = 0
    pending_user_input_requests: int = 0
    has_system_error: bool = False


class ThreadStatusSubscription:
    """Small Python watch-receiver equivalent for a single thread status."""

    def __init__(self, status: ThreadStatus) -> None:
        self._status = status
        self._version = 0
        self._seen_version = 0
        self._closed = False
        self._condition = asyncio.Condition()

    def borrow(self) -> ThreadStatus:
        return self._status

    async def changed(self, *, timeout: float | None = None) -> bool:
        async def wait_for_change() -> bool:
            async with self._condition:
                await self._condition.wait_for(lambda: self._closed or self._version != self._seen_version)
                if self._closed:
                    return False
                self._seen_version = self._version
                return True

        if timeout is None:
            return await wait_for_change()
        return await asyncio.wait_for(wait_for_change(), timeout)

    async def _send_if_modified(self, status: ThreadStatus) -> None:
        async with self._condition:
            if _status_eq(self._status, status):
                return
            self._status = status
            self._version += 1
            self._condition.notify_all()

    async def close(self) -> None:
        async with self._condition:
            self._closed = True
            self._condition.notify_all()


class ThreadWatchActiveGuard:
    def __init__(self, manager: "ThreadWatchManager", thread_id: str, guard_type: ThreadWatchActiveGuardType) -> None:
        self._manager = manager
        self._thread_id = thread_id
        self._guard_type = guard_type
        self._released = False

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        await self._manager.note_active_guard_released(self._thread_id, self._guard_type)

    async def __aenter__(self) -> "ThreadWatchActiveGuard":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.release()


class ThreadWatchState:
    def __init__(self) -> None:
        self.runtime_by_thread_id: dict[str, RuntimeFacts] = {}
        self.status_watchers_by_thread_id: dict[str, list[ThreadStatusSubscription]] = {}

    def upsert_thread(self, thread_id: str, *, emit_notification: bool) -> ThreadStatusChangedNotification | None:
        previous_status = self.status_for(thread_id)
        runtime = self.runtime_by_thread_id.setdefault(thread_id, RuntimeFacts())
        runtime.is_loaded = True
        if emit_notification:
            return self.status_changed_notification(thread_id, previous_status)
        return None

    def remove_thread(self, thread_id: str) -> ThreadStatusChangedNotification | None:
        previous_status = self.status_for(thread_id)
        self.runtime_by_thread_id.pop(thread_id, None)
        if previous_status is not None and not _status_eq(previous_status, ThreadStatus.not_loaded()):
            return ThreadStatusChangedNotification(thread_id=thread_id, status=ThreadStatus.not_loaded())
        return None

    def update_runtime(
        self,
        thread_id: str,
        mutate: Callable[[RuntimeFacts], None],
    ) -> ThreadStatusChangedNotification | None:
        previous_status = self.status_for(thread_id)
        runtime = self.runtime_by_thread_id.setdefault(thread_id, RuntimeFacts())
        runtime.is_loaded = True
        mutate(runtime)
        return self.status_changed_notification(thread_id, previous_status)

    def status_for(self, thread_id: str) -> ThreadStatus | None:
        runtime = self.runtime_by_thread_id.get(thread_id)
        if runtime is None:
            return None
        return loaded_thread_status(runtime)

    def loaded_status_for_thread(self, thread_id: str) -> ThreadStatus:
        return self.status_for(thread_id) or ThreadStatus.not_loaded()

    def subscribe(self, thread_id: str) -> ThreadStatusSubscription:
        subscription = ThreadStatusSubscription(self.loaded_status_for_thread(thread_id))
        self.status_watchers_by_thread_id.setdefault(thread_id, []).append(subscription)
        return subscription

    async def publish_status(self, thread_id: str, status: ThreadStatus) -> None:
        subscriptions = self.status_watchers_by_thread_id.get(thread_id, [])
        if not subscriptions:
            return
        for subscription in tuple(subscriptions):
            await subscription._send_if_modified(status)

    def status_changed_notification(
        self,
        thread_id: str,
        previous_status: ThreadStatus | None,
    ) -> ThreadStatusChangedNotification | None:
        status = self.status_for(thread_id)
        if status is None:
            return None
        if previous_status is not None and _status_eq(previous_status, status):
            return None
        return ThreadStatusChangedNotification(thread_id=thread_id, status=status)


class ThreadWatchManager:
    def __init__(self, outgoing: Any | None = None) -> None:
        self._state = ThreadWatchState()
        self._outgoing = outgoing
        self._lock = asyncio.Lock()
        self._running_turn_count_subscribers: list[asyncio.Queue[int]] = []

    @classmethod
    def new(cls) -> "ThreadWatchManager":
        return cls()

    @classmethod
    def new_with_outgoing(cls, outgoing: Any) -> "ThreadWatchManager":
        return cls(outgoing)

    async def upsert_thread(self, thread: Thread) -> None:
        await self._mutate_and_publish(lambda state: state.upsert_thread(thread.id, emit_notification=True), thread.id)

    async def upsert_thread_silently(self, thread: Thread) -> None:
        await self._mutate_and_publish(lambda state: state.upsert_thread(thread.id, emit_notification=False), thread.id)

    async def remove_thread(self, thread_id: str) -> None:
        await self._mutate_and_publish(lambda state: state.remove_thread(thread_id), thread_id)

    async def loaded_status_for_thread(self, thread_id: str) -> ThreadStatus:
        async with self._lock:
            return self._state.loaded_status_for_thread(thread_id)

    async def loaded_statuses_for_threads(self, thread_ids: list[str]) -> dict[str, ThreadStatus]:
        async with self._lock:
            return {thread_id: self._state.loaded_status_for_thread(thread_id) for thread_id in thread_ids}

    async def running_turn_count(self) -> int:
        async with self._lock:
            return self._running_turn_count_locked()

    def subscribe_running_turn_count(self) -> asyncio.Queue[int]:
        queue: asyncio.Queue[int] = asyncio.Queue()
        self._running_turn_count_subscribers.append(queue)
        return queue

    async def note_turn_started(self, thread_id: str) -> None:
        def mutate(runtime: RuntimeFacts) -> None:
            runtime.is_loaded = True
            runtime.running = True
            runtime.has_system_error = False

        await self.update_runtime_for_thread(thread_id, mutate)

    async def note_turn_completed(self, thread_id: str, failed: bool = False) -> None:
        del failed
        await self.clear_active_state(thread_id)

    async def note_turn_interrupted(self, thread_id: str) -> None:
        await self.clear_active_state(thread_id)

    async def note_thread_shutdown(self, thread_id: str) -> None:
        def mutate(runtime: RuntimeFacts) -> None:
            runtime.running = False
            runtime.pending_permission_requests = 0
            runtime.pending_user_input_requests = 0
            runtime.is_loaded = False

        await self.update_runtime_for_thread(thread_id, mutate)

    async def note_system_error(self, thread_id: str) -> None:
        def mutate(runtime: RuntimeFacts) -> None:
            runtime.running = False
            runtime.pending_permission_requests = 0
            runtime.pending_user_input_requests = 0
            runtime.has_system_error = True

        await self.update_runtime_for_thread(thread_id, mutate)

    async def clear_active_state(self, thread_id: str) -> None:
        def mutate(runtime: RuntimeFacts) -> None:
            runtime.running = False
            runtime.pending_permission_requests = 0
            runtime.pending_user_input_requests = 0

        await self.update_runtime_for_thread(thread_id, mutate)

    async def note_permission_requested(self, thread_id: str) -> ThreadWatchActiveGuard:
        return await self.note_pending_request(thread_id, ThreadWatchActiveGuardType.PERMISSION)

    async def note_user_input_requested(self, thread_id: str) -> ThreadWatchActiveGuard:
        return await self.note_pending_request(thread_id, ThreadWatchActiveGuardType.USER_INPUT)

    async def note_pending_request(
        self,
        thread_id: str,
        guard_type: ThreadWatchActiveGuardType,
    ) -> ThreadWatchActiveGuard:
        def mutate(runtime: RuntimeFacts) -> None:
            runtime.is_loaded = True
            if guard_type is ThreadWatchActiveGuardType.PERMISSION:
                runtime.pending_permission_requests += 1
            else:
                runtime.pending_user_input_requests += 1

        await self.update_runtime_for_thread(thread_id, mutate)
        return ThreadWatchActiveGuard(self, thread_id, guard_type)

    async def subscribe(self, thread_id: str) -> ThreadStatusSubscription:
        async with self._lock:
            return self._state.subscribe(str(thread_id))

    async def note_active_guard_released(
        self,
        thread_id: str,
        guard_type: ThreadWatchActiveGuardType,
    ) -> None:
        def mutate(runtime: RuntimeFacts) -> None:
            if guard_type is ThreadWatchActiveGuardType.PERMISSION:
                runtime.pending_permission_requests = max(0, runtime.pending_permission_requests - 1)
            else:
                runtime.pending_user_input_requests = max(0, runtime.pending_user_input_requests - 1)

        await self.update_runtime_for_thread(thread_id, mutate)

    async def update_runtime_for_thread(self, thread_id: str, update: Callable[[RuntimeFacts], None]) -> None:
        await self._mutate_and_publish(lambda state: state.update_runtime(thread_id, update), thread_id)

    async def _mutate_and_publish(
        self,
        mutate: Callable[[ThreadWatchState], ThreadStatusChangedNotification | None],
        thread_id: str,
    ) -> None:
        async with self._lock:
            notification = mutate(self._state)
            status = self._state.loaded_status_for_thread(thread_id)
            running_turn_count = self._running_turn_count_locked()
            await self._state.publish_status(thread_id, status)

        self._publish_running_turn_count(running_turn_count)
        if notification is not None and self._outgoing is not None:
            await _send_server_notification(
                self._outgoing,
                ServerNotification("ThreadStatusChanged", notification),
            )

    def _running_turn_count_locked(self) -> int:
        return sum(1 for runtime in self._state.runtime_by_thread_id.values() if runtime.running)

    def _publish_running_turn_count(self, running_turn_count: int) -> None:
        for queue in tuple(self._running_turn_count_subscribers):
            queue.put_nowait(running_turn_count)


def resolve_thread_status(status: ThreadStatus, has_in_progress_turn: bool) -> ThreadStatus:
    if has_in_progress_turn and (_status_eq(status, ThreadStatus.idle()) or _status_eq(status, ThreadStatus.not_loaded())):
        return ThreadStatus.active()
    return status


def loaded_thread_status(runtime: RuntimeFacts) -> ThreadStatus:
    if not runtime.is_loaded:
        return ThreadStatus.not_loaded()

    active_flags: list[ThreadActiveFlag] = []
    if runtime.pending_permission_requests > 0:
        active_flags.append(ThreadActiveFlag.WAITING_ON_APPROVAL)
    if runtime.pending_user_input_requests > 0:
        active_flags.append(ThreadActiveFlag.WAITING_ON_USER_INPUT)

    if runtime.running or active_flags:
        return ThreadStatus.active(active_flags)
    if runtime.has_system_error:
        return ThreadStatus.system_error()
    return ThreadStatus.idle()


def _status_eq(left: ThreadStatus, right: ThreadStatus) -> bool:
    return left.to_mapping() == right.to_mapping()


async def _send_server_notification(outgoing: Any, notification: ServerNotification) -> None:
    sender = getattr(outgoing, "send_server_notification", None)
    if sender is None:
        raise TypeError("outgoing must provide send_server_notification")
    result = sender(notification)
    if inspect.isawaitable(result):
        await result


__all__ = [
    "RuntimeFacts",
    "ThreadStatusSubscription",
    "ThreadWatchActiveGuard",
    "ThreadWatchActiveGuardType",
    "ThreadWatchManager",
    "ThreadWatchState",
    "loaded_thread_status",
    "resolve_thread_status",
]
