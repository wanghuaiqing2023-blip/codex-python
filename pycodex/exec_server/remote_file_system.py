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
class RemoteFileSystemBoundary(ExecutorFileSystem):
    transport_params: ExecServerTransportParams | None = None
    client: LazyRemoteExecServerClient | None = None

    @classmethod
    def new(cls, client: LazyRemoteExecServerClient) -> "RemoteFileSystemBoundary":
        return cls(client=client)

    async def _client(self) -> Any:
        if self.client is not None:
            return await self.client.get()
        if self.transport_params is None:
            raise ExecServerError.protocol("remote filesystem requires transport params")
        return await LazyRemoteExecServerClient(self.transport_params).get()

    async def read_file(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> bytes:
        client = await self._client()
        try:
            response = await client.fs_read_file(FsReadFileParams(str(path), remote_sandbox_context(sandbox)))
            data = base64.b64decode(response.data_base64, validate=True)
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc
        except binascii.Error as exc:
            raise OSError(f"remote fs/readFile returned invalid base64 dataBase64: {exc}") from exc
        return data

    async def write_file(
        self,
        path: str | Path | AbsolutePathBuf,
        contents: bytes,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_write_file(
                FsWriteFileParams(
                    str(path),
                    base64.b64encode(contents).decode("ascii"),
                    remote_sandbox_context(sandbox),
                )
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_create_directory(
                FsCreateDirectoryParams(str(path), options.recursive, remote_sandbox_context(sandbox))
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc

    async def get_metadata(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> FileMetadata:
        client = await self._client()
        try:
            response = await client.fs_get_metadata(FsGetMetadataParams(str(path), remote_sandbox_context(sandbox)))
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc
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
        sandbox: FileSystemSandboxContext | None = None,
    ) -> list[ReadDirectoryEntry]:
        client = await self._client()
        try:
            response = await client.fs_read_directory(FsReadDirectoryParams(str(path), remote_sandbox_context(sandbox)))
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc
        return [
            ReadDirectoryEntry(entry.file_name, entry.is_directory, entry.is_file)
            for entry in response.entries
        ]

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_remove(
                FsRemoveParams(str(path), options.recursive, options.force, remote_sandbox_context(sandbox))
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: FileSystemSandboxContext | None = None,
    ) -> None:
        client = await self._client()
        try:
            await client.fs_copy(
                FsCopyParams(
                    str(source_path),
                    str(destination_path),
                    options.recursive,
                    remote_sandbox_context(sandbox),
                )
            )
        except ExecServerError as exc:
            raise map_remote_error(exc) from exc


def remote_sandbox_context(
    sandbox: FileSystemSandboxContext | None,
) -> FileSystemSandboxContext | None:
    if sandbox is None:
        return None
    return sandbox.drop_cwd_if_unused()


def map_remote_error(error: ExecServerError) -> OSError:
    code = getattr(error, "code", None)
    message = getattr(error, "message", str(error))
    if getattr(error, "kind", None) == "server":
        if code == -32004:
            return FileNotFoundError(message)
        if code == -32600:
            return OSError(errno.EINVAL, message)
        return OSError(message)
    if getattr(error, "kind", None) in {"closed", "disconnected"}:
        return BrokenPipeError("exec-server transport closed")
    return OSError(str(error))


from pycodex.exec_server.client import ExecServerError, LazyRemoteExecServerClient
from pycodex.exec_server.client_api import ExecServerTransportParams
from pycodex.exec_server.protocol import FsCopyParams, FsCreateDirectoryParams, FsGetMetadataParams, FsReadDirectoryParams, FsReadFileParams, FsRemoveParams, FsWriteFileParams
