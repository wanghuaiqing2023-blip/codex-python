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


DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT = 10


DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT = 10


DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT_SECONDS = DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT


DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT_SECONDS = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT


@dataclass(frozen=True)
class ExecServerClientConnectOptions:
    client_name: str = "codex-core"
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
    resume_session_id: str | None = None

    @classmethod
    def from_remote(cls, value: "RemoteExecServerConnectArgs") -> "ExecServerClientConnectOptions":
        return cls(
            client_name=value.client_name,
            initialize_timeout=value.initialize_timeout,
            resume_session_id=value.resume_session_id,
        )

    @classmethod
    def from_stdio(cls, value: "StdioExecServerConnectArgs") -> "ExecServerClientConnectOptions":
        return cls(
            client_name=value.client_name,
            initialize_timeout=value.initialize_timeout,
            resume_session_id=value.resume_session_id,
        )


@dataclass(frozen=True)
class RemoteExecServerConnectArgs:
    websocket_url: str
    client_name: str
    connect_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
    resume_session_id: str | None = None

    @classmethod
    def new(cls, websocket_url: str, client_name: str) -> "RemoteExecServerConnectArgs":
        return cls(websocket_url=websocket_url, client_name=client_name)

    def to_client_connect_options(self) -> ExecServerClientConnectOptions:
        return ExecServerClientConnectOptions.from_remote(self)


@dataclass(frozen=True)
class StdioExecServerCommand:
    program: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "program", str(self.program))
        object.__setattr__(self, "args", [str(arg) for arg in self.args])
        object.__setattr__(self, "env", {str(key): str(value) for key, value in self.env.items()})
        if self.cwd is not None and not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))


@dataclass(frozen=True)
class StdioExecServerConnectArgs:
    command: StdioExecServerCommand
    client_name: str
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
    resume_session_id: str | None = None

    def to_client_connect_options(self) -> ExecServerClientConnectOptions:
        return ExecServerClientConnectOptions.from_stdio(self)


class ExecServerTransportKind(str, Enum):
    WEBSOCKET_URL = "websocketUrl"
    STDIO_COMMAND = "stdioCommand"


@dataclass(frozen=True)
class ExecServerTransportParams:
    kind: ExecServerTransportKind
    websocket_url: str | None = None
    command: StdioExecServerCommand | None = None
    connect_timeout: int | None = None
    initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT

    @classmethod
    def websocket_url_params(cls, websocket_url: str) -> "ExecServerTransportParams":
        return cls(
            kind=ExecServerTransportKind.WEBSOCKET_URL,
            websocket_url=websocket_url,
            connect_timeout=DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
            initialize_timeout=DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
        )

    @classmethod
    def from_websocket_url(
        cls,
        websocket_url: str,
        *,
        connect_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT,
        initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    ) -> "ExecServerTransportParams":
        return cls(
            kind=ExecServerTransportKind.WEBSOCKET_URL,
            websocket_url=websocket_url,
            connect_timeout=connect_timeout,
            initialize_timeout=initialize_timeout,
        )

    @classmethod
    def stdio_command(
        cls,
        command: StdioExecServerCommand,
        *,
        initialize_timeout: int = DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    ) -> "ExecServerTransportParams":
        return cls(
            kind=ExecServerTransportKind.STDIO_COMMAND,
            command=command,
            initialize_timeout=initialize_timeout,
        )

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExecServerTransportKind):
            object.__setattr__(self, "kind", ExecServerTransportKind(self.kind))
        if self.kind is ExecServerTransportKind.WEBSOCKET_URL:
            if self.websocket_url is None:
                raise ValueError("websocket_url is required for WebSocketUrl transport")
            if self.command is not None:
                raise ValueError("command is only valid for StdioCommand transport")
            if self.connect_timeout is None:
                object.__setattr__(self, "connect_timeout", DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT)
        elif self.kind is ExecServerTransportKind.STDIO_COMMAND:
            if self.command is None:
                raise ValueError("command is required for StdioCommand transport")
            if self.websocket_url is not None:
                raise ValueError("websocket_url is only valid for WebSocketUrl transport")
            if self.connect_timeout is not None:
                raise ValueError("connect_timeout is only valid for WebSocketUrl transport")


class HttpClient:
    def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
        raise NotImplementedError("codex-exec-server HTTP transport is not ported")

    def http_request_stream(self, params: HttpRequestParams) -> tuple[HttpRequestResponse, Any]:
        raise NotImplementedError("codex-exec-server streamed HTTP transport is not ported")


from pycodex.exec_server.protocol import HttpRequestParams, HttpRequestResponse
