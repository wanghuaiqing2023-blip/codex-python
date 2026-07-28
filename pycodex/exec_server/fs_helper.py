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


CODEX_FS_HELPER_ARG1 = "--codex-run-as-fs-helper"


@dataclass(frozen=True)
class FsHelperRequest:
    operation: str
    params: Any

    @classmethod
    def read_file(cls, params: FsReadFileParams) -> "FsHelperRequest":
        return cls(FS_READ_FILE_METHOD, params)

    @classmethod
    def write_file(cls, params: FsWriteFileParams) -> "FsHelperRequest":
        return cls(FS_WRITE_FILE_METHOD, params)

    @classmethod
    def create_directory(cls, params: FsCreateDirectoryParams) -> "FsHelperRequest":
        return cls(FS_CREATE_DIRECTORY_METHOD, params)

    @classmethod
    def get_metadata(cls, params: FsGetMetadataParams) -> "FsHelperRequest":
        return cls(FS_GET_METADATA_METHOD, params)

    @classmethod
    def read_directory(cls, params: FsReadDirectoryParams) -> "FsHelperRequest":
        return cls(FS_READ_DIRECTORY_METHOD, params)

    @classmethod
    def remove(cls, params: FsRemoveParams) -> "FsHelperRequest":
        return cls(FS_REMOVE_METHOD, params)

    @classmethod
    def copy(cls, params: FsCopyParams) -> "FsHelperRequest":
        return cls(FS_COPY_METHOD, params)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FsHelperRequest":
        operation = str(value["operation"])
        param_type = _FS_REQUEST_PARAM_TYPES.get(operation)
        if param_type is None:
            raise ValueError(f"unsupported fs helper operation: {operation}")
        return cls(operation, _fs_dataclass_from_mapping(param_type, value.get("params", {})))

    def to_mapping(self) -> dict[str, Any]:
        return {"operation": self.operation, "params": _fs_dataclass_to_camel_mapping(self.params)}


@dataclass(frozen=True)
class FsHelperPayload:
    operation: str
    response: Any

    @classmethod
    def read_file(cls, response: FsReadFileResponse) -> "FsHelperPayload":
        return cls(FS_READ_FILE_METHOD, response)

    @classmethod
    def write_file(cls, response: FsWriteFileResponse) -> "FsHelperPayload":
        return cls(FS_WRITE_FILE_METHOD, response)

    @classmethod
    def create_directory(cls, response: FsCreateDirectoryResponse) -> "FsHelperPayload":
        return cls(FS_CREATE_DIRECTORY_METHOD, response)

    @classmethod
    def get_metadata(cls, response: FsGetMetadataResponse) -> "FsHelperPayload":
        return cls(FS_GET_METADATA_METHOD, response)

    @classmethod
    def read_directory(cls, response: FsReadDirectoryResponse) -> "FsHelperPayload":
        return cls(FS_READ_DIRECTORY_METHOD, response)

    @classmethod
    def remove(cls, response: FsRemoveResponse) -> "FsHelperPayload":
        return cls(FS_REMOVE_METHOD, response)

    @classmethod
    def copy(cls, response: FsCopyResponse) -> "FsHelperPayload":
        return cls(FS_COPY_METHOD, response)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FsHelperPayload":
        operation = str(value["operation"])
        response_type = _FS_RESPONSE_TYPES.get(operation)
        if response_type is None:
            raise ValueError(f"unsupported fs helper operation: {operation}")
        return cls(operation, _fs_dataclass_from_mapping(response_type, value.get("response", {})))

    def to_mapping(self) -> dict[str, Any]:
        return {"operation": self.operation, "response": _fs_dataclass_to_camel_mapping(self.response)}

    def expect_read_file(self) -> FsReadFileResponse | JSONRPCErrorError:
        return self._expect(FS_READ_FILE_METHOD)

    def expect_write_file(self) -> FsWriteFileResponse | JSONRPCErrorError:
        return self._expect(FS_WRITE_FILE_METHOD)

    def expect_create_directory(self) -> FsCreateDirectoryResponse | JSONRPCErrorError:
        return self._expect(FS_CREATE_DIRECTORY_METHOD)

    def expect_get_metadata(self) -> FsGetMetadataResponse | JSONRPCErrorError:
        return self._expect(FS_GET_METADATA_METHOD)

    def expect_read_directory(self) -> FsReadDirectoryResponse | JSONRPCErrorError:
        return self._expect(FS_READ_DIRECTORY_METHOD)

    def expect_remove(self) -> FsRemoveResponse | JSONRPCErrorError:
        return self._expect(FS_REMOVE_METHOD)

    def expect_copy(self) -> FsCopyResponse | JSONRPCErrorError:
        return self._expect(FS_COPY_METHOD)

    def _expect(self, expected: str) -> Any | JSONRPCErrorError:
        if self.operation == expected:
            return self.response
        return unexpected_response(expected, self.operation)


