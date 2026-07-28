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


MAX_READ_FILE_BYTES = 512 * 1024 * 1024


class DirectFileSystem(ExecutorFileSystem):
    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        _reject_sandbox_context(sandbox)
        path = _fs_path(path)
        if path.stat().st_size > MAX_READ_FILE_BYTES:
            raise ValueError(f"file is too large to read: limit is {MAX_READ_FILE_BYTES} bytes")
        return path.read_bytes()

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        _reject_sandbox_context(sandbox)
        _fs_path(path).write_bytes(bytes(contents))

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_sandbox_context(sandbox)
        _fs_path(path).mkdir(parents=options.recursive, exist_ok=options.recursive)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        _reject_sandbox_context(sandbox)
        path = _fs_path(path)
        metadata = path.stat()
        return FileMetadata(
            is_directory=path.is_dir(),
            is_file=path.is_file(),
            is_symlink=path.is_symlink(),
            created_at_ms=_system_time_to_unix_ms(metadata.st_ctime),
            modified_at_ms=_system_time_to_unix_ms(metadata.st_mtime),
        )

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        _reject_sandbox_context(sandbox)
        entries: list[ReadDirectoryEntry] = []
        for entry in _fs_path(path).iterdir():
            try:
                metadata = entry.stat()
            except OSError:
                continue
            entries.append(
                ReadDirectoryEntry(
                    file_name=entry.name,
                    is_directory=entry.is_dir(),
                    is_file=metadata is not None and entry.is_file(),
                )
            )
        return entries

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_sandbox_context(sandbox)
        _remove_path(_fs_path(path), recursive=options.recursive, force=options.force)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_sandbox_context(sandbox)
        _copy_path(_fs_path(source_path), _fs_path(destination_path), recursive=options.recursive)


class UnsandboxedFileSystem(ExecutorFileSystem):
    def __init__(self, file_system: DirectFileSystem | None = None) -> None:
        self.file_system = file_system or DirectFileSystem()

    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        _reject_platform_sandbox_context(sandbox)
        return await self.file_system.read_file(path, None)

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.write_file(path, contents, None)

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.create_directory(path, options, None)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        _reject_platform_sandbox_context(sandbox)
        return await self.file_system.get_metadata(path, None)

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        _reject_platform_sandbox_context(sandbox)
        return await self.file_system.read_directory(path, None)

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.remove(path, options, None)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        _reject_platform_sandbox_context(sandbox)
        await self.file_system.copy(source_path, destination_path, options, None)


class LocalFileSystem(ExecutorFileSystem):
    def __init__(
        self,
        unsandboxed: UnsandboxedFileSystem | None = None,
        sandboxed: ExecutorFileSystem | None = None,
    ) -> None:
        self.unsandboxed = unsandboxed or UnsandboxedFileSystem()
        self.sandboxed = sandboxed

    @classmethod
    def unsandboxed_fs(cls) -> "LocalFileSystem":
        return cls()

    @classmethod
    def unsandboxed(cls) -> "LocalFileSystem":
        return cls()

    @classmethod
    def with_runtime_paths(cls, runtime_paths: "ExecServerRuntimePaths") -> "LocalFileSystem":
        return cls(sandboxed=SandboxedFileSystem.new(runtime_paths))

    def file_system_for(self, sandbox: Any | None = None) -> tuple[ExecutorFileSystem, Any | None]:
        if _sandbox_should_run_in_sandbox(sandbox):
            if self.sandboxed is None:
                raise ValueError("sandboxed filesystem operations require configured runtime paths")
            return self.sandboxed, sandbox
        return self.unsandboxed, sandbox

    async def read_file(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> bytes:
        file_system, sandbox = self.file_system_for(sandbox)
        return await file_system.read_file(path, sandbox)

    async def write_file(self, path: str | Path | AbsolutePathBuf, contents: bytes, sandbox: Any | None = None) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.write_file(path, contents, sandbox)

    async def create_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        options: CreateDirectoryOptions,
        sandbox: Any | None = None,
    ) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.create_directory(path, options, sandbox)

    async def get_metadata(self, path: str | Path | AbsolutePathBuf, sandbox: Any | None = None) -> FileMetadata:
        file_system, sandbox = self.file_system_for(sandbox)
        return await file_system.get_metadata(path, sandbox)

    async def read_directory(
        self,
        path: str | Path | AbsolutePathBuf,
        sandbox: Any | None = None,
    ) -> list[ReadDirectoryEntry]:
        file_system, sandbox = self.file_system_for(sandbox)
        return await file_system.read_directory(path, sandbox)

    async def remove(
        self,
        path: str | Path | AbsolutePathBuf,
        options: RemoveOptions,
        sandbox: Any | None = None,
    ) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.remove(path, options, sandbox)

    async def copy(
        self,
        source_path: str | Path | AbsolutePathBuf,
        destination_path: str | Path | AbsolutePathBuf,
        options: CopyOptions,
        sandbox: Any | None = None,
    ) -> None:
        file_system, sandbox = self.file_system_for(sandbox)
        await file_system.copy(source_path, destination_path, options, sandbox)


