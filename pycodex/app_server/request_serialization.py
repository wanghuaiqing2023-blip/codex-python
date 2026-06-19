"""Request serialization queues ported from ``request_serialization.rs``."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.app_server.connection_rpc_gate import ConnectionRpcGate
from pycodex.app_server_protocol import ClientRequestSerializationScope

FutureUnit = Awaitable[None] | Callable[[], Awaitable[None] | None]


class RequestSerializationAccess(Enum):
    EXCLUSIVE = "Exclusive"
    SHARED_READ = "SharedRead"


@dataclass(frozen=True)
class RequestSerializationQueueKey:
    kind: str
    value: Any = None
    connection_id: Any = None

    @classmethod
    def global_(cls, name: str) -> "RequestSerializationQueueKey":
        return cls("Global", str(name))

    @classmethod
    def thread(cls, thread_id: str) -> "RequestSerializationQueueKey":
        return cls("Thread", str(thread_id))

    @classmethod
    def thread_path(cls, path: Path | str) -> "RequestSerializationQueueKey":
        return cls("ThreadPath", Path(path))

    @classmethod
    def command_exec_process(cls, connection_id: Any, process_id: str) -> "RequestSerializationQueueKey":
        return cls("CommandExecProcess", str(process_id), connection_id)

    @classmethod
    def process(cls, connection_id: Any, process_handle: str) -> "RequestSerializationQueueKey":
        return cls("Process", str(process_handle), connection_id)

    @classmethod
    def fuzzy_file_search_session(cls, session_id: str) -> "RequestSerializationQueueKey":
        return cls("FuzzyFileSearchSession", str(session_id))

    @classmethod
    def fs_watch(cls, connection_id: Any, watch_id: str) -> "RequestSerializationQueueKey":
        return cls("FsWatch", str(watch_id), connection_id)

    @classmethod
    def mcp_oauth(cls, server_name: str) -> "RequestSerializationQueueKey":
        return cls("McpOauth", str(server_name))

    @classmethod
    def from_scope(
        cls,
        connection_id: Any,
        scope: ClientRequestSerializationScope,
    ) -> tuple["RequestSerializationQueueKey", RequestSerializationAccess]:
        scope_type = scope.type
        if scope_type == "Global":
            return cls.global_(_required(scope.key, "key")), RequestSerializationAccess.EXCLUSIVE
        if scope_type == "GlobalSharedRead":
            return cls.global_(_required(scope.key, "key")), RequestSerializationAccess.SHARED_READ
        if scope_type == "Thread":
            return cls.thread(_required(scope.thread_id, "thread_id")), RequestSerializationAccess.EXCLUSIVE
        if scope_type == "ThreadPath":
            return cls.thread_path(_required(scope.path, "path")), RequestSerializationAccess.EXCLUSIVE
        if scope_type == "CommandExecProcess":
            return (
                cls.command_exec_process(connection_id, _required(scope.process_id, "process_id")),
                RequestSerializationAccess.EXCLUSIVE,
            )
        if scope_type == "Process":
            return (
                cls.process(connection_id, _required(scope.process_handle, "process_handle")),
                RequestSerializationAccess.EXCLUSIVE,
            )
        if scope_type == "FuzzyFileSearchSession":
            return (
                cls.fuzzy_file_search_session(_required(scope.session_id, "session_id")),
                RequestSerializationAccess.EXCLUSIVE,
            )
        if scope_type == "FsWatch":
            return (
                cls.fs_watch(connection_id, _required(scope.watch_id, "watch_id")),
                RequestSerializationAccess.EXCLUSIVE,
            )
        if scope_type == "McpOauth":
            return cls.mcp_oauth(_required(scope.server_name, "server_name")), RequestSerializationAccess.EXCLUSIVE
        raise ValueError(f"unknown ClientRequestSerializationScope type: {scope_type}")


@dataclass
class QueuedInitializedRequest:
    gate: ConnectionRpcGate
    future: FutureUnit

    @classmethod
    def new(cls, gate: ConnectionRpcGate, future: FutureUnit) -> "QueuedInitializedRequest":
        return cls(gate=gate, future=future)

    async def run(self) -> bool:
        return await self.gate.run(self.future)


@dataclass
class _QueuedSerializedRequest:
    access: RequestSerializationAccess
    request: QueuedInitializedRequest


class RequestSerializationQueues:
    def __init__(self) -> None:
        self._queues: dict[RequestSerializationQueueKey, deque[_QueuedSerializedRequest]] = {}
        self._lock = asyncio.Lock()
        self._drain_tasks: set[asyncio.Task[None]] = set()

    @classmethod
    def default(cls) -> "RequestSerializationQueues":
        return cls()

    async def enqueue(
        self,
        key: RequestSerializationQueueKey,
        access: RequestSerializationAccess,
        request: QueuedInitializedRequest,
    ) -> None:
        queued = _QueuedSerializedRequest(access=access, request=request)
        should_spawn = False
        async with self._lock:
            queue = self._queues.get(key)
            if queue is None:
                queue = deque()
                self._queues[key] = queue
                should_spawn = True
            queue.append(queued)

        if should_spawn:
            task = asyncio.create_task(self._drain(key))
            self._drain_tasks.add(task)
            task.add_done_callback(self._drain_tasks.discard)

    async def wait_idle(self) -> None:
        while True:
            tasks = tuple(self._drain_tasks)
            if not tasks:
                return
            await asyncio.gather(*tasks)

    def pending_queue_count(self) -> int:
        return len(self._queues)

    async def _drain(self, key: RequestSerializationQueueKey) -> None:
        while True:
            requests = await self._pop_next_batch(key)
            if not requests:
                return
            await asyncio.gather(*(request.request.run() for request in requests))

    async def _pop_next_batch(self, key: RequestSerializationQueueKey) -> list[_QueuedSerializedRequest]:
        async with self._lock:
            queue = self._queues.get(key)
            if queue is None:
                return []
            if not queue:
                self._queues.pop(key, None)
                return []

            first = queue.popleft()
            batch = [first]
            if first.access is RequestSerializationAccess.SHARED_READ:
                while queue and queue[0].access is RequestSerializationAccess.SHARED_READ:
                    batch.append(queue.popleft())
            return batch


def _required(value: str | None, label: str) -> str:
    if value is None:
        raise ValueError(f"{label} is required")
    return value


__all__ = [
    "QueuedInitializedRequest",
    "RequestSerializationAccess",
    "RequestSerializationQueueKey",
    "RequestSerializationQueues",
]
