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


ENVIRONMENTS_TOML_FILE = "environments.toml"


MAX_ENVIRONMENT_ID_LEN = 64


@dataclass(frozen=True)
class EnvironmentToml:
    id: str
    url: str | None = None
    program: str | None = None
    args: list[str] | None = None
    env: dict[str, str] | None = None
    cwd: Path | None = None
    connect_timeout_sec: int | float | None = None
    initialize_timeout_sec: int | float | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "EnvironmentToml":
        _reject_unknown_fields(
            data,
            {
                "id",
                "url",
                "program",
                "args",
                "env",
                "cwd",
                "connect_timeout_sec",
                "initialize_timeout_sec",
            },
        )
        return cls(
            id=str(data.get("id", "")),
            url=_optional_str(data.get("url")),
            program=_optional_str(data.get("program")),
            args=_optional_str_list(data.get("args")),
            env=_optional_str_dict(data.get("env")),
            cwd=Path(data["cwd"]) if data.get("cwd") is not None else None,
            connect_timeout_sec=_optional_duration_seconds(data.get("connect_timeout_sec")),
            initialize_timeout_sec=_optional_duration_seconds(data.get("initialize_timeout_sec")),
        )


@dataclass(frozen=True)
class EnvironmentsToml:
    default: str | None = None
    include_local: bool | None = None
    environments: list[EnvironmentToml] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "EnvironmentsToml":
        _reject_unknown_fields(data, {"default", "include_local", "environments"})
        environments_raw = data.get("environments", [])
        if not isinstance(environments_raw, list):
            raise ExecServerError.protocol("environment config environments must be a list")
        include_local = data.get("include_local")
        if include_local is not None and not isinstance(include_local, bool):
            raise ExecServerError.protocol("environment config include_local must be a boolean")
        return cls(
            default=_optional_str(data.get("default")),
            include_local=include_local,
            environments=[EnvironmentToml.from_mapping(item) for item in environments_raw],
        )


@dataclass(frozen=True)
class TomlEnvironmentProvider:
    default: EnvironmentDefault
    include_local: bool
    environments: list[tuple[str, ExecServerTransportParams]]

    @classmethod
    def new(cls, config: EnvironmentsToml) -> "TomlEnvironmentProvider":
        return cls.new_with_config_dir(config, None)

    @classmethod
    def new_with_config_dir(
        cls,
        config: EnvironmentsToml,
        config_dir: str | Path | None,
    ) -> "TomlEnvironmentProvider":
        include_local = True if config.include_local is None else config.include_local
        ids: set[str] = set()
        if include_local:
            ids.add(LOCAL_ENVIRONMENT_ID)
        parsed_environments: list[tuple[str, ExecServerTransportParams]] = []
        config_dir_path = Path(config_dir) if config_dir is not None else None
        for item in config.environments:
            environment_id, transport = parse_environment_toml(item, config_dir_path)
            if environment_id in ids:
                raise ExecServerError.protocol(f"environment id `{environment_id}` is duplicated")
            ids.add(environment_id)
            parsed_environments.append((environment_id, transport))
        default = normalize_default_environment_id(config.default, include_local, ids)
        return cls(default=default, include_local=include_local, environments=parsed_environments)

    def snapshot(self) -> EnvironmentProviderSnapshot:
        return EnvironmentProviderSnapshot(
            environments=[
                (environment_id, Environment.remote_with_transport(transport, local_runtime_paths=None))
                for environment_id, transport in self.environments
            ],
            default=self.default,
            include_local=self.include_local,
        )


def parse_environment_toml(
    item: EnvironmentToml,
    config_dir: str | Path | None = None,
) -> tuple[str, ExecServerTransportParams]:
    validate_environment_id(item.id)
    if item.program is None and (item.args is not None or item.env is not None or item.cwd is not None):
        raise ExecServerError.protocol(f"environment `{item.id}` args, env, and cwd require program")
    if item.url is None and item.connect_timeout_sec is not None:
        raise ExecServerError.protocol(f"environment `{item.id}` connect_timeout_sec requires url")

    connect_timeout = (
        DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT
        if item.connect_timeout_sec is None
        else item.connect_timeout_sec
    )
    initialize_timeout = (
        DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT
        if item.initialize_timeout_sec is None
        else item.initialize_timeout_sec
    )

    if item.url is not None and item.program is None:
        url = validate_websocket_url(item.url)
        return (
            item.id,
            ExecServerTransportParams.from_websocket_url(
                url,
                connect_timeout=connect_timeout,
                initialize_timeout=initialize_timeout,
            ),
        )
    if item.url is None and item.program is not None:
        program = item.program.strip()
        if not program:
            raise ExecServerError.protocol(f"environment `{item.id}` program cannot be empty")
        cwd = normalize_stdio_cwd(item.id, item.cwd, config_dir)
        return (
            item.id,
            ExecServerTransportParams.stdio_command(
                StdioExecServerCommand(
                    program=program,
                    args=item.args or [],
                    env=item.env or {},
                    cwd=cwd,
                ),
                initialize_timeout=initialize_timeout,
            ),
        )

    raise ExecServerError.protocol(f"environment `{item.id}` must set exactly one of url or program")


