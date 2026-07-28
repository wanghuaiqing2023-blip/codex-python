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


FS_HELPER_ENV_ALLOWLIST = ("PATH", "TMPDIR", "TMP", "TEMP")


FS_HELPER_BAZEL_BWRAP_ENV_ALLOWLIST = (
    "CARGO_BIN_EXE_bwrap",
    "RUNFILES_DIR",
    "RUNFILES_MANIFEST_FILE",
    "RUNFILES_MANIFEST_ONLY",
    "TEST_SRCDIR",
    "TEST_WORKSPACE",
)


@dataclass(frozen=True)
class FsSandboxExecRequest:
    argv: list[str]
    cwd: AbsolutePathBuf
    env: dict[str, str]
    arg0: str | None = None


@dataclass(frozen=True)
class FsSandboxCommandOutput:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    status_text: str | None = None

    def status_success(self) -> bool:
        return self.returncode == 0

    def status_display(self) -> str:
        return self.status_text if self.status_text is not None else f"exit status: {self.returncode}"


@dataclass(frozen=True)
class FileSystemSandboxRunner:
    runtime_paths: ExecServerRuntimePaths
    helper_env: dict[str, str] = field(default_factory=lambda: helper_env())
    command_runner: Any | None = None

    @classmethod
    def new(cls, runtime_paths: ExecServerRuntimePaths) -> "FileSystemSandboxRunner":
        return cls(runtime_paths=runtime_paths, helper_env=helper_env())

    async def run(
        self,
        sandbox: FileSystemSandboxContext,
        request: FsHelperRequest,
    ) -> FsHelperPayload | JSONRPCErrorError:
        cwd_or_error = sandbox_cwd(sandbox)
        if isinstance(cwd_or_error, JSONRPCErrorError):
            return cwd_or_error
        cwd = cwd_or_error
        file_system_policy = sandbox.permissions.file_system_sandbox_policy()
        read_roots = [] if sandbox.use_legacy_landlock else helper_read_roots(self.runtime_paths)
        file_system_policy = add_helper_runtime_permissions(file_system_policy, read_roots, cwd.as_path())
        permission_profile = PermissionProfile.from_runtime_permissions_with_enforcement(
            sandbox.permissions.enforcement(),
            file_system_policy,
            NetworkSandboxPolicy.RESTRICTED,
        )
        command = self.sandbox_exec_request(permission_profile, cwd, sandbox)
        if isinstance(command, JSONRPCErrorError):
            return command
        try:
            request_json = json.dumps(request.to_mapping(), separators=(",", ":")).encode("utf-8")
        except Exception as exc:
            return _fs_sandbox_json_error(exc)
        return await self.run_command(command, request_json)

    async def run_command(
        self,
        command: FsSandboxExecRequest,
        request_json: bytes,
    ) -> FsHelperPayload | JSONRPCErrorError:
        if not command.argv:
            return invalid_request("fs sandbox command was empty")
        if self.command_runner is None:
            output_or_error = await _run_fs_sandbox_subprocess(command, request_json)
            if isinstance(output_or_error, JSONRPCErrorError):
                return output_or_error
            output = output_or_error
        else:
            try:
                output = await _maybe_await(self.command_runner(command, request_json))
            except OSError as exc:
                return internal_error(exc)
        output = _fs_sandbox_command_output(output)
        if not output.status_success():
            stderr = output.stderr.decode("utf-8", errors="replace").strip()
            return internal_error(
                f"fs sandbox helper failed with status {output.status_display()}: {stderr}"
            )
        try:
            response = FsHelperResponse.from_mapping(json.loads(output.stdout))
        except Exception as exc:
            return _fs_sandbox_json_error(exc)
        if response.status == "error":
            return response.payload  # type: ignore[return-value]
        return response.payload  # type: ignore[return-value]

    def sandbox_exec_request(
        self,
        permission_profile: PermissionProfile,
        cwd: AbsolutePathBuf,
        sandbox_context: FileSystemSandboxContext,
    ) -> FsSandboxExecRequest | JSONRPCErrorError:
        sandbox_manager = SandboxManager.new()
        file_system_policy, network_policy = permission_profile.to_runtime_permissions()
        windows_sandbox_level = sandbox_context.windows_sandbox_level or WindowsSandboxLevel.DISABLED
        sandbox = sandbox_manager.select_initial(
            file_system_policy,
            network_policy,
            SandboxablePreference.AUTO,
            windows_sandbox_level,
            False,
        )
        command = SandboxCommand(
            program=str(self.runtime_paths.codex_self_exe),
            args=(CODEX_FS_HELPER_ARG1,),
            cwd=cwd.as_path(),
            env=dict(self.helper_env),
            additional_permissions=None,
        )
        try:
            transformed = sandbox_manager.transform(
                SandboxTransformRequest(
                    command=command,
                    permissions=permission_profile,
                    sandbox=sandbox,
                    enforce_managed_network=False,
                    network=None,
                    sandbox_policy_cwd=cwd.as_path(),
                    codex_linux_sandbox_exe=(
                        self.runtime_paths.codex_linux_sandbox_exe.as_path()
                        if self.runtime_paths.codex_linux_sandbox_exe is not None
                        else None
                    ),
                    use_legacy_landlock=sandbox_context.use_legacy_landlock,
                    windows_sandbox_level=windows_sandbox_level,
                    windows_sandbox_private_desktop=sandbox_context.windows_sandbox_private_desktop,
                )
            )
        except Exception as exc:
            return invalid_request(f"failed to prepare fs sandbox: {exc}")
        return FsSandboxExecRequest(
            argv=list(transformed.command),
            cwd=AbsolutePathBuf.from_absolute_path(transformed.cwd),
            env=dict(transformed.env),
            arg0=transformed.arg0,
        )


