"""Rust-aligned projection of ``codex-network-proxy::state``."""

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

@dataclass
class NetworkProxyConstraints:
    enabled: bool | None = None
    mode: NetworkMode | str | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    allowed_domains: list[str] | None = None
    denied_domains: list[str] | None = None
    allowlist_expansion_enabled: bool | None = None
    denylist_expansion_enabled: bool | None = None
    allow_unix_sockets: list[str] | None = None
    allow_local_binding: bool | None = None


class NetworkProxyConstraintError(ValueError):
    def __init__(self, field_name: str, candidate: str, allowed: str) -> None:
        self.field_name = field_name
        self.candidate = candidate
        self.allowed = allowed
        super().__init__(f"invalid value for {field_name}: {candidate} (allowed {allowed})")

    def to_mapping(self) -> dict[str, str]:
        return {
            "type": "InvalidValue",
            "field_name": self.field_name,
            "candidate": self.candidate,
            "allowed": self.allowed,
        }


def build_config_state(
    config: NetworkProxyConfig,
    constraints: NetworkProxyConstraints | None = None,
) -> ConfigState:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    if constraints is None:
        constraints = NetworkProxyConstraints()
    elif not isinstance(constraints, NetworkProxyConstraints):
        raise TypeError("constraints must be NetworkProxyConstraints")
    _validate_unix_socket_allowlist_paths(config)
    _validate_non_global_wildcard_domain_patterns("network.denied_domains", config.network.denied_domains() or [])
    validate_policy_against_constraints(config, constraints)
    return ConfigState(_clone_network_proxy_config(config), _clone_network_proxy_constraints(constraints))


def validate_policy_against_constraints(
    config: NetworkProxyConfig,
    constraints: NetworkProxyConstraints,
) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    if not isinstance(constraints, NetworkProxyConstraints):
        raise TypeError("constraints must be NetworkProxyConstraints")
    _validate_mitm_hook_config(config)
    config_allowed_domains = config.network.allowed_domains() or []
    config_denied_domains = config.network.denied_domains() or []
    denied_domain_overrides = {entry.lower() for entry in config_denied_domains}
    config_allow_unix_sockets = config.network.allow_unix_sockets_effective()
    _validate_non_global_wildcard_domain_patterns("network.denied_domains", config_denied_domains)

    if constraints.enabled is not None and config.network.enabled and not constraints.enabled:
        raise NetworkProxyConstraintError("network.enabled", "true", "false (disabled by managed config)")

    if constraints.mode is not None:
        max_mode = NetworkMode(constraints.mode)
        if _network_mode_rank(config.network.mode) > _network_mode_rank(max_mode):
            raise NetworkProxyConstraintError(
                "network.mode",
                _rust_debug_network_mode(config.network.mode),
                f"{_rust_debug_network_mode(max_mode)} or more restrictive",
            )

    if constraints.allow_upstream_proxy is False and config.network.allow_upstream_proxy:
        raise NetworkProxyConstraintError(
            "network.allow_upstream_proxy",
            "true",
            "false (disabled by managed config)",
        )

    if constraints.dangerously_allow_non_loopback_proxy is False and config.network.dangerously_allow_non_loopback_proxy:
        raise NetworkProxyConstraintError(
            "network.dangerously_allow_non_loopback_proxy",
            "true",
            "false (disabled by managed config)",
        )

    allow_all_unix_sockets = (
        constraints.dangerously_allow_all_unix_sockets
        if constraints.dangerously_allow_all_unix_sockets is not None
        else constraints.allow_unix_sockets is None
    )
    if config.network.dangerously_allow_all_unix_sockets and not allow_all_unix_sockets:
        raise NetworkProxyConstraintError(
            "network.dangerously_allow_all_unix_sockets",
            "true",
            "false (disabled by managed config)",
        )

    if constraints.allow_local_binding is not None and config.network.allow_local_binding and not constraints.allow_local_binding:
        raise NetworkProxyConstraintError(
            "network.allow_local_binding",
            "true",
            "false (disabled by managed config)",
        )

    if constraints.allowed_domains is not None:
        allowed_domains = list(_string_tuple(constraints.allowed_domains, "constraints.allowed_domains"))
        _validate_non_global_wildcard_domain_patterns("network.allowed_domains", allowed_domains)
        required_set = {entry.lower() for entry in allowed_domains}
        candidate_set = {entry.lower() for entry in config_allowed_domains}
        if constraints.allowlist_expansion_enabled is True:
            missing = sorted(entry for entry in required_set if entry not in candidate_set and entry not in denied_domain_overrides)
            if missing:
                raise NetworkProxyConstraintError(
                    "network.allowed_domains",
                    "missing managed allowed_domains entries",
                    _rust_debug_list(missing),
                )
        elif constraints.allowlist_expansion_enabled is False:
            expected_set = required_set.difference(denied_domain_overrides)
            if candidate_set != expected_set:
                raise NetworkProxyConstraintError(
                    "network.allowed_domains",
                    _rust_debug_list(config_allowed_domains),
                    "must match managed allowed_domains",
                )
        else:
            managed_patterns = [_DomainPattern.parse_for_constraints(entry) for entry in allowed_domains]
            invalid = [
                entry
                for entry in config_allowed_domains
                if not any(managed.allows(_DomainPattern.parse_for_constraints(entry)) for managed in managed_patterns)
            ]
            if invalid:
                raise NetworkProxyConstraintError(
                    "network.allowed_domains",
                    _rust_debug_list(invalid),
                    "subset of managed allowed_domains",
                )

    if constraints.denied_domains is not None:
        denied_domains = list(_string_tuple(constraints.denied_domains, "constraints.denied_domains"))
        _validate_non_global_wildcard_domain_patterns("network.denied_domains", denied_domains)
        required_set = {entry.lower() for entry in denied_domains}
        candidate_set = {entry.lower() for entry in config_denied_domains}
        if constraints.denylist_expansion_enabled is False:
            if candidate_set != required_set:
                raise NetworkProxyConstraintError(
                    "network.denied_domains",
                    _rust_debug_list(config_denied_domains),
                    "must match managed denied_domains",
                )
        else:
            missing = sorted(entry for entry in required_set if entry not in candidate_set)
            if missing:
                raise NetworkProxyConstraintError(
                    "network.denied_domains",
                    "missing managed denied_domains entries",
                    _rust_debug_list(missing),
                )

    if constraints.allow_unix_sockets is not None:
        allowed_set = {entry.lower() for entry in _string_tuple(constraints.allow_unix_sockets, "constraints.allow_unix_sockets")}
        invalid = [entry for entry in config_allow_unix_sockets if entry.lower() not in allowed_set]
        if invalid:
            raise NetworkProxyConstraintError(
                "network.allow_unix_sockets",
                _rust_debug_list(invalid),
                "subset of managed allow_unix_sockets",
            )