def _remove_path(path: Path, *, recursive: bool, force: bool) -> None:
    try:
        metadata_is_dir = path.is_dir() and not path.is_symlink()
    except OSError:
        metadata_is_dir = False
    if not path.exists() and not path.is_symlink():
        if force:
            return
        raise FileNotFoundError(path)
    if metadata_is_dir:
        if recursive:
            shutil.rmtree(path)
        else:
            path.rmdir()
    else:
        path.unlink()


def _copy_path(source_path: Path, destination_path: Path, *, recursive: bool) -> None:
    if source_path.is_dir() and not source_path.is_symlink():
        if not recursive:
            raise ValueError("fs/copy requires recursive: true when sourcePath is a directory")
        source_resolved = source_path.resolve()
        destination_existing = _resolve_existing_path(destination_path)
        if destination_existing == source_resolved or source_resolved in destination_existing.parents:
            raise ValueError("fs/copy cannot copy a directory to itself or one of its descendants")
        _copy_dir_recursive(source_path, destination_path)
        return
    if source_path.is_symlink():
        target = os.readlink(source_path)
        os.symlink(target, destination_path, target_is_directory=source_path.is_dir())
        return
    if source_path.is_file():
        shutil.copyfile(source_path, destination_path)
        return
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    raise ValueError("fs/copy only supports regular files, directories, and symlinks")


