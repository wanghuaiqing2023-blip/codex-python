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
from pycodex.exec_server.process import (
    ExecBackend,
    ExecProcess,
    ExecProcessEventReceiver,
    StartedExecProcess,
)


@dataclass(frozen=True)
class RemoteProcessBoundary(ExecBackend):
    transport_params: ExecServerTransportParams | None = None
    client: LazyRemoteExecServerClient | None = None

    @classmethod
    def new(cls, client: LazyRemoteExecServerClient) -> "RemoteProcessBoundary":
        return cls(client=client)

    async def start(self, params: ExecParams) -> StartedExecProcess:
        process_id = params.process_id
        client = await self._client()
        session = await client.register_session(process_id)
        try:
            await client.exec(params)
        except Exception:
            await session.unregister()
            raise
        return StartedExecProcess(process=RemoteExecProcess(session))

    async def _client(self) -> Any:
        if self.client is not None:
            return await self.client.get()
        if self.transport_params is None:
            raise ExecServerError.protocol("remote process requires transport params")
        return await LazyRemoteExecServerClient(self.transport_params).get()


@dataclass
class RemoteExecProcess(ExecProcess):
    session: Any
    _unregistered: bool = False

    def process_id(self) -> ProcessId:
        return self.session.process_id()

    def subscribe_wake(self) -> Any:
        return self.session.subscribe_wake()

    def subscribe_events(self) -> ExecProcessEventReceiver:
        return self.session.subscribe_events()

    async def read(
        self,
        after_seq: int | None,
        max_bytes: int | None,
        wait_ms: int | None,
    ) -> ReadResponse:
        return await self.session.read(after_seq, max_bytes, wait_ms)

    async def write(self, chunk: bytes) -> WriteResponse:
        return await self.session.write(chunk)

    async def terminate(self) -> None:
        await self.session.terminate()

    async def unregister(self) -> None:
        if not self._unregistered:
            self._unregistered = True
            await self.session.unregister()

    def __del__(self) -> None:
        if self._unregistered:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._unregistered = True
        loop.create_task(self.session.unregister())


from pycodex.exec_server.client import ExecServerError, LazyRemoteExecServerClient
from pycodex.exec_server.client_api import ExecServerTransportParams
from pycodex.exec_server.process_id import ProcessId
from pycodex.exec_server.protocol import ExecParams, ReadResponse, WriteResponse