@dataclass(frozen=True)
class FsHelperResponse:
    status: str
    payload: FsHelperPayload | JSONRPCErrorError

    @classmethod
    def ok(cls, payload: FsHelperPayload) -> "FsHelperResponse":
        return cls("ok", payload)

    @classmethod
    def error(cls, error: JSONRPCErrorError) -> "FsHelperResponse":
        return cls("error", error)

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "FsHelperResponse":
        status = str(value["status"])
        payload = value.get("payload", {})
        if status == "ok":
            return cls.ok(FsHelperPayload.from_mapping(payload))
        if status == "error":
            return cls.error(JSONRPCErrorError.from_mapping(payload))
        raise ValueError(f"unsupported fs helper response status: {status}")

    def to_mapping(self) -> dict[str, Any]:
        if self.status == "ok":
            return {"status": "ok", "payload": self.payload.to_mapping()}  # type: ignore[union-attr]
        return {"status": "error", "payload": self.payload.to_mapping()}


def unexpected_response(expected: str, actual: str) -> JSONRPCErrorError:
    return internal_error(f"unexpected fs sandbox helper response: expected {expected}, got {actual}")


async def run_direct_request(request: FsHelperRequest) -> FsHelperPayload | JSONRPCErrorError:
    try:
        return _run_direct_request_sync(request)
    except Exception as exc:
        return map_fs_error(exc)


def map_fs_error(err: BaseException) -> JSONRPCErrorError:
    if isinstance(err, FileNotFoundError):
        return not_found(err)
    if isinstance(err, (ValueError, PermissionError)):
        return invalid_request(err)
    err_no = getattr(err, "errno", None)
    if err_no in {errno.EINVAL, errno.EACCES, errno.EPERM}:
        return invalid_request(err)
    return internal_error(err)


from pycodex.exec_server.fs_helper_main import _run_direct_request_sync
from pycodex.exec_server.local_file_system import _fs_dataclass_from_mapping, _fs_dataclass_to_camel_mapping
from pycodex.exec_server.protocol import FS_COPY_METHOD, FS_CREATE_DIRECTORY_METHOD, FS_GET_METADATA_METHOD, FS_READ_DIRECTORY_METHOD, FS_READ_FILE_METHOD, FS_REMOVE_METHOD, FS_WRITE_FILE_METHOD, FsCopyParams, FsCopyResponse, FsCreateDirectoryParams, FsCreateDirectoryResponse, FsGetMetadataParams, FsGetMetadataResponse, FsReadDirectoryParams, FsReadDirectoryResponse, FsReadFileParams, FsReadFileResponse, FsRemoveParams, FsRemoveResponse, FsWriteFileParams, FsWriteFileResponse
from pycodex.exec_server.rpc import not_found
from pycodex.exec_server.server.file_system_handler import _FS_REQUEST_PARAM_TYPES, _FS_RESPONSE_TYPES
