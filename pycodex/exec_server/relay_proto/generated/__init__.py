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
class RelayData:
    seq: int
    segment_index: int = 0
    segment_count: int = 1
    payload: bytes = b""


@dataclass(frozen=True)
class RelayResume:
    next_seq: int = 0


@dataclass(frozen=True)
class RelayReset:
    reason: str


@dataclass(frozen=True)
class RelayAck:
    pass


@dataclass(frozen=True)
class RelayHeartbeat:
    pass


@dataclass(frozen=True)
class RelayMessageFrame:
    version: int
    stream_id: str
    ack: int = 0
    ack_bits: int = 0
    body_kind: RelayFrameBodyKind | str | None = None
    body: RelayData | RelayResume | RelayReset | RelayAck | RelayHeartbeat | None = None

    def __post_init__(self) -> None:
        if self.body_kind is not None and not isinstance(self.body_kind, RelayFrameBodyKind):
            object.__setattr__(self, "body_kind", RelayFrameBodyKind(self.body_kind))

    @classmethod
    def data(cls, stream_id: str, seq: int, payload: bytes) -> "RelayMessageFrame":
        return cls(
            version=RELAY_MESSAGE_FRAME_VERSION,
            stream_id=stream_id,
            body_kind=RelayFrameBodyKind.DATA,
            body=RelayData(seq=seq, payload=bytes(payload)),
        )

    @classmethod
    def resume(cls, stream_id: str) -> "RelayMessageFrame":
        return cls(
            version=RELAY_MESSAGE_FRAME_VERSION,
            stream_id=stream_id,
            body_kind=RelayFrameBodyKind.RESUME,
            body=RelayResume(next_seq=0),
        )

    @classmethod
    def reset(cls, stream_id: str, reason: str) -> "RelayMessageFrame":
        return cls(
            version=RELAY_MESSAGE_FRAME_VERSION,
            stream_id=stream_id,
            body_kind=RelayFrameBodyKind.RESET,
            body=RelayReset(reason),
        )

    def validate(self) -> RelayFrameBodyKind:
        if self.version != RELAY_MESSAGE_FRAME_VERSION:
            raise ExecServerError.protocol(f"unsupported relay message frame version {self.version}")
        if not self.stream_id.strip():
            raise ExecServerError.protocol("relay message frame is missing stream_id")
        if self.body_kind is RelayFrameBodyKind.DATA and isinstance(self.body, RelayData):
            if self.body.segment_index != 0 or self.body.segment_count != 1 or not self.body.payload:
                raise ExecServerError.protocol("relay data message frame is missing required fields")
            return RelayFrameBodyKind.DATA
        if self.body_kind is RelayFrameBodyKind.ACK and isinstance(self.body, RelayAck):
            return RelayFrameBodyKind.ACK
        if self.body_kind is RelayFrameBodyKind.RESUME and isinstance(self.body, RelayResume):
            return RelayFrameBodyKind.RESUME
        if self.body_kind is RelayFrameBodyKind.RESET and isinstance(self.body, RelayReset):
            if not self.body.reason:
                raise ExecServerError.protocol("relay reset message frame is missing reason")
            return RelayFrameBodyKind.RESET
        if self.body_kind is RelayFrameBodyKind.HEARTBEAT and isinstance(self.body, RelayHeartbeat):
            return RelayFrameBodyKind.HEARTBEAT
        raise ExecServerError.protocol("relay message frame is missing body")

    def into_jsonrpc_message(self) -> JSONRPCMessage:
        kind = self.validate()
        if kind is not RelayFrameBodyKind.DATA:
            raise ExecServerError.protocol("expected relay data message frame")
        assert isinstance(self.body, RelayData)
        try:
            payload = json.loads(self.body.payload.decode("utf-8"))
            return JSONRPCMessage.from_mapping(payload)
        except Exception as exc:
            raise ExecServerError(str(exc), "json") from exc

    def into_reset_reason(self) -> str | None:
        if self.body_kind is RelayFrameBodyKind.RESET and isinstance(self.body, RelayReset) and self.body.reason:
            return self.body.reason
        return None


from pycodex.exec_server.client import ExecServerError
from pycodex.exec_server.relay import RELAY_MESSAGE_FRAME_VERSION
from pycodex.exec_server.relay import RelayFrameBodyKind


