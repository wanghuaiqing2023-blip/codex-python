"""Rust-aligned projection of ``codex-network-proxy::config``."""

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

class NetworkDomainPermission(str, Enum):
    NONE = "none"
    ALLOW = "allow"
    DENY = "deny"


class NetworkMode(str, Enum):
    FULL = "full"
    LIMITED = "limited"

    def allows_method(self, method: str) -> bool:
        if self is NetworkMode.FULL:
            return True
        return method in {"GET", "HEAD", "OPTIONS"}


@dataclass
class NetworkProxyNetworkConfig:
    enabled: bool = False
    proxy_url: str = "http://127.0.0.1:3128"
    enable_socks5: bool = True
    socks_url: str = "http://127.0.0.1:8081"
    enable_socks5_udp: bool = True
    allow_upstream_proxy: bool = True
    dangerously_allow_non_loopback_proxy: bool = False
    dangerously_allow_all_unix_sockets: bool = False
    mode: NetworkMode = NetworkMode.FULL
    mitm: bool = False
    mitm_hooks: list[JsonValue] = field(default_factory=list)
    allow_unix_sockets: list[str] = field(default_factory=list)
    allow_local_binding: bool = False
    _allowed_domains: list[str] = field(default_factory=list)
    _denied_domains: list[str] = field(default_factory=list)

    def set_allowed_domains(self, domains: Sequence[str] | None) -> None:
        self._allowed_domains = _normalized_domain_list(domains)

    def set_denied_domains(self, domains: Sequence[str] | None) -> None:
        self._denied_domains = _normalized_domain_list(domains)

    def allowed_domains(self) -> list[str] | None:
        denied = set(self._denied_domains)
        allowed = [entry for entry in self._allowed_domains if entry not in denied]
        return allowed or None

    def denied_domains(self) -> list[str] | None:
        return list(self._denied_domains) if self._denied_domains else None

    def set_allow_unix_sockets(self, sockets: Sequence[str] | None) -> None:
        self.allow_unix_sockets = sorted(set(_string_tuple(sockets or (), "allow unix sockets")))

    def upsert_domain_permission(self, host: str, permission: NetworkDomainPermission) -> None:
        normalized = normalize_host(host)
        permission = NetworkDomainPermission(permission)
        self._allowed_domains = [item for item in self._allowed_domains if item != normalized]
        self._denied_domains = [item for item in self._denied_domains if item != normalized]
        if permission is NetworkDomainPermission.ALLOW:
            self._allowed_domains.append(normalized)
        elif permission is NetworkDomainPermission.DENY:
            self._denied_domains.append(normalized)

    def allow_unix_sockets_effective(self) -> list[str]:
        return sorted(set(self.allow_unix_sockets))

    def to_mapping(self) -> dict[str, JsonValue]:
        domains: dict[str, str] | None = None
        effective = _effective_domain_entries(self._allowed_domains, self._denied_domains)
        if effective:
            domains = {pattern: permission.value for pattern, permission in effective}
        unix_sockets = {path: "allow" for path in self.allow_unix_sockets_effective()} or None
        return {
            "enabled": self.enabled,
            "proxy_url": self.proxy_url,
            "enable_socks5": self.enable_socks5,
            "socks_url": self.socks_url,
            "enable_socks5_udp": self.enable_socks5_udp,
            "allow_upstream_proxy": self.allow_upstream_proxy,
            "dangerously_allow_non_loopback_proxy": self.dangerously_allow_non_loopback_proxy,
            "dangerously_allow_all_unix_sockets": self.dangerously_allow_all_unix_sockets,
            "mode": self.mode.value,
            "domains": domains,
            "unix_sockets": unix_sockets,
            "allow_local_binding": self.allow_local_binding,
            "mitm": self.mitm,
            "mitm_hooks": list(self.mitm_hooks),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "NetworkProxyNetworkConfig":
        settings = cls()
        if value is None:
            return settings
        if not isinstance(value, Mapping):
            raise TypeError("network must be a mapping")
        if "enabled" in value and value["enabled"] is not None:
            settings.enabled = _optional_bool(value["enabled"], "network.enabled") or False
        if "proxy_url" in value and value["proxy_url"] is not None:
            settings.proxy_url = _string_field(value["proxy_url"], "network.proxy_url")
        if "enable_socks5" in value and value["enable_socks5"] is not None:
            settings.enable_socks5 = _optional_bool(value["enable_socks5"], "network.enable_socks5") or False
        if "socks_url" in value and value["socks_url"] is not None:
            settings.socks_url = _string_field(value["socks_url"], "network.socks_url")
        if "enable_socks5_udp" in value and value["enable_socks5_udp"] is not None:
            settings.enable_socks5_udp = _optional_bool(value["enable_socks5_udp"], "network.enable_socks5_udp") or False
        if "allow_upstream_proxy" in value and value["allow_upstream_proxy"] is not None:
            settings.allow_upstream_proxy = _optional_bool(
                value["allow_upstream_proxy"],
                "network.allow_upstream_proxy",
            ) or False
        if "dangerously_allow_non_loopback_proxy" in value and value["dangerously_allow_non_loopback_proxy"] is not None:
            settings.dangerously_allow_non_loopback_proxy = _optional_bool(
                value["dangerously_allow_non_loopback_proxy"],
                "network.dangerously_allow_non_loopback_proxy",
            ) or False
        if "dangerously_allow_all_unix_sockets" in value and value["dangerously_allow_all_unix_sockets"] is not None:
            settings.dangerously_allow_all_unix_sockets = _optional_bool(
                value["dangerously_allow_all_unix_sockets"],
                "network.dangerously_allow_all_unix_sockets",
            ) or False
        if "mode" in value and value["mode"] is not None:
            settings.mode = NetworkMode(_string_field(value["mode"], "network.mode"))
        if "domains" in value and value["domains"] is not None:
            domains = value["domains"]
            if not isinstance(domains, Mapping):
                raise TypeError("network.domains must be a mapping")
            for host, permission in domains.items():
                if not isinstance(host, str):
                    raise TypeError("network.domains keys must be strings")
                settings.upsert_domain_permission(host, NetworkDomainPermission(permission))
        if "unix_sockets" in value and value["unix_sockets"] is not None:
            unix_sockets = value["unix_sockets"]
            if not isinstance(unix_sockets, Mapping):
                raise TypeError("network.unix_sockets must be a mapping")
            settings.allow_unix_sockets = sorted(
                path
                for path, permission in unix_sockets.items()
                if NetworkDomainPermission.NONE.value != str(permission)
                if _unix_socket_permission(permission) == "allow"
            )
        if "allow_local_binding" in value and value["allow_local_binding"] is not None:
            settings.allow_local_binding = _optional_bool(value["allow_local_binding"], "network.allow_local_binding") or False
        if "mitm" in value and value["mitm"] is not None:
            settings.mitm = _optional_bool(value["mitm"], "network.mitm") or False
        if "mitm_hooks" in value and value["mitm_hooks"] is not None:
            hooks = value["mitm_hooks"]
            if isinstance(hooks, str) or not isinstance(hooks, Sequence):
                raise TypeError("network.mitm_hooks must be a sequence")
            settings.mitm_hooks = list(hooks)
        return settings


@dataclass
class NetworkProxyConfig:
    network: NetworkProxyNetworkConfig = field(default_factory=NetworkProxyNetworkConfig)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"network": self.network.to_mapping()}

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "NetworkProxyConfig":
        if not isinstance(value, Mapping):
            raise TypeError("config must be a mapping")
        return cls(network=NetworkProxyNetworkConfig.from_mapping(value.get("network")))


