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


class ProcessHandler:
    def __init__(self, process: LocalProcess | RpcNotificationSender | None) -> None:
        if isinstance(process, LocalProcess) or _has_local_process_surface(process):
            self.process = process
        else:
            self.process = LocalProcess.new(process)

    @classmethod
    def new(cls, notifications: RpcNotificationSender | None) -> "ProcessHandler":
        return cls(LocalProcess.new(notifications))

    @property
    def notifications(self) -> RpcNotificationSender | None:
        return getattr(self.process, "notifications", None)

    @property
    def shutdown_called(self) -> bool:
        return bool(getattr(self.process, "shutdown_called", False))

    async def shutdown(self) -> None:
        await self.process.shutdown()

    def set_notification_sender(self, notifications: RpcNotificationSender | None) -> None:
        self.process.set_notification_sender(notifications)

    async def exec(self, params: ExecParams) -> ExecResponse:
        return await self.process.exec(params)

    async def exec_read(self, params: ReadParams) -> ReadResponse:
        return await self.process.exec_read(params)

    async def exec_write(self, params: WriteParams) -> WriteResponse:
        return await self.process.exec_write(params)

    async def terminate(self, params: TerminateParams) -> TerminateResponse:
        terminate = getattr(self.process, "terminate_process", None)
        if callable(terminate):
            return await terminate(params)
        return await self.process.terminate(params)


def _has_local_process_surface(value: Any) -> bool:
    return all(
        callable(getattr(value, name, None))
        for name in ("shutdown", "set_notification_sender", "exec", "exec_read", "exec_write")
    )


from pycodex.exec_server.local_process import LocalProcess
from pycodex.exec_server.protocol import ExecParams, ExecResponse, ReadParams, ReadResponse, TerminateParams, TerminateResponse, WriteParams, WriteResponse
from pycodex.exec_server.rpc import RpcNotificationSender