def _copy_dir_recursive(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in source.iterdir():
        target_path = target / entry.name
        if entry.is_dir() and not entry.is_symlink():
            _copy_dir_recursive(entry, target_path)
        elif entry.is_symlink():
            os.symlink(os.readlink(entry), target_path, target_is_directory=entry.is_dir())
        elif entry.is_file():
            shutil.copyfile(entry, target_path)


def _resolve_existing_path(path: Path) -> Path:
    existing = path
    unresolved: list[Path] = []
    while not existing.exists():
        if existing.name == "":
            break
        unresolved.append(Path(existing.name))
        parent = existing.parent
        if parent == existing:
            break
        existing = parent
    resolved = existing.resolve()
    for item in reversed(unresolved):
        resolved = resolved / item
    return resolved


def resolve_existing_path(path: str | Path | AbsolutePathBuf) -> Path:
    return _resolve_existing_path(_fs_path(path))


def current_sandbox_cwd() -> Path:
    try:
        cwd = Path.cwd()
    except OSError as exc:
        raise OSError(f"failed to read current dir: {exc}") from exc
    return resolve_existing_path(cwd)


def _fs_path(path: str | Path | AbsolutePathBuf) -> Path:
    if isinstance(path, AbsolutePathBuf):
        return path.as_path()
    return Path(path)


def _system_time_to_unix_ms(seconds: float) -> int:
    if seconds < 0:
        return 0
    return int(seconds * 1000)


def _fs_dataclass_from_mapping(cls: type, value: dict[str, Any]) -> Any:
    if cls is FsReadFileParams:
        return cls(path=value["path"], sandbox=value.get("sandbox"))
    if cls is FsWriteFileParams:
        return cls(path=value["path"], data_base64=value.get("dataBase64", value.get("data_base64", "")), sandbox=value.get("sandbox"))
    if cls is FsCreateDirectoryParams:
        return cls(path=value["path"], recursive=value.get("recursive"), sandbox=value.get("sandbox"))
    if cls is FsGetMetadataParams:
        return cls(path=value["path"], sandbox=value.get("sandbox"))
    if cls is FsReadDirectoryParams:
        return cls(path=value["path"], sandbox=value.get("sandbox"))
    if cls is FsRemoveParams:
        return cls(path=value["path"], recursive=value.get("recursive"), force=value.get("force"), sandbox=value.get("sandbox"))
    if cls is FsCopyParams:
        return cls(
            source_path=value.get("sourcePath", value.get("source_path")),
            destination_path=value.get("destinationPath", value.get("destination_path")),
            recursive=value.get("recursive", False),
            sandbox=value.get("sandbox"),
        )
    if cls is FsReadFileResponse:
        return cls(data_base64=value.get("dataBase64", value.get("data_base64", "")))
    if cls in {FsWriteFileResponse, FsCreateDirectoryResponse, FsRemoveResponse, FsCopyResponse}:
        return cls()
    if cls is FsGetMetadataResponse:
        return cls(
            is_directory=value.get("isDirectory", value.get("is_directory")),
            is_file=value.get("isFile", value.get("is_file")),
            is_symlink=value.get("isSymlink", value.get("is_symlink")),
            created_at_ms=value.get("createdAtMs", value.get("created_at_ms")),
            modified_at_ms=value.get("modifiedAtMs", value.get("modified_at_ms")),
        )
    if cls is FsReadDirectoryResponse:
        return cls(entries=[_fs_dataclass_from_mapping(FsReadDirectoryEntry, item) for item in value.get("entries", [])])
    if cls is FsReadDirectoryEntry:
        return cls(
            file_name=value.get("fileName", value.get("file_name")),
            is_directory=value.get("isDirectory", value.get("is_directory")),
            is_file=value.get("isFile", value.get("is_file")),
        )
    raise TypeError(f"unsupported fs dataclass: {cls!r}")


def _fs_dataclass_to_camel_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, FsReadFileParams):
        return _without_none({"path": str(value.path), "sandbox": value.sandbox})
    if isinstance(value, FsWriteFileParams):
        return _without_none({"path": str(value.path), "dataBase64": value.data_base64, "sandbox": value.sandbox})
    if isinstance(value, FsCreateDirectoryParams):
        return _without_none({"path": str(value.path), "recursive": value.recursive, "sandbox": value.sandbox})
    if isinstance(value, FsGetMetadataParams):
        return _without_none({"path": str(value.path), "sandbox": value.sandbox})
    if isinstance(value, FsReadDirectoryParams):
        return _without_none({"path": str(value.path), "sandbox": value.sandbox})
    if isinstance(value, FsRemoveParams):
        return _without_none({"path": str(value.path), "recursive": value.recursive, "force": value.force, "sandbox": value.sandbox})
    if isinstance(value, FsCopyParams):
        return _without_none(
            {
                "sourcePath": str(value.source_path),
                "destinationPath": str(value.destination_path),
                "recursive": value.recursive,
                "sandbox": value.sandbox,
            }
        )
    if isinstance(value, FsReadFileResponse):
        return {"dataBase64": value.data_base64}
    if isinstance(value, (FsWriteFileResponse, FsCreateDirectoryResponse, FsRemoveResponse, FsCopyResponse)):
        return {}
    if isinstance(value, FsGetMetadataResponse):
        return {
            "isDirectory": value.is_directory,
            "isFile": value.is_file,
            "isSymlink": value.is_symlink,
            "createdAtMs": value.created_at_ms,
            "modifiedAtMs": value.modified_at_ms,
        }
    if isinstance(value, FsReadDirectoryResponse):
        return {"entries": [_fs_dataclass_to_camel_mapping(item) for item in value.entries]}
    if isinstance(value, FsReadDirectoryEntry):
        return {"fileName": value.file_name, "isDirectory": value.is_directory, "isFile": value.is_file}
    if isinstance(value, JSONRPCErrorError):
        return value.to_mapping()
    raise TypeError(f"unsupported fs dataclass value: {value!r}")


def _without_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


from pycodex.exec_server.protocol import FsCopyParams, FsCopyResponse, FsCreateDirectoryParams, FsCreateDirectoryResponse, FsGetMetadataParams, FsGetMetadataResponse, FsReadDirectoryEntry, FsReadDirectoryParams, FsReadDirectoryResponse, FsReadFileParams, FsReadFileResponse, FsRemoveParams, FsRemoveResponse, FsWriteFileParams, FsWriteFileResponse
from pycodex.exec_server.sandboxed_file_system import SandboxedFileSystem, _reject_platform_sandbox_context, _reject_sandbox_context, _sandbox_should_run_in_sandbox

LOCAL_FS = LocalFileSystem.unsandboxed()