@dataclass(frozen=True)
class RuntimeConfig:
    http_addr: str
    socks_addr: str


def host_and_port_from_network_addr(value: str, default_port: int) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    trimmed = value.strip()
    if not trimmed:
        return "<missing>"
    try:
        host, port = _parse_host_port(trimmed, default_port)
    except ValueError:
        host, port = trimmed, default_port
    return _format_host_and_port(host, port)


def resolve_runtime(config: NetworkProxyConfig) -> RuntimeConfig:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    _validate_unix_socket_allowlist_paths(config)
    http_addr = _resolve_addr(config.network.proxy_url, 3128)
    socks_addr = _resolve_addr(config.network.socks_url, 8081)
    http_addr, socks_addr = _clamp_bind_addrs(http_addr, socks_addr, config.network)
    return RuntimeConfig(http_addr=http_addr, socks_addr=socks_addr)


def _effective_domain_entries(
    allowed_domains: Sequence[str],
    denied_domains: Sequence[str],
) -> list[tuple[str, NetworkDomainPermission]]:
    order: list[str] = []
    effective: dict[str, NetworkDomainPermission] = {}
    for pattern, permission in (
        *((pattern, NetworkDomainPermission.ALLOW) for pattern in allowed_domains),
        *((pattern, NetworkDomainPermission.DENY) for pattern in denied_domains),
    ):
        if pattern not in effective:
            order.append(pattern)
            effective[pattern] = permission
            continue
        if _domain_permission_rank(permission) > _domain_permission_rank(effective[pattern]):
            effective[pattern] = permission
    return [(pattern, effective[pattern]) for pattern in order]


def _domain_permission_rank(permission: NetworkDomainPermission) -> int:
    permission = NetworkDomainPermission(permission)
    if permission is NetworkDomainPermission.NONE:
        return 0
    if permission is NetworkDomainPermission.ALLOW:
        return 1
    return 2


def _unix_socket_permission(permission: object) -> str:
    if not isinstance(permission, str):
        raise TypeError("network.unix_sockets permissions must be strings")
    if permission not in {"allow", "none"}:
        raise ValueError(f"invalid unix socket permission {permission!r}")
    return permission


def _host_and_port_from_url(url: str, default_port: int) -> str:
    return host_and_port_from_network_addr(url, default_port)


