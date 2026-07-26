"""Rust-aligned projection of ``codex-network-proxy::proxy``."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import fnmatch
import json
import os
import re
import socket
import stat
import sys
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Mapping, Sequence

JsonValue = Any

PROXY_URL_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "WS_PROXY",
    "WSS_PROXY",
    "ALL_PROXY",
    "FTP_PROXY",
    "YARN_HTTP_PROXY",
    "YARN_HTTPS_PROXY",
    "NPM_CONFIG_HTTP_PROXY",
    "NPM_CONFIG_HTTPS_PROXY",
    "NPM_CONFIG_PROXY",
    "BUNDLE_HTTP_PROXY",
    "BUNDLE_HTTPS_PROXY",
    "PIP_PROXY",
    "DOCKER_HTTP_PROXY",
    "DOCKER_HTTPS_PROXY",
)


ALL_PROXY_ENV_KEYS = ("ALL_PROXY", "all_proxy")


PROXY_ACTIVE_ENV_KEY = "CODEX_NETWORK_PROXY_ACTIVE"


ALLOW_LOCAL_BINDING_ENV_KEY = "CODEX_NETWORK_ALLOW_LOCAL_BINDING"


ELECTRON_GET_USE_PROXY_ENV_KEY = "ELECTRON_GET_USE_PROXY"


NODE_USE_ENV_PROXY_ENV_KEY = "NODE_USE_ENV_PROXY"


PROXY_GIT_SSH_COMMAND_ENV_KEY = "GIT_SSH_COMMAND"


CODEX_PROXY_GIT_SSH_COMMAND_MARKER = "CODEX_PROXY_GIT_SSH_COMMAND=1 "


_CODEX_PROXY_GIT_SSH_COMMAND_PREFIX = (
    "CODEX_PROXY_GIT_SSH_COMMAND=1 ssh -o ProxyCommand='nc -X 5 -x "
)


_CODEX_PROXY_GIT_SSH_COMMAND_SUFFIX = " %h %p'"


PROXY_ENV_KEYS = (
    PROXY_ACTIVE_ENV_KEY,
    ALLOW_LOCAL_BINDING_ENV_KEY,
    ELECTRON_GET_USE_PROXY_ENV_KEY,
    NODE_USE_ENV_PROXY_ENV_KEY,
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "YARN_HTTP_PROXY",
    "YARN_HTTPS_PROXY",
    "npm_config_http_proxy",
    "npm_config_https_proxy",
    "npm_config_proxy",
    "NPM_CONFIG_HTTP_PROXY",
    "NPM_CONFIG_HTTPS_PROXY",
    "NPM_CONFIG_PROXY",
    "BUNDLE_HTTP_PROXY",
    "BUNDLE_HTTPS_PROXY",
    "PIP_PROXY",
    "DOCKER_HTTP_PROXY",
    "DOCKER_HTTPS_PROXY",
    "WS_PROXY",
    "WSS_PROXY",
    "ws_proxy",
    "wss_proxy",
    "NO_PROXY",
    "no_proxy",
    "npm_config_noproxy",
    "NPM_CONFIG_NOPROXY",
    "YARN_NO_PROXY",
    "BUNDLE_NO_PROXY",
    "ALL_PROXY",
    "all_proxy",
    "FTP_PROXY",
    "ftp_proxy",
)


FTP_PROXY_ENV_KEYS = ("FTP_PROXY", "ftp_proxy")


WEBSOCKET_PROXY_ENV_KEYS = ("WS_PROXY", "WSS_PROXY", "ws_proxy", "wss_proxy")


NO_PROXY_ENV_KEYS = (
    "NO_PROXY",
    "no_proxy",
    "npm_config_noproxy",
    "NPM_CONFIG_NOPROXY",
    "YARN_NO_PROXY",
    "BUNDLE_NO_PROXY",
)


DEFAULT_NO_PROXY_VALUE = "localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"


_ADDR_IN_USE_ERRNOS = {48, 98, 10048}


def proxy_url_env_value(env: Mapping[str, str], canonical_key: str) -> str | None:
    if canonical_key in env:
        return env[canonical_key]
    return env.get(canonical_key.lower())


def has_proxy_url_env_vars(env: Mapping[str, str]) -> bool:
    for key in PROXY_URL_ENV_KEYS:
        value = proxy_url_env_value(env, key)
        if value is not None and value.strip():
            return True
    return False


def apply_proxy_env_overrides(
    env: MutableMapping[str, str],
    http_addr: str | tuple[str, int],
    socks_addr: str | tuple[str, int],
    *,
    socks_enabled: bool,
    allow_local_binding: bool,
) -> None:
    http_endpoint = _proxy_socket_addr(http_addr)
    socks_endpoint = _proxy_socket_addr(socks_addr)
    http_proxy_url = f"http://{http_endpoint}"
    socks_proxy_url = f"socks5h://{socks_endpoint}"
    env[PROXY_ACTIVE_ENV_KEY] = "1"
    env[ALLOW_LOCAL_BINDING_ENV_KEY] = "1" if allow_local_binding else "0"
    _set_env_keys(
        env,
        (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "http_proxy",
            "https_proxy",
            "YARN_HTTP_PROXY",
            "YARN_HTTPS_PROXY",
            "npm_config_http_proxy",
            "npm_config_https_proxy",
            "npm_config_proxy",
            "NPM_CONFIG_HTTP_PROXY",
            "NPM_CONFIG_HTTPS_PROXY",
            "NPM_CONFIG_PROXY",
            "BUNDLE_HTTP_PROXY",
            "BUNDLE_HTTPS_PROXY",
            "PIP_PROXY",
            "DOCKER_HTTP_PROXY",
            "DOCKER_HTTPS_PROXY",
        ),
        http_proxy_url,
    )
    _set_env_keys(env, WEBSOCKET_PROXY_ENV_KEYS, http_proxy_url)
    _set_env_keys(env, NO_PROXY_ENV_KEYS, DEFAULT_NO_PROXY_VALUE)
    env[ELECTRON_GET_USE_PROXY_ENV_KEY] = "true"
    env[NODE_USE_ENV_PROXY_ENV_KEY] = "1"
    if socks_enabled:
        _set_env_keys(env, ALL_PROXY_ENV_KEYS, socks_proxy_url)
        _set_env_keys(env, FTP_PROXY_ENV_KEYS, socks_proxy_url)
    else:
        _set_env_keys(env, ALL_PROXY_ENV_KEYS, http_proxy_url)
        _set_env_keys(env, FTP_PROXY_ENV_KEYS, http_proxy_url)
    if sys.platform == "darwin" and socks_enabled:
        command = env.get(PROXY_GIT_SSH_COMMAND_ENV_KEY)
        if command is None or is_codex_proxy_git_ssh_command(command):
            env[PROXY_GIT_SSH_COMMAND_ENV_KEY] = codex_proxy_git_ssh_command(socks_addr)


def codex_proxy_git_ssh_command(socks_addr: str | tuple[str, int]) -> str:
    return (
        f"{_CODEX_PROXY_GIT_SSH_COMMAND_PREFIX}"
        f"{_proxy_socket_addr(socks_addr)}"
        f"{_CODEX_PROXY_GIT_SSH_COMMAND_SUFFIX}"
    )


def is_codex_proxy_git_ssh_command(command: str) -> bool:
    return command.startswith(_CODEX_PROXY_GIT_SSH_COMMAND_PREFIX) and command.endswith(
        _CODEX_PROXY_GIT_SSH_COMMAND_SUFFIX
    )


@dataclass
class ReservedListenerSet:
    http_listener: socket.socket
    socks_listener: socket.socket | None = None

    def take_http(self) -> socket.socket | None:
        listener = self.http_listener
        self.http_listener = None  # type: ignore[assignment]
        return listener

    def take_socks(self) -> socket.socket | None:
        listener = self.socks_listener
        self.socks_listener = None
        return listener

    def http_addr(self) -> tuple[str, int]:
        host, port = self.http_listener.getsockname()[:2]
        return str(host), int(port)

    def socks_addr(self, default_addr: str | tuple[str, int]) -> tuple[str, int]:
        if self.socks_listener is None:
            return _parse_socket_addr(default_addr)
        host, port = self.socks_listener.getsockname()[:2]
        return str(host), int(port)

    def close(self) -> None:
        if self.http_listener is not None:
            self.http_listener.close()
        if self.socks_listener is not None:
            self.socks_listener.close()

    def __enter__(self) -> "ReservedListenerSet":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def windows_managed_loopback_addr(addr: str | tuple[str, int]) -> tuple[str, int]:
    _host, port = _parse_socket_addr(addr)
    return "127.0.0.1", port


def reserve_loopback_ephemeral_listeners(reserve_socks_listener: bool) -> ReservedListenerSet:
    http_listener = _reserve_tcp_listener(("127.0.0.1", 0))
    socks_listener: socket.socket | None = None
    try:
        if reserve_socks_listener:
            socks_listener = _reserve_tcp_listener(("127.0.0.1", 0))
        return ReservedListenerSet(http_listener, socks_listener)
    except Exception:
        http_listener.close()
        if socks_listener is not None:
            socks_listener.close()
        raise


def reserve_windows_managed_listeners(
    http_addr: str | tuple[str, int],
    socks_addr: str | tuple[str, int],
    *,
    reserve_socks_listener: bool,
) -> ReservedListenerSet:
    managed_http_addr = windows_managed_loopback_addr(http_addr)
    managed_socks_addr = windows_managed_loopback_addr(socks_addr)
    try:
        return _try_reserve_windows_managed_listeners(
            managed_http_addr,
            managed_socks_addr,
            reserve_socks_listener=reserve_socks_listener,
        )
    except OSError as exc:
        if exc.errno not in _ADDR_IN_USE_ERRNOS:
            raise
        return reserve_loopback_ephemeral_listeners(reserve_socks_listener)


def _try_reserve_windows_managed_listeners(
    http_addr: tuple[str, int],
    socks_addr: tuple[str, int],
    *,
    reserve_socks_listener: bool,
) -> ReservedListenerSet:
    http_listener = _reserve_tcp_listener(http_addr)
    socks_listener: socket.socket | None = None
    try:
        if reserve_socks_listener:
            socks_listener = _reserve_tcp_listener(socks_addr)
        return ReservedListenerSet(http_listener, socks_listener)
    except Exception:
        http_listener.close()
        if socks_listener is not None:
            socks_listener.close()
        raise


@dataclass(frozen=True)
class NetworkProxyRuntimeSettings:
    allow_local_binding: bool
    allow_unix_sockets: tuple[str, ...]
    dangerously_allow_all_unix_sockets: bool

    @classmethod
    def from_config(cls, config: NetworkProxyConfig) -> "NetworkProxyRuntimeSettings":
        return cls(
            allow_local_binding=config.network.allow_local_binding,
            allow_unix_sockets=tuple(config.network.allow_unix_sockets_effective()),
            dangerously_allow_all_unix_sockets=config.network.dangerously_allow_all_unix_sockets,
        )


class NetworkProxy:
    def __init__(
        self,
        *,
        state: NetworkProxyState,
        http_addr: tuple[str, int],
        socks_addr: tuple[str, int],
        socks_enabled: bool,
        runtime_settings: NetworkProxyRuntimeSettings,
        reserved_listeners: ReservedListenerSet | None = None,
        policy_decider: object | None = None,
    ) -> None:
        self.state = state
        self._http_addr = (str(http_addr[0]), int(http_addr[1]))
        self._socks_addr = (str(socks_addr[0]), int(socks_addr[1]))
        self.socks_enabled = bool(socks_enabled)
        self._runtime_settings = runtime_settings
        self.reserved_listeners = reserved_listeners
        self.policy_decider = policy_decider

    @classmethod
    def builder(cls) -> "NetworkProxyBuilder":
        return NetworkProxyBuilder()

    def http_addr(self) -> tuple[str, int]:
        return self._http_addr

    def socks_addr(self) -> tuple[str, int]:
        return self._socks_addr

    async def current_cfg(self) -> NetworkProxyConfig:
        return await self.state.current_cfg()

    async def add_allowed_domain(self, host: str) -> None:
        await self.state.add_allowed_domain(host)

    async def add_denied_domain(self, host: str) -> None:
        await self.state.add_denied_domain(host)

    def allow_local_binding(self) -> bool:
        return self._runtime_settings.allow_local_binding

    def allow_unix_sockets(self) -> tuple[str, ...]:
        return self._runtime_settings.allow_unix_sockets

    def dangerously_allow_all_unix_sockets(self) -> bool:
        return self._runtime_settings.dangerously_allow_all_unix_sockets

    def apply_to_env(self, env: MutableMapping[str, str]) -> None:
        apply_proxy_env_overrides(
            env,
            self._http_addr,
            self._socks_addr,
            socks_enabled=self.socks_enabled,
            allow_local_binding=self.allow_local_binding(),
        )

    async def replace_config_state(self, new_state: ConfigState) -> None:
        current_cfg = await self.state.current_cfg()
        if new_state.config.network.enabled != current_cfg.network.enabled:
            raise ValueError("cannot update network.enabled on a running proxy")
        if new_state.config.network.proxy_url != current_cfg.network.proxy_url:
            raise ValueError("cannot update network.proxy_url on a running proxy")
        if new_state.config.network.socks_url != current_cfg.network.socks_url:
            raise ValueError("cannot update network.socks_url on a running proxy")
        if new_state.config.network.enable_socks5 != current_cfg.network.enable_socks5:
            raise ValueError("cannot update network.enable_socks5 on a running proxy")
        if new_state.config.network.enable_socks5_udp != current_cfg.network.enable_socks5_udp:
            raise ValueError("cannot update network.enable_socks5_udp on a running proxy")
        await self.state.replace_config_state(new_state)
        self._runtime_settings = NetworkProxyRuntimeSettings.from_config(new_state.config)

    async def run(self) -> "NetworkProxyHandle":
        current_cfg = await self.state.current_cfg()
        if not current_cfg.network.enabled:
            return NetworkProxyHandle.noop()
        reserved = self.reserved_listeners
        http_listener = reserved.take_http() if reserved is not None else None
        socks_listener = reserved.take_socks() if reserved is not None else None
        if http_listener is not None:
            http_coro = run_http_proxy_with_std_listener(self.state, http_listener, self.policy_decider)
        else:
            http_coro = run_http_proxy(self.state, self._http_addr, self.policy_decider)
        http_task = asyncio.create_task(http_coro, name="codex-network-proxy-http")
        socks_task: asyncio.Task[None] | None = None
        if current_cfg.network.enable_socks5:
            if socks_listener is not None:
                socks_coro = run_socks5_with_std_listener(
                    self.state,
                    socks_listener,
                    self.policy_decider,
                    current_cfg.network.enable_socks5_udp,
                )
            else:
                socks_coro = run_socks5(
                    self.state,
                    self._socks_addr,
                    self.policy_decider,
                    current_cfg.network.enable_socks5_udp,
                )
            socks_task = asyncio.create_task(socks_coro, name="codex-network-proxy-socks")
        return NetworkProxyHandle(
            http_task=NetworkProxyTask.pending("http", http_task),
            socks_task=NetworkProxyTask.pending("socks", socks_task) if socks_task is not None else None,
        )


class NetworkProxyBuilder:
    def __init__(self) -> None:
        self._state: NetworkProxyState | None = None
        self._http_addr: tuple[str, int] | None = None
        self._socks_addr: tuple[str, int] | None = None
        self._managed_by_codex = True
        self._policy_decider: object | None = None
        self._blocked_request_observer: object | None = None

    def state(self, state: NetworkProxyState) -> "NetworkProxyBuilder":
        self._state = state
        return self

    def http_addr(self, addr: str | tuple[str, int]) -> "NetworkProxyBuilder":
        self._http_addr = _parse_socket_addr(addr)
        return self

    def socks_addr(self, addr: str | tuple[str, int]) -> "NetworkProxyBuilder":
        self._socks_addr = _parse_socket_addr(addr)
        return self

    def managed_by_codex(self, managed_by_codex: bool) -> "NetworkProxyBuilder":
        self._managed_by_codex = bool(managed_by_codex)
        return self

    def policy_decider(self, decider: object) -> "NetworkProxyBuilder":
        self._policy_decider = decider
        return self

    def blocked_request_observer(self, observer: object) -> "NetworkProxyBuilder":
        self._blocked_request_observer = observer
        return self

    async def build(self) -> NetworkProxy:
        if self._state is None:
            raise ValueError("NetworkProxyBuilder requires a state; supply one via builder.state(...)")
        await self._state.set_blocked_request_observer(self._blocked_request_observer)
        current_cfg = await self._state.current_cfg()
        runtime = resolve_runtime(current_cfg)
        reserved_listeners: ReservedListenerSet | None = None
        if self._managed_by_codex:
            reserved_listeners = reserve_loopback_ephemeral_listeners(current_cfg.network.enable_socks5)
            http_addr = reserved_listeners.http_addr()
            socks_addr = reserved_listeners.socks_addr(_parse_socket_addr(runtime.socks_addr))
        else:
            http_addr = self._http_addr or _parse_socket_addr(runtime.http_addr)
            socks_addr = self._socks_addr or _parse_socket_addr(runtime.socks_addr)
        http_addr, socks_addr = _clamp_bind_addrs_tuple(http_addr, socks_addr, current_cfg.network)
        return NetworkProxy(
            state=self._state,
            http_addr=http_addr,
            socks_addr=socks_addr,
            socks_enabled=current_cfg.network.enable_socks5,
            runtime_settings=NetworkProxyRuntimeSettings.from_config(current_cfg),
            reserved_listeners=reserved_listeners,
            policy_decider=self._policy_decider,
        )


@dataclass
class NetworkProxyTask:
    name: str
    result: BaseException | None = None
    aborted: bool = False
    completed: bool = False
    task: asyncio.Task[None] | None = None

    @classmethod
    def pending(cls, name: str, task: asyncio.Task[None] | None = None) -> "NetworkProxyTask":
        return cls(name=name, task=task)

    @classmethod
    def ok(cls, name: str) -> "NetworkProxyTask":
        return cls(name=name, completed=True)

    async def wait(self) -> None:
        try:
            if self.task is not None:
                await self.task
            if self.result is not None:
                raise self.result
        finally:
            self.completed = True

    async def abort(self) -> None:
        self.aborted = True
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.completed = True


@dataclass
class NetworkProxyHandle:
    http_task: NetworkProxyTask | None
    socks_task: NetworkProxyTask | None = None
    completed: bool = False

    @classmethod
    def noop(cls) -> "NetworkProxyHandle":
        return cls(http_task=NetworkProxyTask.ok("http"), completed=True)

    async def wait(self) -> None:
        if self.http_task is None:
            raise ValueError("missing http proxy task")
        http_task = self.http_task
        socks_task = self.socks_task
        self.http_task = None
        self.socks_task = None
        http_error: BaseException | None = None
        socks_error: BaseException | None = None
        try:
            await http_task.wait()
        except BaseException as exc:
            http_error = exc
        if socks_task is not None:
            try:
                await socks_task.wait()
            except BaseException as exc:
                socks_error = exc
        self.completed = True
        if http_error is not None:
            raise http_error
        if socks_error is not None:
            raise socks_error

    async def shutdown(self) -> None:
        if self.http_task is not None:
            await self.http_task.abort()
        if self.socks_task is not None:
            await self.socks_task.abort()
        self.http_task = None
        self.socks_task = None
        self.completed = True

    def __del__(self) -> None:
        if self.completed:
            return
        for proxy_task in (self.http_task, self.socks_task):
            if proxy_task is None or proxy_task.completed:
                continue
            proxy_task.aborted = True
            task = proxy_task.task
            if task is not None and not task.done():
                task.cancel()
        self.http_task = None
        self.socks_task = None
        self.completed = True


def _set_env_keys(env: MutableMapping[str, str], keys: Sequence[str], value: str) -> None:
    for key in keys:
        env[key] = value


def _proxy_socket_addr(value: str | tuple[str, int]) -> str:
    if isinstance(value, tuple):
        host, port = value
        return _format_host_and_port(host, int(port))
    return str(value)


def _parse_socket_addr(value: str | tuple[str, int]) -> tuple[str, int]:
    if isinstance(value, tuple):
        host, port = value
        return str(host), int(port)
    host, port = _split_formatted_host_port(value)
    return host, port


def _reserve_tcp_listener(addr: tuple[str, int]) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(addr)
        listener.listen()
        return listener
    except Exception:
        listener.close()
        raise

from .config import (
    NetworkProxyConfig,
    _clamp_bind_addrs_tuple,
    _format_host_and_port,
    _split_formatted_host_port,
    resolve_runtime,
)
from .http_proxy import (
    run_http_proxy,
    run_http_proxy_with_std_listener,
)
from .runtime import (
    ConfigState,
    NetworkProxyState,
)
from .socks5 import (
    run_socks5,
    run_socks5_with_std_listener,
)

__all__ = [
    "ALLOW_LOCAL_BINDING_ENV_KEY",
    "ALL_PROXY_ENV_KEYS",
    "CODEX_PROXY_GIT_SSH_COMMAND_MARKER",
    "DEFAULT_NO_PROXY_VALUE",
    "ELECTRON_GET_USE_PROXY_ENV_KEY",
    "FTP_PROXY_ENV_KEYS",
    "NODE_USE_ENV_PROXY_ENV_KEY",
    "NO_PROXY_ENV_KEYS",
    "NetworkProxy",
    "NetworkProxyBuilder",
    "NetworkProxyHandle",
    "NetworkProxyRuntimeSettings",
    "NetworkProxyTask",
    "PROXY_ACTIVE_ENV_KEY",
    "PROXY_ENV_KEYS",
    "PROXY_GIT_SSH_COMMAND_ENV_KEY",
    "PROXY_URL_ENV_KEYS",
    "ReservedListenerSet",
    "WEBSOCKET_PROXY_ENV_KEYS",
    "apply_proxy_env_overrides",
    "codex_proxy_git_ssh_command",
    "has_proxy_url_env_vars",
    "is_codex_proxy_git_ssh_command",
    "proxy_url_env_value",
    "reserve_loopback_ephemeral_listeners",
    "reserve_windows_managed_listeners",
    "windows_managed_loopback_addr",
]
