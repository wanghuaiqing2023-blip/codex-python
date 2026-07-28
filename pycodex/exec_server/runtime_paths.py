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
class ExecServerRuntimePaths:
    codex_self_exe: AbsolutePathBuf
    codex_linux_sandbox_exe: AbsolutePathBuf | None = None

    @classmethod
    def from_optional_paths(
        cls,
        codex_self_exe: str | Path | None,
        codex_linux_sandbox_exe: str | Path | None = None,
    ) -> "ExecServerRuntimePaths":
        if codex_self_exe is None:
            raise ValueError("Codex executable path is not configured")
        return cls.new(codex_self_exe, codex_linux_sandbox_exe)

    @classmethod
    def new(
        cls,
        codex_self_exe: str | Path,
        codex_linux_sandbox_exe: str | Path | None = None,
    ) -> "ExecServerRuntimePaths":
        return cls(
            codex_self_exe=AbsolutePathBuf.from_absolute_path(codex_self_exe),
            codex_linux_sandbox_exe=(
                AbsolutePathBuf.from_absolute_path(codex_linux_sandbox_exe)
                if codex_linux_sandbox_exe is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, str | None]:
        return {
            "codex_self_exe": str(self.codex_self_exe),
            "codex_linux_sandbox_exe": (
                str(self.codex_linux_sandbox_exe) if self.codex_linux_sandbox_exe is not None else None
            ),
        }
