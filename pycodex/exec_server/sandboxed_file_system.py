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


class SandboxedFileSystem(ExecutorFileSystem):
    def __init__(self, sandbox_runner: Any) -> None:
        self.sandbox_runner = sandbox_runner

    @classmethod
    def new(cls, runtime_paths: "ExecServerRuntimePaths") -> "SandboxedFileSystem":
        return cls(FileSystemSandboxRunner.new(runtime_paths))

    async def run_sandboxed(
        self,
        sandbox: Any,
        request: FsHelperRequest,
    ) -> FsHelperPayload:
        payload = await _maybe_await(self.sandbox_runner.run(sandbox, request))
        if isinstance(payload, JSONRPCErrorError):
            raise map_sandbox_error(payload)
        if not isinstance(payload, FsHelperPayload):
            raise TypeError("sandbox runner returned an invalid fs helper payload")
        return payload

    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(sandbox, FsHelperRequest.read_file(FsReadFileParams(str(_fs_path(path)))))
        response = payload.expect_read_file()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)
        try:
            return base64.b64decode(response.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise OSError(f"fs/readFile returned invalid base64 dataBase64: {exc}") from exc

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.write_file(
                FsWriteFileParams(str(_fs_path(path)), base64.b64encode(bytes(contents)).decode("ascii"))
            ),
        )
        response = payload.expect_write_file()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.create_directory(
                FsCreateDirectoryParams(str(_fs_path(path)), recursive=options.recursive, sandbox=None)
            ),
        )
        response = payload.expect_create_directory()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.get_metadata(FsGetMetadataParams(str(_fs_path(path)), sandbox=None)),
        )
        response = payload.expect_get_metadata()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)
        return FileMetadata(
            is_directory=response.is_directory,
            is_file=response.is_file,
            is_symlink=response.is_symlink,
            created_at_ms=response.created_at_ms,
            modified_at_ms=response.modified_at_ms,
        )

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.read_directory(FsReadDirectoryParams(str(_fs_path(path)), sandbox=None)),
        )
        response = payload.expect_read_directory()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)
        return [
            ReadDirectoryEntry(
                file_name=entry.file_name,
                is_directory=entry.is_directory,
                is_file=entry.is_file,
            )
            for entry in response.entries
        ]

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.remove(
                FsRemoveParams(
                    str(_fs_path(path)),
                    recursive=options.recursive,
                    force=options.force,
                    sandbox=None,
                )
            ),
        )
        response = payload.expect_remove()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        sandbox = _require_platform_sandbox(sandbox)
        payload = await self.run_sandboxed(
            sandbox,
            FsHelperRequest.copy(
                FsCopyParams(
                    str(_fs_path(source_path)),
                    str(_fs_path(destination_path)),
                    recursive=options.recursive,
                    sandbox=None,
                )
            ),
        )
        response = payload.expect_copy()
        if isinstance(response, JSONRPCErrorError):
            raise map_sandbox_error(response)


def _reject_sandbox_context(sandbox: Any | None) -> None:
    if sandbox is not None:
        raise ValueError("direct filesystem operations do not accept sandbox context")


def _reject_platform_sandbox_context(sandbox: Any | None) -> None:
    if _sandbox_should_run_in_sandbox(sandbox):
        raise ValueError("sandboxed filesystem operations require configured runtime paths")


def _require_platform_sandbox(sandbox: Any | None) -> Any:
    if not _sandbox_should_run_in_sandbox(sandbox):
        raise ValueError(
            "sandboxed filesystem operations require ReadOnly or WorkspaceWrite sandbox policy"
        )
    return sandbox


def _sandbox_should_run_in_sandbox(sandbox: Any | None) -> bool:
    if sandbox is None:
        return False
    should_run = getattr(sandbox, "should_run_in_sandbox", None)
    if callable(should_run):
        return bool(should_run())
    return bool(getattr(sandbox, "run_in_sandbox", False))


def map_sandbox_error(error: JSONRPCErrorError) -> OSError:
    if error.code == -32004:
        return FileNotFoundError(error.message)
    if error.code == -32600:
        return ValueError(error.message)
    return OSError(error.message)


from pycodex.exec_server.fs_helper import FsHelperPayload, FsHelperRequest
from pycodex.exec_server.fs_sandbox import FileSystemSandboxRunner
from pycodex.exec_server.local_file_system import _fs_path
from pycodex.exec_server.protocol import FsCopyParams, FsCreateDirectoryParams, FsGetMetadataParams, FsReadDirectoryParams, FsReadFileParams, FsRemoveParams, FsWriteFileParams
from pycodex.exec_server.rpc import _maybe_await
