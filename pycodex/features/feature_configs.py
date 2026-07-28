"""Typed feature configuration owned by ``codex-features::feature_configs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum


@dataclass
class MultiAgentV2ConfigToml:
    enabled: bool | None = None
    max_concurrent_threads_per_session: int | None = None
    min_wait_timeout_ms: int | None = None
    max_wait_timeout_ms: int | None = None
    default_wait_timeout_ms: int | None = None
    usage_hint_enabled: bool | None = None
    usage_hint_text: str | None = None
    root_agent_usage_hint_text: str | None = None
    subagent_usage_hint_text: str | None = None
    tool_namespace: str | None = None
    hide_spawn_agent_metadata: bool | None = None
    non_code_mode_only: bool | None = None

    def feature_enabled(self) -> bool | None:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


@dataclass
class AppsMcpPathOverrideConfigToml:
    enabled: bool | None = None
    path: str | None = None

    def feature_enabled(self) -> bool | None:
        if self.enabled is not None:
            return self.enabled
        return True if self.path is not None else None

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


class NetworkProxyModeToml(str, Enum):
    LIMITED = "limited"
    FULL = "full"


class NetworkProxyDomainPermissionToml(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class NetworkProxyUnixSocketPermissionToml(str, Enum):
    ALLOW = "allow"
    NONE = "none"


@dataclass
class NetworkProxyConfigToml:
    enabled: bool | None = None
    proxy_url: str | None = None
    enable_socks5: bool | None = None
    socks_url: str | None = None
    enable_socks5_udp: bool | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    mode: NetworkProxyModeToml | None = None
    domains: Mapping[str, NetworkProxyDomainPermissionToml] | None = None
    unix_sockets: Mapping[str, NetworkProxyUnixSocketPermissionToml] | None = None
    allow_local_binding: bool | None = None

    def feature_enabled(self) -> bool | None:
        return self.enabled

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


__all__ = [
    "AppsMcpPathOverrideConfigToml",
    "MultiAgentV2ConfigToml",
    "NetworkProxyConfigToml",
    "NetworkProxyDomainPermissionToml",
    "NetworkProxyModeToml",
    "NetworkProxyUnixSocketPermissionToml",
]