def _format_host_and_port(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _parse_host_port(url: str, default_port: int) -> tuple[str, int]:
    from urllib.parse import urlparse

    trimmed = url.strip()
    if not trimmed:
        raise ValueError(f"missing host in network proxy address: {url}")

    try:
        ip = ipaddress.ip_address(trimmed)
    except ValueError:
        ip = None
    if ip is not None and ip.version == 6 and not trimmed.startswith("["):
        return trimmed, default_port

    candidate = trimmed if "://" in trimmed else f"http://{trimmed}"
    try:
        parsed = urlparse(candidate)
        host = parsed.hostname
        if host:
            try:
                port = parsed.port if parsed.port is not None else default_port
            except ValueError:
                port = default_port
            return host.strip("[]"), port
    except ValueError:
        pass

    return _parse_host_port_fallback(trimmed, default_port)


def _parse_host_port_fallback(value: str, default_port: int) -> tuple[str, int]:
    without_scheme = value.split("://", 1)[1] if "://" in value else value
    host_port = without_scheme.split("/", 1)[0]
    host_port = host_port.rsplit("@", 1)[1] if "@" in host_port else host_port

    if host_port.startswith("[") and "]" in host_port:
        end = host_port.index("]")
        host = host_port[1:end]
        if not host:
            raise ValueError(f"missing host in network proxy address: {value}")
        rest = host_port[end + 1 :]
        port = default_port
        if rest.startswith(":"):
            try:
                port = int(rest[1:])
            except ValueError:
                port = default_port
        return host, port

    if host_port.count(":") == 1:
        host, raw_port = host_port.rsplit(":", 1)
        if not host:
            raise ValueError(f"missing host in network proxy address: {value}")
        try:
            port = int(raw_port)
        except ValueError:
            port = default_port
        return host, port

    if not host_port:
        raise ValueError(f"missing host in network proxy address: {value}")
    return host_port, default_port


def _resolve_addr(value: str, default_port: int) -> str:
    host, port = _parse_host_port(value, default_port)
    if host.lower() == "localhost":
        host = "127.0.0.1"
    else:
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            host = "127.0.0.1"
    return _format_host_and_port(host, port)


def _clamp_bind_addrs(http_addr: str, socks_addr: str, settings: NetworkProxyNetworkConfig) -> tuple[str, str]:
    http_addr = _clamp_non_loopback(http_addr, settings.dangerously_allow_non_loopback_proxy)
    socks_addr = _clamp_non_loopback(socks_addr, settings.dangerously_allow_non_loopback_proxy)
    if not settings.allow_unix_sockets_effective() and not settings.dangerously_allow_all_unix_sockets:
        return http_addr, socks_addr
    return _force_loopback(http_addr), _force_loopback(socks_addr)


def _clamp_bind_addrs_tuple(
    http_addr: tuple[str, int],
    socks_addr: tuple[str, int],
    settings: NetworkProxyNetworkConfig,
) -> tuple[tuple[str, int], tuple[str, int]]:
    http, socks = _clamp_bind_addrs(
        _format_host_and_port(http_addr[0], http_addr[1]),
        _format_host_and_port(socks_addr[0], socks_addr[1]),
        settings,
    )
    return _parse_socket_addr(http), _parse_socket_addr(socks)


def _clamp_non_loopback(addr: str, allow_non_loopback: bool) -> str:
    host, port = _split_formatted_host_port(addr)
    if _is_loopback_host(host) or allow_non_loopback:
        return addr
    return f"127.0.0.1:{port}"


def _force_loopback(addr: str) -> str:
    _host, port = _split_formatted_host_port(addr)
    return f"127.0.0.1:{port}"


def _split_formatted_host_port(addr: str) -> tuple[str, int]:
    if addr.startswith("[") and "]:" in addr:
        host, raw_port = addr[1:].split("]:", 1)
        return host, int(raw_port)
    host, raw_port = addr.rsplit(":", 1)
    return host, int(raw_port)


def _validate_unix_socket_allowlist_paths(config: NetworkProxyConfig) -> None:
    for index, socket_path in enumerate(config.network.allow_unix_sockets_effective()):
        if not isinstance(socket_path, str):
            raise TypeError("network.allow_unix_sockets entries must be strings")
        path = Path(socket_path)
        if not path.is_absolute() and not socket_path.startswith("/"):
            raise ValueError(f"invalid network.allow_unix_sockets[{index}]: expected an absolute path, got {socket_path!r}")


def _canonical_path_or_none(path: Path) -> Path | None:
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def _string_field(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _optional_bool(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a bool")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must be a sequence of strings")
    return tuple(value)


def _normalized_domain_list(domains: Sequence[str] | None) -> list[str]:
    if domains is None:
        return []
    return [normalize_host(domain) for domain in _string_tuple(domains, "domains")]

from .policy import (
    _is_loopback_host,
    normalize_host,
)
from .proxy import _parse_socket_addr

__all__ = [
    "NetworkDomainPermission",
    "NetworkMode",
    "NetworkProxyConfig",
    "NetworkProxyNetworkConfig",
    "RuntimeConfig",
    "host_and_port_from_network_addr",
    "resolve_runtime",
]
