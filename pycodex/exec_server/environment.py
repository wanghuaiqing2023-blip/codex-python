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


CODEX_EXEC_SERVER_URL_ENV_VAR = "CODEX_EXEC_SERVER_URL"


LOCAL_ENVIRONMENT_ID = "local"


REMOTE_ENVIRONMENT_ID = "remote"


@dataclass(frozen=True)
class Environment:
    exec_server_url_value: str | None = None
    remote_transport: ExecServerTransportParams | None = None
    local_runtime_paths: ExecServerRuntimePaths | None = None
    exec_backend: ExecBackend | None = None
    filesystem: ExecutorFileSystem | None = None
    http_client: Any | None = None

    @classmethod
    def default_for_tests(cls) -> "Environment":
        return cls(
            exec_backend=LocalProcess.new(None),
            filesystem=LocalFileSystem.unsandboxed(),
            http_client=ReqwestHttpClient(),
        )

    @classmethod
    def create(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths,
    ) -> "Environment":
        return cls._create_inner(exec_server_url, local_runtime_paths)

    @classmethod
    def create_for_tests(cls, exec_server_url: str | None = None) -> "Environment":
        return cls._create_inner(exec_server_url, None)

    @classmethod
    def _create_inner(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths | None,
    ) -> "Environment":
        normalized_url, disabled = normalize_exec_server_url(exec_server_url)
        if disabled:
            raise ExecServerError.protocol("disabled mode does not create an Environment")
        if normalized_url is not None:
            return cls.remote_inner(normalized_url, local_runtime_paths)
        if local_runtime_paths is not None:
            return cls.local(local_runtime_paths)
        return cls.default_for_tests()

    @classmethod
    def local(cls, local_runtime_paths: ExecServerRuntimePaths) -> "Environment":
        return cls(
            local_runtime_paths=local_runtime_paths,
            exec_backend=LocalProcess.new(None),
            filesystem=LocalFileSystem.with_runtime_paths(local_runtime_paths),
            http_client=ReqwestHttpClient(),
        )

    @classmethod
    def remote_inner(
        cls,
        exec_server_url: str,
        local_runtime_paths: ExecServerRuntimePaths | None = None,
    ) -> "Environment":
        return cls.remote_with_transport(
            ExecServerTransportParams.from_websocket_url(exec_server_url),
            local_runtime_paths,
        )

    @classmethod
    def remote_with_transport(
        cls,
        remote_transport: ExecServerTransportParams,
        local_runtime_paths: ExecServerRuntimePaths | None = None,
    ) -> "Environment":
        exec_server_url = (
            remote_transport.websocket_url
            if remote_transport.kind is ExecServerTransportKind.WEBSOCKET_URL
            else None
        )
        return cls(
            exec_server_url_value=exec_server_url,
            remote_transport=remote_transport,
            local_runtime_paths=local_runtime_paths,
            exec_backend=RemoteProcessBoundary(remote_transport),
            filesystem=RemoteFileSystemBoundary(remote_transport),
            http_client=LazyRemoteExecServerClient(remote_transport),
        )

    def is_remote(self) -> bool:
        return self.exec_server_url_value is not None or self.remote_transport is not None

    def exec_server_url(self) -> str | None:
        return self.exec_server_url_value

    def get_exec_backend(self) -> ExecBackend:
        return self.exec_backend if self.exec_backend is not None else LocalProcess.new(None)

    def get_filesystem(self) -> ExecutorFileSystem:
        return self.filesystem if self.filesystem is not None else LocalFileSystem.unsandboxed()

    def get_http_client(self) -> Any:
        return self.http_client if self.http_client is not None else ReqwestHttpClient()


