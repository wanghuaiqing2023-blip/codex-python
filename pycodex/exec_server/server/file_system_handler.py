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
from pycodex.exec_server.protocol import (
    FS_COPY_METHOD,
    FS_CREATE_DIRECTORY_METHOD,
    FS_GET_METADATA_METHOD,
    FS_READ_DIRECTORY_METHOD,
    FS_READ_FILE_METHOD,
    FS_REMOVE_METHOD,
    FS_WRITE_FILE_METHOD,
    FsCopyParams,
    FsCopyResponse,
    FsCreateDirectoryParams,
    FsCreateDirectoryResponse,
    FsGetMetadataParams,
    FsGetMetadataResponse,
    FsReadDirectoryEntry,
    FsReadDirectoryParams,
    FsReadDirectoryResponse,
    FsReadFileParams,
    FsReadFileResponse,
    FsRemoveParams,
    FsRemoveResponse,
    FsWriteFileParams,
    FsWriteFileResponse,
)


class FileSystemHandler:
    def __init__(self, file_system: LocalFileSystem | None = None) -> None:
        self.file_system = file_system or LocalFileSystem.unsandboxed()

    @classmethod
    def new(cls, runtime_paths: "ExecServerRuntimePaths") -> "FileSystemHandler":
        return cls(LocalFileSystem.with_runtime_paths(runtime_paths))

    async def read_file(self, params: FsReadFileParams) -> FsReadFileResponse | JSONRPCErrorError:
        try:
            data = await self.file_system.read_file(params.path, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsReadFileResponse(data_base64=base64.b64encode(data).decode("ascii"))

    async def write_file(self, params: FsWriteFileParams) -> FsWriteFileResponse | JSONRPCErrorError:
        try:
            data = base64.b64decode(params.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            return invalid_request(f"{FS_WRITE_FILE_METHOD} requires valid base64 dataBase64: {exc}")
        try:
            await self.file_system.write_file(params.path, data, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsWriteFileResponse()

    async def create_directory(
        self,
        params: FsCreateDirectoryParams,
    ) -> FsCreateDirectoryResponse | JSONRPCErrorError:
        try:
            await self.file_system.create_directory(
                params.path,
                CreateDirectoryOptions(recursive=True if params.recursive is None else params.recursive),
                params.sandbox,
            )
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsCreateDirectoryResponse()

    async def get_metadata(self, params: FsGetMetadataParams) -> FsGetMetadataResponse | JSONRPCErrorError:
        try:
            metadata = await self.file_system.get_metadata(params.path, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsGetMetadataResponse(
            is_directory=metadata.is_directory,
            is_file=metadata.is_file,
            is_symlink=metadata.is_symlink,
            created_at_ms=metadata.created_at_ms,
            modified_at_ms=metadata.modified_at_ms,
        )

    async def read_directory(
        self,
        params: FsReadDirectoryParams,
    ) -> FsReadDirectoryResponse | JSONRPCErrorError:
        try:
            entries = await self.file_system.read_directory(params.path, params.sandbox)
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsReadDirectoryResponse(
            [
                FsReadDirectoryEntry(
                    file_name=entry.file_name,
                    is_directory=entry.is_directory,
                    is_file=entry.is_file,
                )
                for entry in entries
            ]
        )

    async def remove(self, params: FsRemoveParams) -> FsRemoveResponse | JSONRPCErrorError:
        try:
            await self.file_system.remove(
                params.path,
                RemoveOptions(
                    recursive=True if params.recursive is None else params.recursive,
                    force=True if params.force is None else params.force,
                ),
                params.sandbox,
            )
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsRemoveResponse()

    async def copy(self, params: FsCopyParams) -> FsCopyResponse | JSONRPCErrorError:
        try:
            await self.file_system.copy(
                params.source_path,
                params.destination_path,
                CopyOptions(recursive=params.recursive),
                params.sandbox,
            )
        except OSError as exc:
            return map_fs_error(exc)
        except ValueError as exc:
            return map_fs_error(exc)
        return FsCopyResponse()


_FS_REQUEST_PARAM_TYPES = {
    FS_READ_FILE_METHOD: FsReadFileParams,
    FS_WRITE_FILE_METHOD: FsWriteFileParams,
    FS_CREATE_DIRECTORY_METHOD: FsCreateDirectoryParams,
    FS_GET_METADATA_METHOD: FsGetMetadataParams,
    FS_READ_DIRECTORY_METHOD: FsReadDirectoryParams,
    FS_REMOVE_METHOD: FsRemoveParams,
    FS_COPY_METHOD: FsCopyParams,
}


_FS_RESPONSE_TYPES = {
    FS_READ_FILE_METHOD: FsReadFileResponse,
    FS_WRITE_FILE_METHOD: FsWriteFileResponse,
    FS_CREATE_DIRECTORY_METHOD: FsCreateDirectoryResponse,
    FS_GET_METADATA_METHOD: FsGetMetadataResponse,
    FS_READ_DIRECTORY_METHOD: FsReadDirectoryResponse,
    FS_REMOVE_METHOD: FsRemoveResponse,
    FS_COPY_METHOD: FsCopyResponse,
}


def map_fs_error(err: BaseException) -> JSONRPCErrorError:
    if isinstance(err, FileNotFoundError):
        return not_found(err)
    if isinstance(err, (ValueError, PermissionError)):
        return invalid_request(err)
    err_no = getattr(err, "errno", None)
    if err_no in {errno.EINVAL, errno.EACCES, errno.EPERM}:
        return invalid_request(err)
    return internal_error(err)


from pycodex.exec_server.local_file_system import LocalFileSystem
from pycodex.exec_server.rpc import not_found
