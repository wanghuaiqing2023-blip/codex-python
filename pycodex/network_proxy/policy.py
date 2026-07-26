"""Rust-aligned projection of ``codex-network-proxy::policy``."""

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
class Host:
    value: str

    @classmethod
    def parse(cls, value: str) -> "Host":
        normalized = normalize_host(value)
        if not normalized:
            raise ValueError("host is empty")
        return cls(normalized)

    def as_str(self) -> str:
        return self.value


def normalize_host(host: str) -> str:
    if not isinstance(host, str):
        raise TypeError("host must be a string")
    host = host.strip()
    if host.startswith("[") and "]" in host:
        return _normalize_dns_host_or_ip_literal(host[1 : host.index("]")])
    if host.count(":") == 1:
        return _normalize_dns_host_or_ip_literal(host.split(":", 1)[0])
    return _normalize_dns_host_or_ip_literal(host)


def is_loopback_host(host: Host | str) -> bool:
    value = host.as_str() if isinstance(host, Host) else Host.parse(host).as_str()
    value = _unscoped_ip_literal(value) or value
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def is_non_public_ip(ip: str | ipaddress._BaseAddress) -> bool:
    address = ipaddress.ip_address(ip)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return is_non_public_ip(address.ipv4_mapped)
    if isinstance(address, ipaddress.IPv4Address):
        return (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_unspecified
            or address.is_multicast
            or address == ipaddress.IPv4Address("255.255.255.255")
            or _ipv4_in_network(address, "0.0.0.0/8")
            or _ipv4_in_network(address, "100.64.0.0/10")
            or _ipv4_in_network(address, "192.0.0.0/24")
            or _ipv4_in_network(address, "192.0.2.0/24")
            or _ipv4_in_network(address, "198.18.0.0/15")
            or _ipv4_in_network(address, "198.51.100.0/24")
            or _ipv4_in_network(address, "203.0.113.0/24")
            or _ipv4_in_network(address, "240.0.0.0/4")
        )
    return (
        address.is_loopback
        or address.is_unspecified
        or address.is_multicast
        or address.is_private
        or address.is_link_local
    )


def is_global_wildcard_domain_pattern(pattern: str) -> bool:
    return _is_global_wildcard_domain_pattern(pattern)


def compile_allowlist_globset(patterns: Sequence[str]) -> "DomainGlobSet":
    return _compile_globset_with_policy(patterns, allow_global_wildcard=True)


def compile_denylist_globset(patterns: Sequence[str]) -> "DomainGlobSet":
    return _compile_globset_with_policy(patterns, allow_global_wildcard=False)


def _is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _is_global_wildcard_domain_pattern(pattern: str) -> bool:
    return "*" in _expand_domain_pattern(_normalize_pattern(pattern))


def _normalize_dns_host_or_ip_literal(host: str) -> str:
    host = host.lower().rstrip(".")
    normalized = _normalize_ip_literal(host)
    return normalized if normalized is not None else host


def _normalize_ip_literal(host: str) -> str | None:
    if "%25" in host:
        ip, scope = host.split("%25", 1)
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            pass
        else:
            return f"{ip}%{scope}"
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    for delimiter in ("%25", "%"):
        if delimiter in host:
            ip, scope = host.split(delimiter, 1)
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                continue
            return f"{ip}%{scope}"
    return None


def _unscoped_ip_literal(host: str) -> str | None:
    if "%" not in host:
        return None
    ip, _scope = host.split("%", 1)
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


def _ipv4_in_network(ip: ipaddress.IPv4Address, network: str) -> bool:
    return ip in ipaddress.ip_network(network)


def _normalize_pattern(pattern: str) -> str:
    pattern = pattern.strip()
    if pattern == "*":
        return "*"
    if pattern.startswith("**."):
        return "**." + normalize_host(pattern[3:])
    if pattern.startswith("*."):
        return "*." + normalize_host(pattern[2:])
    return normalize_host(pattern)


def _expand_domain_pattern(pattern: str) -> list[str]:
    parsed = _DomainPattern.parse(pattern)
    if parsed.kind == "exact":
        return [parsed.suffix]
    if parsed.kind == "subdomain_wildcard":
        return [f"?*.{parsed.suffix}"]
    return [parsed.suffix, f"?*.{parsed.suffix}"]


@dataclass(frozen=True)
class DomainGlobSet:
    patterns: tuple[str, ...]

    def is_match(self, host: str) -> bool:
        normalized = normalize_host(host)
        return any(fnmatch.fnmatchcase(normalized.lower(), pattern.lower()) for pattern in self.patterns)


def _compile_globset_with_policy(patterns: Sequence[str], *, allow_global_wildcard: bool) -> DomainGlobSet:
    if isinstance(patterns, str) or not isinstance(patterns, Sequence):
        raise TypeError("patterns must be a sequence of strings")
    expanded: list[str] = []
    seen: set[str] = set()
    for raw_pattern in patterns:
        if not isinstance(raw_pattern, str):
            raise TypeError("patterns must be a sequence of strings")
        if not allow_global_wildcard and _is_global_wildcard_domain_pattern(raw_pattern):
            raise ValueError(
                'unsupported global wildcard domain pattern "*"; use exact hosts or scoped wildcards like *.example.com or **.example.com'
            )
        for candidate in _expand_domain_pattern(_normalize_pattern(raw_pattern)):
            if candidate not in seen:
                _validate_glob_pattern(candidate)
                seen.add(candidate)
                expanded.append(candidate)
    return DomainGlobSet(tuple(expanded))


@dataclass(frozen=True)
class _DomainPattern:
    kind: str
    suffix: str

    @classmethod
    def parse(cls, value: str) -> "_DomainPattern":
        pattern = value.strip()
        if not pattern:
            return cls("exact", "")
        if pattern.startswith("**."):
            suffix = pattern[3:].strip()
            return cls("double_wildcard", suffix if suffix else "")
        if pattern.startswith("*."):
            suffix = pattern[2:].strip()
            return cls("subdomain_wildcard", suffix if suffix else "")
        return cls("exact", pattern)

    @classmethod
    def parse_for_constraints(cls, value: str) -> "_DomainPattern":
        pattern = normalize_host(value)
        if pattern.startswith("**."):
            return cls("double_wildcard", pattern[3:])
        if pattern.startswith("*."):
            return cls("subdomain_wildcard", pattern[2:])
        return cls("exact", pattern)

    def allows(self, candidate: "_DomainPattern") -> bool:
        if self.kind == "exact":
            return candidate.kind == "exact" and candidate.suffix == self.suffix
        if self.kind == "subdomain_wildcard":
            if candidate.kind == "exact":
                return candidate.suffix.endswith("." + self.suffix)
            if candidate.kind == "subdomain_wildcard":
                return candidate.suffix == self.suffix or candidate.suffix.endswith("." + self.suffix)
            return False
        if self.kind == "double_wildcard":
            if candidate.kind == "exact":
                return candidate.suffix == self.suffix or candidate.suffix.endswith("." + self.suffix)
            if candidate.kind in {"subdomain_wildcard", "double_wildcard"}:
                return candidate.suffix == self.suffix or candidate.suffix.endswith("." + self.suffix)
        return False

from .mitm_hook import _validate_glob_pattern

__all__ = [
    "DomainGlobSet",
    "Host",
    "compile_allowlist_globset",
    "compile_denylist_globset",
    "is_global_wildcard_domain_pattern",
    "is_loopback_host",
    "is_non_public_ip",
    "normalize_host",
]
