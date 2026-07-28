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


class HttpResponseBodyStream:
    def __init__(
        self,
        client: "ExecServerClient | None" = None,
        request_id: str | None = None,
        rx: asyncio.Queue[HttpRequestBodyDeltaNotification | None] | None = None,
        *,
        local_chunks: list[bytes] | None = None,
        local_error: str | None = None,
    ) -> None:
        self.client = client
        self.request_id = request_id
        self.rx = rx
        self.local_chunks = deque(local_chunks or [])
        self.local_error = local_error
        self.next_seq = 1
        self.pending_eof = False
        self.closed = False

    @classmethod
    def local(
        cls,
        chunks: list[bytes] | tuple[bytes, ...],
        *,
        error: str | None = None,
    ) -> "HttpResponseBodyStream":
        return cls(local_chunks=[bytes(chunk) for chunk in chunks], local_error=error)

    @classmethod
    def remote(
        cls,
        client: "ExecServerClient",
        request_id: str,
        rx: asyncio.Queue[HttpRequestBodyDeltaNotification | None],
    ) -> "HttpResponseBodyStream":
        return cls(client, request_id, rx)

    async def recv(self) -> bytes | None:
        if self.client is None:
            if self.local_chunks:
                return self.local_chunks.popleft()
            if self.local_error is not None:
                error = self.local_error
                self.local_error = None
                raise ExecServerError.http_request(error)
            return None

        if self.pending_eof:
            self.pending_eof = False
            await self._finish()
            return None

        if self.rx is None or self.request_id is None:
            raise ExecServerError.protocol("http response stream is not registered")
        delta = await self.rx.get()
        if delta is None:
            await self._finish()
            failure = self.client.take_http_body_stream_failure(self.request_id)
            if failure is not None:
                raise ExecServerError.protocol(
                    f"http response stream `{self.request_id}` failed: {failure}"
                )
            return None

        if delta.seq != self.next_seq:
            await self._finish()
            raise ExecServerError.protocol(
                f"http response stream `{self.request_id}` received seq {delta.seq}, expected {self.next_seq}"
            )
        self.next_seq += 1
        chunk = delta.delta.into_inner()

        if delta.error is not None:
            await self._finish()
            raise ExecServerError.protocol(
                f"http response stream `{self.request_id}` failed: {delta.error}"
            )
        if delta.done:
            await self._finish()
            if not chunk:
                return None
            self.pending_eof = True
        return chunk

    async def _finish(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.client is not None and self.request_id is not None:
            await self.client.remove_http_body_stream(self.request_id)

    def __del__(self) -> None:
        if self.closed:
            return
        if self.client is None or self.request_id is None:
            self.closed = True
            return
        self.closed = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.client.remove_http_body_stream(self.request_id))


async def send_body_delta(notifications: Any, delta: HttpRequestBodyDeltaNotification) -> bool:
    try:
        result = notifications.notify(HTTP_REQUEST_BODY_DELTA_METHOD, delta)
        if inspect.isawaitable(result):
            await result
        return True
    except Exception:
        return False


from pycodex.exec_server.client import ExecServerError
from pycodex.exec_server.protocol import HTTP_REQUEST_BODY_DELTA_METHOD, HttpRequestBodyDeltaNotification