def normalize_stdio_cwd(
    environment_id: str,
    cwd: str | Path | None,
    config_dir: str | Path | None,
) -> Path | None:
    if cwd is None:
        return None
    cwd_path = cwd if isinstance(cwd, Path) else Path(cwd)
    if cwd_path.is_absolute():
        return cwd_path
    if config_dir is None:
        raise ExecServerError.protocol(f"environment `{environment_id}` cwd must be absolute")
    return Path(config_dir) / cwd_path


def normalize_default_environment_id(
    default: str | None,
    include_local: bool,
    ids: set[str],
) -> EnvironmentDefault:
    if default is None:
        if include_local:
            return EnvironmentDefault.environment_id_value(LOCAL_ENVIRONMENT_ID)
        return EnvironmentDefault.disabled()
    default = default.strip()
    if not default:
        raise ExecServerError.protocol("default environment id cannot be empty")
    if default.lower() != "none" and default not in ids:
        raise ExecServerError.protocol(f"default environment `{default}` is not configured")
    if default.lower() == "none":
        return EnvironmentDefault.disabled()
    return EnvironmentDefault.environment_id_value(default)


def validate_environment_id(environment_id: str) -> None:
    trimmed = environment_id.strip()
    if not trimmed:
        raise ExecServerError.protocol("environment id cannot be empty")
    if trimmed != environment_id:
        raise ExecServerError.protocol(
            f"environment id `{environment_id}` must not contain surrounding whitespace"
        )
    if environment_id == LOCAL_ENVIRONMENT_ID or environment_id.lower() == "none":
        raise ExecServerError.protocol(f"environment id `{environment_id}` is reserved")
    if len(environment_id) > MAX_ENVIRONMENT_ID_LEN:
        raise ExecServerError.protocol(
            f"environment id `{environment_id}` cannot be longer than {MAX_ENVIRONMENT_ID_LEN} characters"
        )
    if not all(ch.isascii() and (ch.isalnum() or ch in "-_") for ch in environment_id):
        raise ExecServerError.protocol(
            f"environment id `{environment_id}` must contain only ASCII letters, numbers, '-' or '_'"
        )


def validate_websocket_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise ExecServerError.protocol("environment url cannot be empty")
    if not (url.startswith("ws://") or url.startswith("wss://")):
        raise ExecServerError.protocol(f"environment url `{url}` must use ws:// or wss://")
    # Rust validates with tungstenite's IntoClientRequest. For this dependency-
    # light port, require a non-empty network location after ws:// or wss://.
    rest = url.split("://", 1)[1]
    if not rest or rest.startswith("/") or rest.isspace():
        raise ExecServerError.protocol(f"environment url `{url}` is invalid: invalid URL")
    return url


def load_environments_toml(path: str | Path) -> EnvironmentsToml:
    path = Path(path)
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ExecServerError.protocol(f"failed to read environment config `{path}`: {exc}") from exc
    try:
        data = tomllib.loads(contents)
    except tomllib.TOMLDecodeError as exc:
        raise ExecServerError.protocol(f"failed to parse environment config `{path}`: {exc}") from exc
    return EnvironmentsToml.from_mapping(data)


def environment_provider_from_codex_home(codex_home: str | Path) -> EnvironmentProvider | TomlEnvironmentProvider:
    codex_home = Path(codex_home)
    path = codex_home / ENVIRONMENTS_TOML_FILE
    try:
        exists = path.exists()
    except OSError as exc:
        raise ExecServerError.protocol(f"failed to inspect environment config `{path}`: {exc}") from exc
    if not exists:
        return DefaultEnvironmentProvider.from_env()
    environments = load_environments_toml(path)
    return TomlEnvironmentProvider.new_with_config_dir(environments, codex_home)


def _reject_unknown_fields(data: dict[str, Any], allowed: set[str]) -> None:
    unknown = next((key for key in data if key not in allowed), None)
    if unknown is not None:
        raise ExecServerError.protocol(f"unknown field `{unknown}`")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ExecServerError.protocol("environment config args must be a list")
    return [str(item) for item in value]


def _optional_str_dict(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ExecServerError.protocol("environment config env must be a table")
    return {str(key): str(item) for key, item in value.items()}


def _optional_duration_seconds(value: Any) -> int | float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ExecServerError.protocol("duration value must be a non-negative number of seconds")
    return value


from pycodex.exec_server.client import ExecServerError
from pycodex.exec_server.client_api import DEFAULT_REMOTE_EXEC_SERVER_CONNECT_TIMEOUT, DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT, ExecServerTransportParams, StdioExecServerCommand
from pycodex.exec_server.environment import Environment, LOCAL_ENVIRONMENT_ID
from pycodex.exec_server.environment_provider import DefaultEnvironmentProvider, EnvironmentDefault, EnvironmentProvider, EnvironmentProviderSnapshot