class EnvironmentManager:
    def __init__(
        self,
        environments: dict[str, Environment] | None = None,
        default_environment: str | None = LOCAL_ENVIRONMENT_ID,
        local_runtime_paths: ExecServerRuntimePaths | None = None,
        local_environment: Environment | None = None,
    ) -> None:
        self.environments = (
            {LOCAL_ENVIRONMENT_ID: Environment.default_for_tests()} if environments is None else environments
        )
        self._default_environment = default_environment
        self.local_runtime_paths = local_runtime_paths
        self.local_environment = local_environment or self.environments.get(LOCAL_ENVIRONMENT_ID)

    @classmethod
    def default_for_tests(cls) -> "EnvironmentManager":
        local = Environment.default_for_tests()
        return cls({LOCAL_ENVIRONMENT_ID: local}, LOCAL_ENVIRONMENT_ID, None, local)

    @classmethod
    def without_environments(cls) -> "EnvironmentManager":
        return cls({}, None, None, None)

    @classmethod
    def create_for_tests(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths | None,
    ) -> "EnvironmentManager":
        provider = DefaultEnvironmentProvider.new(exec_server_url)
        return cls.from_snapshot(provider.snapshot_inner(), local_runtime_paths)

    @classmethod
    def create_for_tests_with_local(
        cls,
        exec_server_url: str | None,
        local_runtime_paths: ExecServerRuntimePaths,
    ) -> "EnvironmentManager":
        snapshot = DefaultEnvironmentProvider.new(exec_server_url).snapshot_inner()
        return cls.from_snapshot(
            EnvironmentProviderSnapshot(
                environments=list(snapshot.environments),
                default=snapshot.default,
                include_local=True,
            ),
            local_runtime_paths,
        )

    @classmethod
    def from_snapshot(
        cls,
        snapshot: EnvironmentProviderSnapshot,
        local_runtime_paths: ExecServerRuntimePaths | None,
    ) -> "EnvironmentManager":
        environment_map: dict[str, Environment] = {}
        local_environment = None
        if snapshot.include_local:
            if local_runtime_paths is None:
                raise ExecServerError.protocol("local environment requires configured runtime paths")
            local_environment = Environment.local(local_runtime_paths)
            environment_map[LOCAL_ENVIRONMENT_ID] = local_environment
        for environment_id, environment in snapshot.environments:
            if environment_id == "":
                raise ExecServerError.protocol("environment id cannot be empty")
            if environment_id == LOCAL_ENVIRONMENT_ID:
                raise ExecServerError.protocol(
                    f"environment id `{LOCAL_ENVIRONMENT_ID}` is reserved for EnvironmentManager"
                )
            if environment_id in environment_map:
                raise ExecServerError.protocol(f"environment id `{environment_id}` is duplicated")
            environment_map[environment_id] = environment
        if snapshot.default.kind is EnvironmentDefaultKind.DISABLED:
            default_environment = None
        else:
            default_environment = snapshot.default.environment_id
            if default_environment not in environment_map:
                raise ExecServerError.protocol(f"default environment `{default_environment}` is not configured")
        return cls(environment_map, default_environment, local_runtime_paths, local_environment)

    def default_environment(self) -> Environment | None:
        return self.get_environment(self._default_environment) if self._default_environment else None

    def default_environment_id(self) -> str | None:
        return self._default_environment

    def default_environment_ids(self) -> list[str]:
        if not self._default_environment:
            return []
        rest = [key for key in self.environments if key != self._default_environment]
        return [self._default_environment, *rest]

    def try_local_environment(self) -> Environment | None:
        return self.local_environment

    def default_or_local_environment(self) -> Environment | None:
        return self.default_environment() or self.try_local_environment()

    def get_environment(self, environment_id: str | None) -> Environment | None:
        return self.environments.get(environment_id or "")

    def upsert_environment(self, environment_id: str, exec_server_url: str) -> None:
        if not environment_id:
            raise ExecServerError.protocol("environment id cannot be empty")
        normalized_url, disabled = normalize_exec_server_url(exec_server_url)
        if disabled:
            raise ExecServerError.protocol("remote environment cannot use disabled exec-server url")
        if normalized_url is None:
            raise ExecServerError.protocol("remote environment requires an exec-server url")
        self.environments[environment_id] = Environment.remote_inner(normalized_url, self.local_runtime_paths)


from pycodex.exec_server.client import ExecServerError, LazyRemoteExecServerClient
from pycodex.exec_server.client.http_client.reqwest_http_client import ReqwestHttpClient
from pycodex.exec_server.client_api import ExecServerTransportKind, ExecServerTransportParams
from pycodex.exec_server.environment_provider import DefaultEnvironmentProvider, EnvironmentDefaultKind, EnvironmentProviderSnapshot, normalize_exec_server_url
from pycodex.exec_server.local_file_system import LocalFileSystem
from pycodex.exec_server.local_process import LocalProcess
from pycodex.exec_server.process import ExecBackend
from pycodex.exec_server.remote_file_system import RemoteFileSystemBoundary
from pycodex.exec_server.remote_process import RemoteProcessBoundary
from pycodex.exec_server.runtime_paths import ExecServerRuntimePaths
