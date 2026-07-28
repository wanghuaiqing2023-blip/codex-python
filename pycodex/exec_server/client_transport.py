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


ENVIRONMENT_CLIENT_NAME = "codex-environment"


def is_rendezvous_harness_url(websocket_url: str) -> bool:
    if "?" not in websocket_url:
        return False
    _path, query = websocket_url.split("?", 1)
    for pair in query.split("&"):
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        if key == "role" and value == "harness":
            return True
    return False


@dataclass(frozen=True)
class StdioCommandProcessSpec:
    program: str
    args: tuple[str, ...]
    env: dict[str, str]
    cwd: Path | None
    stdin_piped: bool = True
    stdout_piped: bool = True
    stderr_piped: bool = True
    process_group_zero: bool = os.name != "nt"


def stdio_command_process_spec(stdio_command: StdioExecServerCommand) -> StdioCommandProcessSpec:
    return StdioCommandProcessSpec(
        program=stdio_command.program,
        args=tuple(stdio_command.args),
        env=dict(stdio_command.env),
        cwd=stdio_command.cwd,
    )


async def _spawn_stdio_command_connection(stdio_command: StdioExecServerCommand) -> JsonRpcConnection:
    spec = stdio_command_process_spec(stdio_command)
    env = os.environ.copy()
    env.update(spec.env)
    kwargs: dict[str, Any] = {
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
        "env": env,
    }
    if spec.cwd is not None:
        kwargs["cwd"] = spec.cwd
    if spec.process_group_zero:
        kwargs["process_group"] = 0
    try:
        child = await asyncio.create_subprocess_exec(spec.program, *spec.args, **kwargs)
    except Exception as exc:
        raise ExecServerError(f"failed to spawn exec-server: {exc}", "spawn") from exc
    if child.stdin is None:
        raise ExecServerError.protocol("spawned exec-server command has no stdin")
    if child.stdout is None:
        raise ExecServerError.protocol("spawned exec-server command has no stdout")
    if child.stderr is not None:
        asyncio.create_task(_drain_stdio_command_stderr(child.stderr))
    return JsonRpcConnection.from_stdio(
        child.stdout,
        child.stdin,
        "exec-server stdio command",
    ).with_child_process(child)


async def _drain_stdio_command_stderr(stderr: Any) -> None:
    while True:
        try:
            line = await _read_stdio_line(stderr)
        except Exception:
            return
        if not line:
            return


from pycodex.exec_server.client import ExecServerError
from pycodex.exec_server.client_api import StdioExecServerCommand
from pycodex.exec_server.connection import JsonRpcConnection, _read_stdio_line