def _fs_sandbox_command_output(value: Any) -> FsSandboxCommandOutput:
    if isinstance(value, FsSandboxCommandOutput):
        return value
    if isinstance(value, tuple):
        if len(value) == 3:
            return FsSandboxCommandOutput(int(value[0]), bytes(value[1]), bytes(value[2]))
        if len(value) == 4:
            return FsSandboxCommandOutput(int(value[0]), bytes(value[1]), bytes(value[2]), str(value[3]))
    return FsSandboxCommandOutput(
        int(getattr(value, "returncode")),
        bytes(getattr(value, "stdout", b"")),
        bytes(getattr(value, "stderr", b"")),
        getattr(value, "status_text", None),
    )


async def _run_fs_sandbox_subprocess(
    command: FsSandboxExecRequest,
    request_json: bytes,
) -> FsSandboxCommandOutput | JSONRPCErrorError:
    if not command.argv:
        return invalid_request("fs sandbox command was empty")
    program = command.argv[0]
    args = command.argv[1:]
    popen_args = [program, *args]
    kwargs: dict[str, Any] = {
        "cwd": str(command.cwd),
        "env": dict(command.env),
        "stdin": asyncio.subprocess.PIPE,
        "stdout": asyncio.subprocess.PIPE,
        "stderr": asyncio.subprocess.PIPE,
    }
    if command.arg0 and os.name != "nt":
        popen_args = [command.arg0, *args]
        kwargs["executable"] = program
    try:
        child = await asyncio.create_subprocess_exec(*popen_args, **kwargs)
        stdout, stderr = await child.communicate(request_json)
    except OSError as exc:
        return internal_error(exc)
    return FsSandboxCommandOutput(
        child.returncode if child.returncode is not None else 0,
        stdout,
        stderr,
    )


def _fs_sandbox_json_error(error: BaseException) -> JSONRPCErrorError:
    return internal_error(f"failed to encode or decode fs sandbox helper message: {error}")


def sandbox_cwd(sandbox: FileSystemSandboxContext) -> AbsolutePathBuf | JSONRPCErrorError:
    if sandbox.cwd is not None:
        return sandbox.cwd
    if sandbox.has_cwd_dependent_permissions():
        return invalid_request("file system sandbox context with dynamic permissions requires cwd")
    return AbsolutePathBuf.from_absolute_path(Path.cwd())


def helper_read_roots(runtime_paths: ExecServerRuntimePaths) -> list[AbsolutePathBuf]:
    roots: list[AbsolutePathBuf] = []
    for path in (runtime_paths.codex_self_exe, runtime_paths.codex_linux_sandbox_exe):
        if path is None:
            continue
        parent = path.as_path().parent
        root = AbsolutePathBuf.from_absolute_path(parent)
        if root not in roots:
            roots.append(root)
    return roots


def add_helper_runtime_permissions(
    file_system_policy: FileSystemSandboxPolicy,
    helper_read_roots_value: list[AbsolutePathBuf] | tuple[AbsolutePathBuf, ...],
    cwd: str | Path,
) -> FileSystemSandboxPolicy:
    entries = list(file_system_policy.entries)
    if not file_system_policy.has_full_disk_read_access():
        minimal_read_entry = FileSystemSandboxEntry(
            FileSystemPath.special(FileSystemSpecialPath.minimal()),
            FileSystemAccessMode.READ,
        )
        if minimal_read_entry not in entries:
            entries.append(minimal_read_entry)

    candidate = file_system_policy
    for helper_read_root in helper_read_roots_value:
        if candidate.can_read_path_with_cwd(helper_read_root.as_path(), cwd):
            continue
        entry = FileSystemSandboxEntry(
            FileSystemPath.explicit_path(helper_read_root.as_path()),
            FileSystemAccessMode.READ,
        )
        if entry not in entries:
            entries.append(entry)
        candidate = candidate._replace(entries=tuple(entries))

    return file_system_policy._replace(entries=tuple(entries))


def helper_env() -> dict[str, str]:
    return helper_env_from_vars(os.environ.items())


def helper_env_from_vars(vars_iter: Any) -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in vars_iter:
        key_text = os.fsdecode(key)
        if helper_env_key_is_allowed(key_text):
            env[key_text] = os.fsdecode(value)
    return env


def helper_env_key_is_allowed(key: str) -> bool:
    return (
        key in FS_HELPER_ENV_ALLOWLIST
        or bazel_bwrap_env_key_is_allowed(key)
        or (os.name == "nt" and key.lower() == "path")
    )


def bazel_bwrap_env_key_is_allowed(key: str) -> bool:
    return os.environ.get("BAZEL_PACKAGE") is not None and key in FS_HELPER_BAZEL_BWRAP_ENV_ALLOWLIST


def _file_system_path_is_cwd_dependent(path: FileSystemPath) -> bool:
    if path.type == "special" and path.value is not None:
        return path.value.kind == "project_roots"
    if path.type == "glob_pattern" and path.pattern is not None:
        return "codex-project-roots://" in path.pattern
    return False


from pycodex.exec_server.fs_helper import CODEX_FS_HELPER_ARG1, FsHelperPayload, FsHelperRequest, FsHelperResponse
from pycodex.exec_server.rpc import _maybe_await
from pycodex.exec_server.runtime_paths import ExecServerRuntimePaths