def _clone_network_proxy_config(config: NetworkProxyConfig) -> NetworkProxyConfig:
    clone = NetworkProxyConfig()
    clone.network.enabled = config.network.enabled
    clone.network.proxy_url = config.network.proxy_url
    clone.network.enable_socks5 = config.network.enable_socks5
    clone.network.socks_url = config.network.socks_url
    clone.network.enable_socks5_udp = config.network.enable_socks5_udp
    clone.network.allow_upstream_proxy = config.network.allow_upstream_proxy
    clone.network.dangerously_allow_non_loopback_proxy = config.network.dangerously_allow_non_loopback_proxy
    clone.network.dangerously_allow_all_unix_sockets = config.network.dangerously_allow_all_unix_sockets
    clone.network.mode = config.network.mode
    clone.network.mitm = config.network.mitm
    clone.network.mitm_hooks = list(config.network.mitm_hooks)
    clone.network.allow_unix_sockets = list(config.network.allow_unix_sockets)
    clone.network.allow_local_binding = config.network.allow_local_binding
    clone.network.set_allowed_domains(config.network.allowed_domains())
    clone.network.set_denied_domains(config.network.denied_domains())
    return clone


def _clone_network_proxy_constraints(constraints: NetworkProxyConstraints) -> NetworkProxyConstraints:
    return NetworkProxyConstraints(
        enabled=constraints.enabled,
        mode=constraints.mode,
        allow_upstream_proxy=constraints.allow_upstream_proxy,
        dangerously_allow_non_loopback_proxy=constraints.dangerously_allow_non_loopback_proxy,
        dangerously_allow_all_unix_sockets=constraints.dangerously_allow_all_unix_sockets,
        allowed_domains=None if constraints.allowed_domains is None else list(constraints.allowed_domains),
        denied_domains=None if constraints.denied_domains is None else list(constraints.denied_domains),
        allowlist_expansion_enabled=constraints.allowlist_expansion_enabled,
        denylist_expansion_enabled=constraints.denylist_expansion_enabled,
        allow_unix_sockets=None if constraints.allow_unix_sockets is None else list(constraints.allow_unix_sockets),
        allow_local_binding=constraints.allow_local_binding,
    )


def _validate_non_global_wildcard_domain_patterns(field_name: str, patterns: Sequence[str]) -> None:
    for pattern in patterns:
        if _is_global_wildcard_domain_pattern(pattern):
            raise NetworkProxyConstraintError(
                field_name,
                pattern.strip(),
                "exact hosts or scoped wildcards like *.example.com or **.example.com",
            )


def _network_mode_rank(mode: NetworkMode | str) -> int:
    mode = NetworkMode(mode)
    return 0 if mode is NetworkMode.LIMITED else 1


def _rust_debug_network_mode(mode: NetworkMode | str) -> str:
    mode = NetworkMode(mode)
    return "Limited" if mode is NetworkMode.LIMITED else "Full"


def _rust_debug_list(values: Sequence[str]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"

from .config import (
    NetworkMode,
    NetworkProxyConfig,
    _string_tuple,
    _validate_unix_socket_allowlist_paths,
)
from .mitm_hook import _validate_mitm_hook_config
from .policy import (
    _DomainPattern,
    _is_global_wildcard_domain_pattern,
)
from .runtime import ConfigState

__all__ = [
    "NetworkProxyConstraintError",
    "NetworkProxyConstraints",
    "build_config_state",
    "validate_policy_against_constraints",
]
