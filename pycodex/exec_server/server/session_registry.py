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


DETACHED_SESSION_TTL = 10.0


@dataclass(frozen=True)
class ConnectionId:
    value: uuid.UUID

    @classmethod
    def new(cls) -> "ConnectionId":
        return cls(uuid.uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass
class AttachmentState:
    current_connection_id: ConnectionId | None
    detached_connection_id: ConnectionId | None = None
    detached_expires_at: float | None = None


class SessionEntry:
    def __init__(self, session_id: str, process: ProcessHandler, connection_id: ConnectionId) -> None:
        self.session_id = session_id
        self.process = process
        self.attachment = AttachmentState(current_connection_id=connection_id)

    @classmethod
    def new(cls, session_id: str, process: ProcessHandler, connection_id: ConnectionId) -> "SessionEntry":
        return cls(session_id, process, connection_id)

    def attach(self, connection_id: ConnectionId) -> None:
        self.attachment.current_connection_id = connection_id
        self.attachment.detached_connection_id = None
        self.attachment.detached_expires_at = None

    def detach(self, connection_id: ConnectionId, ttl: float = DETACHED_SESSION_TTL) -> bool:
        if self.attachment.current_connection_id != connection_id:
            return False
        self.attachment.current_connection_id = None
        self.attachment.detached_connection_id = connection_id
        self.attachment.detached_expires_at = time.monotonic() + ttl
        return True

    def has_active_connection(self) -> bool:
        return self.attachment.current_connection_id is not None

    def is_attached_to(self, connection_id: ConnectionId) -> bool:
        return self.attachment.current_connection_id == connection_id

    def is_expired(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return self.attachment.detached_expires_at is not None and now >= self.attachment.detached_expires_at

    def is_detached_connection_expired(self, connection_id: ConnectionId, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return (
            self.attachment.current_connection_id is None
            and self.attachment.detached_connection_id == connection_id
            and self.attachment.detached_expires_at is not None
            and now >= self.attachment.detached_expires_at
        )


class SessionRegistry:
    def __init__(self, detached_session_ttl: float = DETACHED_SESSION_TTL) -> None:
        self.sessions: dict[str, SessionEntry] = {}
        self.detached_session_ttl = detached_session_ttl

    @classmethod
    def new(cls, detached_session_ttl: float = DETACHED_SESSION_TTL) -> "SessionRegistry":
        return cls(detached_session_ttl=detached_session_ttl)

    async def attach(
        self,
        resume_session_id: str | None,
        notifications: RpcNotificationSender | None,
    ) -> "SessionHandle | JSONRPCErrorError":
        connection_id = ConnectionId.new()
        if resume_session_id is not None:
            entry = self.sessions.get(resume_session_id)
            if entry is None:
                return invalid_request(f"unknown session id {resume_session_id}")
            if entry.is_expired():
                removed = self.sessions.pop(resume_session_id, None)
                if removed is not None:
                    await removed.process.shutdown()
                return invalid_request(f"unknown session id {resume_session_id}")
            if entry.has_active_connection():
                return invalid_request(f"session {resume_session_id} is already attached to another connection")
            entry.process.set_notification_sender(notifications)
            entry.attach(connection_id)
            return SessionHandle(self, entry, connection_id)

        session_id = str(uuid.uuid4())
        entry = SessionEntry.new(session_id, ProcessHandler.new(notifications), connection_id)
        self.sessions[session_id] = entry
        return SessionHandle(self, entry, connection_id)

    async def expire_if_detached(self, session_id: str, connection_id: ConnectionId) -> None:
        await asyncio.sleep(self.detached_session_ttl)
        entry = self.sessions.get(session_id)
        if entry is None:
            return
        if not entry.is_detached_connection_expired(connection_id):
            return
        removed = self.sessions.pop(session_id, None)
        if removed is not None:
            await removed.process.shutdown()


from pycodex.exec_server.rpc import RpcNotificationSender
from pycodex.exec_server.server.handler import SessionHandle
from pycodex.exec_server.server.process_handler import ProcessHandler
