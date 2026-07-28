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


ERROR_BODY_PREVIEW_BYTES = 4096


@dataclass(frozen=True)
class RemoteEnvironmentConfig:
    base_url: str
    environment_id: str
    auth_provider: Any
    name: str = "codex-exec-server"

    @classmethod
    def new(
        cls,
        base_url: str,
        environment_id: str,
        auth_provider: Any,
    ) -> "RemoteEnvironmentConfig":
        return cls(
            base_url=base_url,
            environment_id=normalize_environment_id(environment_id),
            auth_provider=auth_provider,
        )

    def __repr__(self) -> str:
        return (
            "RemoteEnvironmentConfig("
            f"base_url={self.base_url!r}, "
            f"environment_id={self.environment_id!r}, "
            f"name={self.name!r}, "
            "auth_provider='<redacted>')"
        )


@dataclass(frozen=True)
class EnvironmentRegistryRegistrationResponse:
    environment_id: str
    url: str


class EnvironmentRegistryClient:
    def __init__(self, base_url: str, auth_provider: Any, http: Any | None = None) -> None:
        self.base_url = normalize_base_url(base_url)
        self.auth_provider = auth_provider
        self.http = http

    @classmethod
    def new(cls, base_url: str, auth_provider: Any, http: Any | None = None) -> "EnvironmentRegistryClient":
        return cls(base_url, auth_provider, http)

    def __repr__(self) -> str:
        return (
            "EnvironmentRegistryClient("
            f"base_url={self.base_url!r}, "
            "auth_provider='<redacted>', ..)"
        )

    async def register_environment(self, environment_id: str) -> EnvironmentRegistryRegistrationResponse:
        if self.http is None:
            raise ExecServerError.environment_registry_config(
                "environment registry HTTP client is not configured"
            )
        response = self.http.post(
            endpoint_url(self.base_url, f"/cloud/environment/{environment_id}/register"),
            headers=auth_provider_headers(self.auth_provider),
            follow_redirects=False,
        )
        if inspect.isawaitable(response):
            response = await response
        return await self.parse_json_response(response)

    async def parse_json_response(self, response: Any) -> EnvironmentRegistryRegistrationResponse:
        status = response_status(response)
        if 200 <= status < 300:
            payload = response_json(response)
            if inspect.isawaitable(payload):
                payload = await payload
            try:
                return EnvironmentRegistryRegistrationResponse(
                    environment_id=str(payload["environment_id"]),
                    url=str(payload["url"]),
                )
            except Exception as exc:
                raise ExecServerError(f"failed to parse environment registry response: {exc}") from exc

        body = response_text(response)
        if inspect.isawaitable(body):
            body = await body
        if status in {401, 403}:
            raise environment_registry_auth_error(status, body)
        raise environment_registry_http_error(status, body)


def auth_provider_headers(auth_provider: Any) -> dict[str, str]:
    if hasattr(auth_provider, "to_auth_headers"):
        return dict(auth_provider.to_auth_headers())
    if hasattr(auth_provider, "add_auth_headers"):
        headers: dict[str, str] = {}
        auth_provider.add_auth_headers(headers)
        return headers
    if isinstance(auth_provider, Mapping):
        return dict(auth_provider)
    return {}


def response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if callable(status):
        status = status()
    if hasattr(status, "value"):
        status = status.value
    return int(status)


def response_json(response: Any) -> Any:
    json_method = getattr(response, "json", None)
    if callable(json_method):
        return json_method()
    return getattr(response, "json_body")


def response_text(response: Any) -> str:
    text_method = getattr(response, "text", None)
    if callable(text_method):
        return text_method()
    return str(getattr(response, "body", ""))


def normalize_environment_id(environment_id: str) -> str:
    normalized = environment_id.strip()
    if not normalized:
        raise ExecServerError.environment_registry_config(
            "environment id is required for remote exec-server registration"
        )
    return normalized


def normalize_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        raise ExecServerError.environment_registry_config(
            "environment registry base URL is required"
        )
    return normalized


def endpoint_url(base_url: str, path: str) -> str:
    return f"{base_url}/{path.lstrip('/')}"


def environment_registry_auth_error(status: int, body: str) -> ExecServerError:
    message = registry_error_message(body) or "empty error body"
    return ExecServerError.environment_registry_auth(
        f"environment registry authentication failed ({status_text(status)}): {message}"
    )


def environment_registry_http_error(status: int, body: str) -> ExecServerError:
    code: str | None = None
    message: str | None = None
    try:
        error = json.loads(body).get("error")
        if isinstance(error, Mapping):
            raw_code = error.get("code")
            code = str(raw_code) if raw_code is not None else None
            raw_message = error.get("message")
            if raw_message is not None:
                message = str(raw_message)
    except Exception:
        pass
    if message is None:
        message = preview_error_body(body) or "empty or malformed error body"
    return ExecServerError.environment_registry_http(status, code, message)


def registry_error_message(body: str) -> str | None:
    try:
        error = json.loads(body).get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if message is not None:
                return str(message)
    except Exception:
        pass
    return preview_error_body(body)


def preview_error_body(body: str) -> str | None:
    trimmed = body.strip()
    if not trimmed:
        return None
    return "".join(list(trimmed)[:ERROR_BODY_PREVIEW_BYTES])


def status_text(status: int) -> str:
    known = {
        302: "Found",
        401: "Unauthorized",
        403: "Forbidden",
    }
    reason = known.get(status)
    return f"{status} {reason}" if reason else str(status)


async def run_remote_environment(
    config: RemoteEnvironmentConfig,
    runtime_paths: ExecServerRuntimePaths,
    *,
    registry_client: Any | None = None,
    websocket_connector: Any | None = None,
    serve_environment: Any | None = None,
    sleep: Any | None = None,
    max_iterations: int | None = None,
    stderr: Any | None = None,
) -> None:
    client = registry_client or EnvironmentRegistryClient.new(config.base_url, config.auth_provider)
    processor = ConnectionProcessor.new(runtime_paths)
    connect = websocket_connector or _connect_remote_environment_websocket
    serve = serve_environment or run_multiplexed_environment
    sleep_fn = sleep or asyncio.sleep
    backoff = 1
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        response = await client.register_environment(config.environment_id)
        print(
            "codex exec-server remote environment registered with environment_id "
            f"{response.environment_id}",
            file=stderr or sys.stderr,
        )
        try:
            websocket = await _maybe_await(connect(response.url))
        except Exception:
            websocket = None
        if websocket is not None:
            backoff = 1
            await _maybe_await(serve(websocket, processor))
        await _maybe_await(sleep_fn(backoff))
        backoff = min(backoff * 2, 30)
        iterations += 1


async def _connect_remote_environment_websocket(_url: str) -> Any:
    return await _connect_websocket_url(_url)


from pycodex.exec_server.client import ExecServerError
from pycodex.exec_server.relay import run_multiplexed_environment
from pycodex.exec_server.rpc import _maybe_await
from pycodex.exec_server.runtime_paths import ExecServerRuntimePaths
from pycodex.exec_server.server.processor import ConnectionProcessor
from pycodex.exec_server.server.transport import _connect_websocket_url
