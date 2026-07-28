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


def build_router() -> RpcRouter:
    router = RpcRouter.new()
    router.notification(INITIALIZED_METHOD, lambda handler, _params: handler.initialized())
    router.request(
        INITIALIZE_METHOD,
        lambda handler, params: handler.initialize(params),
        decoder=decode_initialize_params,
        encoder=encode_initialize_response,
    )
    router.request_with_id(
        HTTP_REQUEST_METHOD,
        lambda handler, request_id, params: handler.http_request(request_id, params),
        decoder=decode_http_request_params,
    )
    router.request(
        EXEC_METHOD,
        lambda handler, params: handler.exec(params),
        decoder=decode_exec_params,
        encoder=encode_exec_response,
    )
    router.request(
        EXEC_READ_METHOD,
        lambda handler, params: handler.exec_read(params),
        decoder=decode_read_params,
        encoder=encode_read_response,
    )
    router.request(
        EXEC_WRITE_METHOD,
        lambda handler, params: handler.exec_write(params),
        decoder=decode_write_params,
        encoder=encode_write_response,
    )
    router.request(
        EXEC_TERMINATE_METHOD,
        lambda handler, params: handler.terminate(params),
        decoder=decode_terminate_params,
        encoder=encode_terminate_response,
    )
    router.request(FS_READ_FILE_METHOD, lambda handler, params: handler.fs_read_file(params))
    router.request(FS_WRITE_FILE_METHOD, lambda handler, params: handler.fs_write_file(params))
    router.request(FS_CREATE_DIRECTORY_METHOD, lambda handler, params: handler.fs_create_directory(params))
    router.request(FS_GET_METADATA_METHOD, lambda handler, params: handler.fs_get_metadata(params))
    router.request(FS_READ_DIRECTORY_METHOD, lambda handler, params: handler.fs_read_directory(params))
    router.request(FS_REMOVE_METHOD, lambda handler, params: handler.fs_remove(params))
    router.request(FS_COPY_METHOD, lambda handler, params: handler.fs_copy(params))
    return router


from pycodex.exec_server.protocol import EXEC_METHOD, EXEC_READ_METHOD, EXEC_TERMINATE_METHOD, EXEC_WRITE_METHOD, FS_COPY_METHOD, FS_CREATE_DIRECTORY_METHOD, FS_GET_METADATA_METHOD, FS_READ_DIRECTORY_METHOD, FS_READ_FILE_METHOD, FS_REMOVE_METHOD, FS_WRITE_FILE_METHOD, HTTP_REQUEST_METHOD, INITIALIZED_METHOD, INITIALIZE_METHOD, decode_exec_params, decode_http_request_params, decode_initialize_params, decode_read_params, decode_terminate_params, decode_write_params, encode_exec_response, encode_initialize_response, encode_read_response, encode_terminate_response, encode_write_response
from pycodex.exec_server.rpc import RpcRouter
