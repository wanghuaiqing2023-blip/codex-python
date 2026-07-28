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


async def run_fs_helper_once(input_bytes: bytes) -> bytes:
    request_mapping = json.loads(input_bytes)
    request = FsHelperRequest.from_mapping(request_mapping)
    result = await run_direct_request(request)
    if isinstance(result, JSONRPCErrorError):
        response = FsHelperResponse.error(result)
    else:
        response = FsHelperResponse.ok(result)
    return json.dumps(response.to_mapping(), separators=(",", ":")).encode("utf-8") + b"\n"


def main(input_stream: Any | None = None, output_stream: Any | None = None, error_stream: Any | None = None) -> None:
    input_stream = input_stream or sys.stdin.buffer
    output_stream = output_stream or sys.stdout.buffer
    error_stream = error_stream or sys.stderr
    try:
        input_data = input_stream.read()
        if isinstance(input_data, str):
            input_data = input_data.encode("utf-8")
        output_data = asyncio.run(run_fs_helper_once(input_data))
        if hasattr(output_stream, "buffer"):
            output_stream = output_stream.buffer
        try:
            output_stream.write(output_data)
        except TypeError:
            output_stream.write(output_data.decode("utf-8"))
        output_stream.flush()
    except Exception as exc:
        print(f"fs sandbox helper failed: {exc}", file=error_stream)
        raise SystemExit(1) from exc
    raise SystemExit(0)


def _run_direct_request_sync(request: FsHelperRequest) -> FsHelperPayload:
    operation = request.operation
    params = request.params
    if operation == FS_READ_FILE_METHOD:
        _reject_sandbox_context(params.sandbox)
        path = Path(params.path)
        if path.stat().st_size > MAX_READ_FILE_BYTES:
            raise ValueError(f"file is too large to read: limit is {MAX_READ_FILE_BYTES} bytes")
        data = path.read_bytes()
        return FsHelperPayload.read_file(FsReadFileResponse(data_base64=base64.b64encode(data).decode("ascii")))
    if operation == FS_WRITE_FILE_METHOD:
        _reject_sandbox_context(params.sandbox)
        try:
            data = base64.b64decode(params.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"{FS_WRITE_FILE_METHOD} requires valid base64 dataBase64: {exc}") from exc
        Path(params.path).write_bytes(data)
        return FsHelperPayload.write_file(FsWriteFileResponse())
    if operation == FS_CREATE_DIRECTORY_METHOD:
        _reject_sandbox_context(params.sandbox)
        recursive = True if params.recursive is None else params.recursive
        Path(params.path).mkdir(parents=recursive, exist_ok=recursive)
        return FsHelperPayload.create_directory(FsCreateDirectoryResponse())
    if operation == FS_GET_METADATA_METHOD:
        _reject_sandbox_context(params.sandbox)
        path = Path(params.path)
        metadata = path.stat()
        return FsHelperPayload.get_metadata(
            FsGetMetadataResponse(
                is_directory=path.is_dir(),
                is_file=path.is_file(),
                is_symlink=path.is_symlink(),
                created_at_ms=int(metadata.st_ctime * 1000),
                modified_at_ms=int(metadata.st_mtime * 1000),
            )
        )
    if operation == FS_READ_DIRECTORY_METHOD:
        _reject_sandbox_context(params.sandbox)
        entries: list[FsReadDirectoryEntry] = []
        for entry in Path(params.path).iterdir():
            try:
                entry_metadata = entry.stat()
            except OSError:
                continue
            entries.append(
                FsReadDirectoryEntry(
                    file_name=entry.name,
                    is_directory=entry.is_dir(),
                    is_file=entry_metadata is not None and entry.is_file(),
                )
            )
        return FsHelperPayload.read_directory(FsReadDirectoryResponse(entries))
    if operation == FS_REMOVE_METHOD:
        _reject_sandbox_context(params.sandbox)
        _remove_path(Path(params.path), recursive=True if params.recursive is None else params.recursive, force=True if params.force is None else params.force)
        return FsHelperPayload.remove(FsRemoveResponse())
    if operation == FS_COPY_METHOD:
        _reject_sandbox_context(params.sandbox)
        _copy_path(Path(params.source_path), Path(params.destination_path), recursive=params.recursive)
        return FsHelperPayload.copy(FsCopyResponse())
    raise ValueError(f"unsupported fs helper operation: {operation}")


from pycodex.exec_server.fs_helper import FsHelperPayload, FsHelperRequest, FsHelperResponse, run_direct_request
from pycodex.exec_server.local_file_system import MAX_READ_FILE_BYTES, _copy_path, _remove_path
from pycodex.exec_server.protocol import FS_COPY_METHOD, FS_CREATE_DIRECTORY_METHOD, FS_GET_METADATA_METHOD, FS_READ_DIRECTORY_METHOD, FS_READ_FILE_METHOD, FS_REMOVE_METHOD, FS_WRITE_FILE_METHOD, FsCopyResponse, FsCreateDirectoryResponse, FsGetMetadataResponse, FsReadDirectoryEntry, FsReadDirectoryResponse, FsReadFileResponse, FsRemoveResponse, FsWriteFileResponse
from pycodex.exec_server.sandboxed_file_system import _reject_sandbox_context
