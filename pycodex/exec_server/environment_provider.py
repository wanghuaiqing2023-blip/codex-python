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


class EnvironmentDefaultKind(str, Enum):
    DISABLED = "disabled"
    ENVIRONMENT_ID = "environmentId"


@dataclass(frozen=True)
class EnvironmentDefault:
    kind: EnvironmentDefaultKind
    environment_id: str | None = None

    @classmethod
    def disabled(cls) -> "EnvironmentDefault":
        return cls(EnvironmentDefaultKind.DISABLED)

    @classmethod
    def environment_id_value(cls, environment_id: str) -> "EnvironmentDefault":
        return cls(EnvironmentDefaultKind.ENVIRONMENT_ID, environment_id)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, EnvironmentDefaultKind):
            object.__setattr__(self, "kind", EnvironmentDefaultKind(self.kind))
        if self.kind is EnvironmentDefaultKind.DISABLED:
            if self.environment_id is not None:
                raise ValueError("environment_id is only valid for EnvironmentId default")
        elif not self.environment_id:
            raise ValueError("environment_id is required for EnvironmentId default")


@dataclass(frozen=True)
class EnvironmentProviderSnapshot:
    environments: list[tuple[str, Environment]]
    default: EnvironmentDefault
    include_local: bool


class EnvironmentProvider:
    def snapshot(self) -> EnvironmentProviderSnapshot:
        raise NotImplementedError("environment provider snapshot is not implemented")


def normalize_exec_server_url(exec_server_url: str | None) -> tuple[str | None, bool]:
    if exec_server_url is None:
        return None, False
    url = exec_server_url.strip()
    if not url:
        return None, False
    if url.lower() == "none":
        return None, True
    return url, False


@dataclass(frozen=True)
class DefaultEnvironmentProvider(EnvironmentProvider):
    exec_server_url: str | None = None

    @classmethod
    def new(cls, exec_server_url: str | None) -> "DefaultEnvironmentProvider":
        return cls(exec_server_url)

    @classmethod
    def from_env(cls) -> "DefaultEnvironmentProvider":
        return cls(os.environ.get(CODEX_EXEC_SERVER_URL_ENV_VAR))

    def snapshot_inner(self) -> EnvironmentProviderSnapshot:
        environments: list[tuple[str, Environment]] = []
        exec_server_url, disabled = normalize_exec_server_url(self.exec_server_url)
        if exec_server_url is not None:
            environments.append(
                (
                    REMOTE_ENVIRONMENT_ID,
                    Environment.remote_inner(exec_server_url, local_runtime_paths=None),
                )
            )

        has_remote = any(environment_id == REMOTE_ENVIRONMENT_ID for environment_id, _ in environments)
        include_local = not disabled and not has_remote
        if disabled:
            default = EnvironmentDefault.disabled()
        elif has_remote:
            default = EnvironmentDefault.environment_id_value(REMOTE_ENVIRONMENT_ID)
        else:
            default = EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)
        return EnvironmentProviderSnapshot(environments=environments, default=default, include_local=include_local)

    def snapshot(self) -> EnvironmentProviderSnapshot:
        return self.snapshot_inner()


from pycodex.exec_server.environment import CODEX_EXEC_SERVER_URL_ENV_VAR, Environment, LOCAL_ENVIRONMENT_ID, REMOTE_ENVIRONMENT_ID
