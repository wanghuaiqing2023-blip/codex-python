"""Rust-aligned projection of ``codex-network-proxy::upstream``."""

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

@dataclass(frozen=True)
class ProxyAddress:
    address: str
    protocol: str | None = None
    host: str | None = None
    port: int | None = None

    @classmethod
    def try_from(cls, value: str) -> "ProxyAddress":
        if not isinstance(value, str):
            raise TypeError("proxy address must be a string")
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("proxy address is empty")
        parsed = urlparse(trimmed if "://" in trimmed else f"//{trimmed}")
        protocol = parsed.scheme.lower() or None
        if protocol is not None and protocol not in {"http", "https"}:
            raise ValueError("non-http proxy protocol")
        host = parsed.hostname
        if not host:
            raise ValueError("missing proxy host")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("invalid proxy port") from exc
        return cls(address=trimmed, protocol=protocol, host=host, port=port)

    def is_http(self) -> bool:
        return self.protocol in {None, "http", "https"}


@dataclass(frozen=True)
class ProxyConfig:
    http: ProxyAddress | None = None
    https: ProxyAddress | None = None
    all: ProxyAddress | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "ProxyConfig":
        source = os.environ if env is None else env
        return cls(
            http=read_proxy_env(("HTTP_PROXY", "http_proxy"), source),
            https=read_proxy_env(("HTTPS_PROXY", "https_proxy"), source),
            all=read_proxy_env(("ALL_PROXY", "all_proxy"), source),
        )

    def proxy_for_protocol(self, is_secure: bool) -> ProxyAddress | None:
        if is_secure:
            return self.https or self.http or self.all
        return self.http or self.all


def read_proxy_env(keys: Sequence[str], env: Mapping[str, str] | None = None) -> ProxyAddress | None:
    source = os.environ if env is None else env
    for key in keys:
        if key not in source:
            continue
        value = source[key].strip()
        if not value:
            continue
        try:
            proxy = ProxyAddress.try_from(value)
        except (TypeError, ValueError):
            continue
        if proxy.is_http():
            return proxy
    return None


def proxy_for_connect(env: Mapping[str, str] | None = None) -> ProxyAddress | None:
    return ProxyConfig.from_env(env).proxy_for_protocol(True)


@dataclass(frozen=True)
class UpstreamRoute:
    authority: str
    route: str
    proxy: ProxyAddress | None = None


@dataclass(frozen=True)
class UpstreamClient:
    proxy_config: ProxyConfig
    transport: TargetCheckedTcpConnector | None = None
    unix_socket_path: str | None = None

    @classmethod
    def direct(cls, state: NetworkProxyState) -> "UpstreamClient":
        return cls(ProxyConfig(), TargetCheckedTcpConnector.new(state))

    @classmethod
    def from_env_proxy(
        cls,
        state: NetworkProxyState,
        env: Mapping[str, str] | None = None,
    ) -> "UpstreamClient":
        return cls(ProxyConfig.from_env(env), TargetCheckedTcpConnector.new(state))

    @classmethod
    def direct_with_allow_local_binding(cls, allow_local_binding: bool) -> "UpstreamClient":
        return cls(
            ProxyConfig(),
            TargetCheckedTcpConnector.from_allow_local_binding(allow_local_binding),
        )

    @classmethod
    def from_env_proxy_with_allow_local_binding(
        cls,
        allow_local_binding: bool,
        env: Mapping[str, str] | None = None,
    ) -> "UpstreamClient":
        return cls(
            ProxyConfig.from_env(env),
            TargetCheckedTcpConnector.from_allow_local_binding(allow_local_binding),
        )

    @classmethod
    def unix_socket(cls, path: str) -> "UpstreamClient":
        return cls(ProxyConfig(), None, path)

    def select_route(self, url: str) -> UpstreamRoute:
        parsed = urlparse(url)
        authority = parsed.netloc or "<unknown>"
        is_secure = parsed.scheme.lower() == "https"
        proxy = self.proxy_config.proxy_for_protocol(is_secure)
        return UpstreamRoute(
            authority=authority,
            route="upstream_proxy" if proxy is not None else "direct",
            proxy=proxy,
        )

from .connect_policy import TargetCheckedTcpConnector
from .runtime import NetworkProxyState

__all__ = [
    "ProxyAddress",
    "ProxyConfig",
    "UpstreamClient",
    "UpstreamRoute",
    "proxy_for_connect",
    "read_proxy_env",
]
