"""Python interface for Rust ``codex-exec-server``."""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Mapping
from collections import deque
from dataclasses import dataclass, field, replace
from enum import Enum
import binascii
import errno
import hashlib
from functools import total_ordering
import inspect
import ipaddress
import json
import os
from pathlib import Path
import shutil
import ssl
import struct
import sys
import time
import tomllib
from typing import Any
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from pycodex.app_server.error_code import internal_error, invalid_params, invalid_request, method_not_found
from pycodex.app_server_protocol.jsonrpc_lite import (
    JSONRPCError,
    JSONRPCErrorError,
    JSONRPCMessage,
    JSONRPCNotification,
    JSONRPCRequest,
    JSONRPCResponse,
)
from pycodex.protocol import (
    FileSystemAccessMode,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    FileSystemSpecialPath,
    NetworkSandboxPolicy,
    ShellEnvironmentPolicy,
    ShellEnvironmentPolicyInherit,
    PermissionProfile,
    RequestId,
    WindowsSandboxLevel,
)
from pycodex.sandboxing import (
    SandboxCommand,
    SandboxManager,
    SandboxTransformRequest,
    SandboxablePreference,
)
from pycodex.protocol.shell_environment import create_env as create_shell_env
from pycodex.utils.absolute_path import AbsolutePathBuf



from pycodex.file_system import (
    CopyOptions,
    CreateDirectoryOptions,
    ExecutorFileSystem,
    FileMetadata,
    FileSystemSandboxContext,
    ReadDirectoryEntry,
    RemoveOptions,
)
from pycodex.file_system import FileSystemResult


def _byte_chunk_len(chunk: ByteChunk | bytes | bytearray | memoryview | Any) -> int:
    if isinstance(chunk, ByteChunk):
        return len(chunk.data)
    try:
        return len(chunk)
    except TypeError:
        return len(getattr(chunk, "data", b""))


@dataclass(frozen=True)
class ExecProcessEvent:
    kind: str
    chunk: ProcessOutputChunk | None = None
    seq_value: int | None = None
    exit_code: int | None = None
    message: str | None = None

    @classmethod
    def output(cls, chunk: ProcessOutputChunk) -> "ExecProcessEvent":
        return cls("output", chunk=chunk)

    @classmethod
    def exited(cls, seq: int, exit_code: int) -> "ExecProcessEvent":
        return cls("exited", seq_value=seq, exit_code=exit_code)

    @classmethod
    def closed(cls, seq: int) -> "ExecProcessEvent":
        return cls("closed", seq_value=seq)

    @classmethod
    def failed(cls, message: str) -> "ExecProcessEvent":
        return cls("failed", message=str(message))

    def seq(self) -> int | None:
        if self.kind == "output" and self.chunk is not None:
            return self.chunk.seq
        if self.kind in {"exited", "closed"}:
            return self.seq_value
        return None

    def retained_len(self) -> int:
        if self.kind == "output" and self.chunk is not None:
            return _byte_chunk_len(self.chunk.chunk)
        if self.kind == "failed":
            return len(self.message or "")
        return 0


class ExecProcessEventReceiver:
    def __init__(
        self,
        replay: list[ExecProcessEvent] | tuple[ExecProcessEvent, ...] | None = None,
        live_queue: asyncio.Queue[ExecProcessEvent] | None = None,
    ) -> None:
        self._replay = deque(replay or ())
        self._live_queue = live_queue or asyncio.Queue()

    @classmethod
    def empty(cls) -> "ExecProcessEventReceiver":
        return cls()

    async def recv(self) -> ExecProcessEvent:
        if self._replay:
            return self._replay.popleft()
        return await self._live_queue.get()


class ExecProcessEventLog:
    def __init__(self, event_capacity: int, byte_capacity: int) -> None:
        self.event_capacity = max(0, int(event_capacity))
        self.byte_capacity = max(0, int(byte_capacity))
        self._events: deque[ExecProcessEvent] = deque()
        self._retained_bytes = 0
        self._subscribers: list[asyncio.Queue[ExecProcessEvent]] = []

    @classmethod
    def new(cls, event_capacity: int, byte_capacity: int) -> "ExecProcessEventLog":
        return cls(event_capacity, byte_capacity)

    def publish(self, event: ExecProcessEvent) -> None:
        self._retained_bytes += event.retained_len()
        self._events.append(event)
        while len(self._events) > self.event_capacity or self._retained_bytes > self.byte_capacity:
            if not self._events:
                break
            evicted = self._events.popleft()
            self._retained_bytes = max(0, self._retained_bytes - evicted.retained_len())

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(event)

    def subscribe(self) -> ExecProcessEventReceiver:
        live_queue: asyncio.Queue[ExecProcessEvent] = asyncio.Queue(maxsize=self.event_capacity or 1)
        self._subscribers.append(live_queue)
        return ExecProcessEventReceiver(list(self._events), live_queue)

    def retained_len(self) -> int:
        return len(self._events)

    def retained_bytes(self) -> int:
        return self._retained_bytes


@dataclass(frozen=True)
class StartedExecProcess:
    process: "ExecProcess"


class ExecProcess:
    def process_id(self) -> ProcessId:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    def subscribe_wake(self) -> Any:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    def subscribe_events(self) -> ExecProcessEventReceiver:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    async def write(self, chunk: bytes) -> WriteResponse:
        raise NotImplementedError("codex-exec-server process runtime is not ported")

    async def terminate(self) -> None:
        raise NotImplementedError("codex-exec-server process runtime is not ported")


class ExecBackend:
    async def start(self, params: ExecParams) -> StartedExecProcess:
        raise NotImplementedError("codex-exec-server process runtime is not ported")


from pycodex.exec_server.process_id import ProcessId
from pycodex.exec_server.protocol import ByteChunk, ExecParams, ProcessOutputChunk, ReadResponse, WriteResponse
