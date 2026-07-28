"""Environment and HTTP header helpers owned by ``codex-rmcp-client::utils``."""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.config.mcp_types import McpServerEnvVar
from pycodex.protocol.shell_environment import WINDOWS_CORE_ENV_VARS

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

if sys.platform == "win32":
    DEFAULT_ENV_VARS = WINDOWS_CORE_ENV_VARS
else:
    DEFAULT_ENV_VARS = (
        "HOME",
        "LOGNAME",
        "PATH",
        "SHELL",
        "USER",
        "__CF_USER_TEXT_ENCODING",
        "LANG",
        "LC_ALL",
        "TERM",
        "TMPDIR",
        "TZ",
    )


def _env_var(value: McpServerEnvVar | str | Mapping[str, Any]) -> McpServerEnvVar:
    return McpServerEnvVar.from_value(value)


def create_env_for_mcp_server(
    extra_env: Mapping[str, str] | None,
    env_vars: Iterable[McpServerEnvVar | str | Mapping[str, Any]],
) -> dict[str, str]:
    parsed = tuple(_env_var(value) for value in env_vars)
    remote = next((value for value in parsed if value.is_remote_source()), None)
    if remote is not None:
        raise ValueError(
            f"env_vars entry `{remote.name()}` uses source `remote`, "
            "which requires remote MCP stdio"
        )
    names = (*DEFAULT_ENV_VARS, *(value.name() for value in parsed))
    environment = {
        name: os.environ[name]
        for name in names
        if name in os.environ
    }
    environment.update(dict(extra_env or {}))
    return environment


def create_env_overlay_for_remote_mcp_server(
    extra_env: Mapping[str, str] | None,
    env_vars: Iterable[McpServerEnvVar | str | Mapping[str, Any]],
) -> dict[str, str]:
    environment = {
        value.name(): os.environ[value.name()]
        for raw in env_vars
        if not (value := _env_var(raw)).is_remote_source()
        and value.name() in os.environ
    }
    environment.update(dict(extra_env or {}))
    return environment


def remote_mcp_env_var_names(
    env_vars: Iterable[McpServerEnvVar | str | Mapping[str, Any]],
) -> tuple[str, ...]:
    return tuple(
        value.name()
        for raw in env_vars
        if (value := _env_var(raw)).is_remote_source()
    )


def _valid_header(name: str, value: str) -> bool:
    return bool(_HEADER_NAME.fullmatch(name)) and "\r" not in value and "\n" not in value


def build_default_headers(
    http_headers: Mapping[str, str] | None,
    env_http_headers: Mapping[str, str] | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in (http_headers or {}).items():
        name = str(name)
        value = str(value)
        if _valid_header(name, value):
            headers[name.lower()] = value
    for name, env_var in (env_http_headers or {}).items():
        value = os.environ.get(str(env_var))
        name = str(name)
        if value is None or not value.strip() or not _valid_header(name, value):
            continue
        headers[name.lower()] = value
    return headers


def apply_default_headers(
    headers: Mapping[str, str] | None,
    default_headers: Mapping[str, str],
) -> dict[str, str]:
    merged = dict(default_headers)
    merged.update({str(name).lower(): str(value) for name, value in (headers or {}).items()})
    return merged


__all__ = [
    "DEFAULT_ENV_VARS",
    "apply_default_headers",
    "build_default_headers",
    "create_env_for_mcp_server",
    "create_env_overlay_for_remote_mcp_server",
    "remote_mcp_env_var_names",
]
