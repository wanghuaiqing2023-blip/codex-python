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


@dataclass(frozen=True)
class SessionHandle:
    registry: SessionRegistry
    entry: SessionEntry
    connection_id_value: ConnectionId

    def session_id(self) -> str:
        return self.entry.session_id

    def connection_id(self) -> str:
        return str(self.connection_id_value)

    def is_session_attached(self) -> bool:
        return self.entry.is_attached_to(self.connection_id_value)

    def process(self) -> ProcessHandler:
        return self.entry.process

    async def detach(self) -> None:
        if not self.entry.detach(self.connection_id_value, self.registry.detached_session_ttl):
            return
        self.entry.process.set_notification_sender(None)
        asyncio.create_task(self.registry.expire_if_detached(self.entry.session_id, self.connection_id_value))


class ExecServerHandler:
    def __init__(
        self,
        session_registry: SessionRegistry,
        notifications: RpcNotificationSender | None,
        runtime_paths: "ExecServerRuntimePaths",
        file_system: "FileSystemHandler | None" = None,
    ) -> None:
        self.session_registry = session_registry
        self.notifications = notifications
        self.runtime_paths = runtime_paths
        self.file_system = file_system
        self.session_handle: SessionHandle | None = None
        self.initialize_requested = False
        self.initialized_flag = False
        self.shutdown_called = False

    @classmethod
    def new(
        cls,
        session_registry: SessionRegistry,
        notifications: RpcNotificationSender | None,
        runtime_paths: "ExecServerRuntimePaths",
    ) -> "ExecServerHandler":
        return cls(session_registry, notifications, runtime_paths)

    async def shutdown(self) -> None:
        self.shutdown_called = True
        if self.session_handle is not None:
            await self.session_handle.detach()

    def is_session_attached(self) -> bool:
        return self.session_handle is None or self.session_handle.is_session_attached()

    async def initialize(self, params: "InitializeParams") -> "InitializeResponse | JSONRPCErrorError":
        if self.initialize_requested:
            return invalid_request("initialize may only be sent once per connection")
        self.initialize_requested = True
        session = await self.session_registry.attach(params.resume_session_id, self.notifications)
        if isinstance(session, JSONRPCErrorError):
            self.initialize_requested = False
            return session
        self.session_handle = session
        return InitializeResponse(session_id=session.session_id())

    def initialized(self) -> None | str:
        if not self.initialize_requested:
            return "received `initialized` notification before `initialize`"
        session = self.require_session_attached()
        if isinstance(session, JSONRPCErrorError):
            return session.message
        self.initialized_flag = True
        return None

    async def exec(self, params: "ExecParams") -> "ExecResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        return await session.process().exec(params)

    async def exec_read(self, params: "ReadParams") -> "ReadResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        response = await session.process().exec_read(params)
        if isinstance(response, JSONRPCErrorError):
            return response
        attached = self.require_session_attached()
        if isinstance(attached, JSONRPCErrorError):
            return attached
        return response

    async def exec_write(self, params: "WriteParams") -> "WriteResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        return await session.process().exec_write(params)

    async def terminate(self, params: "TerminateParams") -> "TerminateResponse | JSONRPCErrorError":
        session = self.require_initialized_for("exec")
        if isinstance(session, JSONRPCErrorError):
            return session
        return await session.process().terminate(params)

    async def http_request(self, request_id: RequestId, params: Any) -> None | JSONRPCErrorError:
        error = self.require_initialized_for("http")
        if isinstance(error, JSONRPCErrorError):
            return error
        return JSONRPCErrorError(code=-32603, message="codex-exec-server HTTP runtime is not ported")

    async def fs_read_file(self, params: "FsReadFileParams") -> "FsReadFileResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().read_file(params)

    async def fs_write_file(self, params: "FsWriteFileParams") -> "FsWriteFileResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().write_file(params)

    async def fs_create_directory(
        self,
        params: "FsCreateDirectoryParams",
    ) -> "FsCreateDirectoryResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().create_directory(params)

    async def fs_get_metadata(self, params: "FsGetMetadataParams") -> "FsGetMetadataResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().get_metadata(params)

    async def fs_read_directory(
        self,
        params: "FsReadDirectoryParams",
    ) -> "FsReadDirectoryResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().read_directory(params)

    async def fs_remove(self, params: "FsRemoveParams") -> "FsRemoveResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().remove(params)

    async def fs_copy(self, params: "FsCopyParams") -> "FsCopyResponse | JSONRPCErrorError":
        error = self.require_initialized_for("filesystem")
        if isinstance(error, JSONRPCErrorError):
            return error
        return await self._file_system().copy(params)

    def require_initialized_for(self, method_family: str) -> SessionHandle | JSONRPCErrorError:
        if not self.initialize_requested:
            return invalid_request(f"client must call initialize before using {method_family} methods")
        session = self.require_session_attached()
        if isinstance(session, JSONRPCErrorError):
            return session
        if not self.initialized_flag:
            return invalid_request(f"client must send initialized before using {method_family} methods")
        return session

    def require_session_attached(self) -> SessionHandle | JSONRPCErrorError:
        if self.session_handle is None:
            return invalid_request("client must call initialize before using methods")
        if self.session_handle.is_session_attached():
            return self.session_handle
        return invalid_request("session has been resumed by another connection")

    def _file_system(self) -> "FileSystemHandler":
        if self.file_system is None:
            self.file_system = FileSystemHandler.new(self.runtime_paths)
        return self.file_system


from pycodex.exec_server.protocol import InitializeResponse
from pycodex.exec_server.rpc import RpcNotificationSender
from pycodex.exec_server.server.file_system_handler import FileSystemHandler
from pycodex.exec_server.server.process_handler import ProcessHandler
from pycodex.exec_server.server.session_registry import ConnectionId, SessionEntry, SessionRegistry
