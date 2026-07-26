"""Rust-aligned projection of ``codex-network-proxy::runtime``."""

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

from .reasons import (
    REASON_DENIED,
    REASON_NOT_ALLOWED,
    REASON_NOT_ALLOWED_LOCAL,
)

MAX_BLOCKED_EVENTS = 200


DNS_LOOKUP_TIMEOUT_SECONDS = 2.0


NETWORK_POLICY_VIOLATION_PREFIX = "CODEX_NETWORK_POLICY_VIOLATION"


class HostBlockReason(str, Enum):
    DENIED = REASON_DENIED
    NOT_ALLOWED = REASON_NOT_ALLOWED
    NOT_ALLOWED_LOCAL = REASON_NOT_ALLOWED_LOCAL

    def as_str(self) -> str:
        return self.value


@dataclass(frozen=True)
class HostBlockDecision:
    allowed: bool
    reason: HostBlockReason | None = None

    @classmethod
    def allow(cls) -> "HostBlockDecision":
        return cls(True, None)

    @classmethod
    def blocked(cls, reason: HostBlockReason | str) -> "HostBlockDecision":
        return cls(False, HostBlockReason(reason))


@dataclass(frozen=True)
class ConfigState:
    config: NetworkProxyConfig
    constraints: NetworkProxyConstraints
    blocked: list["BlockedRequest"] = field(default_factory=list)
    blocked_total: int = 0


@dataclass(frozen=True)
class NetworkProxyAuditMetadata:
    value: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True)
class NetworkProxyState:
    state: ConfigState
    reloader: object
    audit_metadata: NetworkProxyAuditMetadata | None = None
    blocked_request_observer: object | None = None
    dns_lookup: Callable[[str, int], object] | None = None
    dns_lookup_timeout: float = DNS_LOOKUP_TIMEOUT_SECONDS

    async def current_cfg(self) -> NetworkProxyConfig:
        await _network_proxy_state_maybe_reload(self)
        return _clone_network_proxy_config(self.state.config)

    async def enabled(self) -> bool:
        await _network_proxy_state_maybe_reload(self)
        return bool(self.state.config.network.enabled)

    async def force_reload(self) -> None:
        reloader = self.reloader
        reload_now = getattr(reloader, "reload_now", None)
        if not callable(reload_now):
            raise AttributeError("reloader must provide reload_now")
        loaded = reload_now()
        if inspect.isawaitable(loaded):
            loaded = await loaded
        if not isinstance(loaded, ConfigState):
            raise TypeError("reload_now must return ConfigState")
        _network_proxy_state_replace_preserving_blocked(self, loaded)

    async def replace_config_state(self, new_state: ConfigState) -> None:
        await _network_proxy_state_maybe_reload(self)
        if not isinstance(new_state, ConfigState):
            raise TypeError("new_state must be ConfigState")
        object.__setattr__(new_state, "blocked", list(self.state.blocked))
        object.__setattr__(new_state, "blocked_total", self.state.blocked_total)
        object.__setattr__(self, "state", new_state)

    async def current_patterns(self) -> tuple[list[str], list[str]]:
        await _network_proxy_state_maybe_reload(self)
        network = self.state.config.network
        return (network.allowed_domains() or [], network.denied_domains() or [])

    async def add_allowed_domain(self, host: str) -> None:
        await self._update_domain_list(host, NetworkDomainPermission.ALLOW)

    async def add_denied_domain(self, host: str) -> None:
        await self._update_domain_list(host, NetworkDomainPermission.DENY)

    async def _update_domain_list(self, host: str, permission: NetworkDomainPermission) -> None:
        parsed_host = Host.parse(host)
        normalized_host = parsed_host.as_str()
        permission = NetworkDomainPermission(permission)
        list_name = "allowlist" if permission is NetworkDomainPermission.ALLOW else "denylist"
        constraint_field = (
            "network.allowed_domains" if permission is NetworkDomainPermission.ALLOW else "network.denied_domains"
        )

        await _network_proxy_state_maybe_reload(self)
        previous_cfg = _clone_network_proxy_config(self.state.config)
        constraints = _clone_network_proxy_constraints(self.state.constraints)

        target_entries = (
            previous_cfg.network.allowed_domains()
            if permission is NetworkDomainPermission.ALLOW
            else previous_cfg.network.denied_domains()
        ) or []
        opposite_entries = (
            previous_cfg.network.denied_domains()
            if permission is NetworkDomainPermission.ALLOW
            else previous_cfg.network.allowed_domains()
        ) or []
        target_contains = any(normalize_host(entry) == normalized_host for entry in target_entries)
        opposite_contains = any(normalize_host(entry) == normalized_host for entry in opposite_entries)
        if target_contains and not opposite_contains:
            return

        candidate = _clone_network_proxy_config(previous_cfg)
        candidate.network.upsert_domain_permission(normalized_host, permission)
        try:
            new_state = build_config_state(candidate, constraints)
        except NetworkProxyConstraintError as exc:
            raise ValueError(f"{constraint_field} constrained by managed config: {exc}") from exc
        except Exception as exc:
            raise ValueError(f"failed to compile updated network {list_name}: {exc}") from exc

        object.__setattr__(new_state, "blocked", list(self.state.blocked))
        object.__setattr__(new_state, "blocked_total", self.state.blocked_total)
        object.__setattr__(self, "state", new_state)

    async def host_blocked(self, host: str, port: int) -> HostBlockDecision:
        await _network_proxy_state_maybe_reload(self)

        try:
            parsed_host = Host.parse(host)
        except ValueError:
            return HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED)

        network = self.state.config.network
        host_str = parsed_host.as_str()
        deny_set = compile_denylist_globset(network.denied_domains() or ())
        allow_set = compile_allowlist_globset(network.allowed_domains() or ())
        allowed_domains = network.allowed_domains() or []

        if deny_set.is_match(host_str):
            return HostBlockDecision.blocked(HostBlockReason.DENIED)
        unscoped_host = _unscoped_ip_literal(host_str)
        if unscoped_host is not None and deny_set.is_match(unscoped_host):
            return HostBlockDecision.blocked(HostBlockReason.DENIED)

        is_allowlisted = allow_set.is_match(host_str)
        if not network.allow_local_binding:
            local_literal = False
            host_no_scope = unscoped_host or host_str
            if is_loopback_host(parsed_host):
                local_literal = True
            else:
                try:
                    local_literal = is_non_public_ip(ipaddress.ip_address(host_no_scope))
                except ValueError:
                    local_literal = False
            if local_literal:
                if not _is_explicit_local_allowlisted(allowed_domains, parsed_host):
                    return HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED_LOCAL)
            elif await host_resolves_to_non_public_ip(
                host_str,
                port,
                self.dns_lookup_timeout,
                self.dns_lookup,
            ):
                return HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED_LOCAL)

        if not allowed_domains or not is_allowlisted:
            return HostBlockDecision.blocked(HostBlockReason.NOT_ALLOWED)
        return HostBlockDecision.allow()

    async def evaluate_mitm_hook_request(self, host: str, request: Any) -> MitmHookEvaluation:
        await _network_proxy_state_maybe_reload(self)
        hooks_by_host = compile_mitm_hooks(self.state.config)
        return evaluate_mitm_hooks(hooks_by_host, host, request)

    async def host_has_mitm_hooks(self, host: str) -> bool:
        await _network_proxy_state_maybe_reload(self)
        hooks_by_host = compile_mitm_hooks(self.state.config)
        return normalize_host(host) in hooks_by_host

    def record_audit_event(self, event: Mapping[str, str]) -> None:
        events = getattr(self, "audit_events", None)
        if events is not None:
            events.append(dict(event))

    async def set_blocked_request_observer(self, observer: object | None) -> None:
        object.__setattr__(self, "blocked_request_observer", observer)

    async def record_blocked(self, entry: "BlockedRequest") -> None:
        await _network_proxy_state_maybe_reload(self)
        self.state.blocked.append(entry)
        object.__setattr__(self.state, "blocked_total", min(self.state.blocked_total + 1, (1 << 64) - 1))
        while len(self.state.blocked) > MAX_BLOCKED_EVENTS:
            self.state.blocked.pop(0)
        observer = self.blocked_request_observer
        if observer is not None:
            callback = getattr(observer, "on_blocked_request", None)
            result = callback(entry) if callable(callback) else observer(entry) if callable(observer) else None
            if inspect.isawaitable(result):
                await result

    async def blocked_snapshot(self) -> list["BlockedRequest"]:
        await _network_proxy_state_maybe_reload(self)
        return list(self.state.blocked)

    async def drain_blocked(self) -> list["BlockedRequest"]:
        await _network_proxy_state_maybe_reload(self)
        blocked = list(self.state.blocked)
        self.state.blocked.clear()
        return blocked

    async def is_unix_socket_allowed(self, path: str) -> bool:
        await _network_proxy_state_maybe_reload(self)
        if not _unix_socket_permissions_supported():
            return False
        if not isinstance(path, str):
            raise TypeError("path must be a string")
        requested_path = Path(path)
        if not requested_path.is_absolute():
            return False
        network = self.state.config.network
        if network.dangerously_allow_all_unix_sockets:
            return True
        requested_canonical = _canonical_path_or_none(requested_path)
        for allowed in network.allow_unix_sockets_effective():
            allowed_path = Path(allowed)
            if not allowed_path.is_absolute():
                continue
            if allowed_path == requested_path:
                return True
            if requested_canonical is None:
                continue
            allowed_canonical = _canonical_path_or_none(allowed_path)
            if allowed_canonical is not None and allowed_canonical == requested_canonical:
                return True
        return False

    async def method_allowed(self, method: str) -> bool:
        await _network_proxy_state_maybe_reload(self)
        return NetworkMode(self.state.config.network.mode).allows_method(method)

    async def allow_upstream_proxy(self) -> bool:
        await _network_proxy_state_maybe_reload(self)
        return bool(self.state.config.network.allow_upstream_proxy)

    async def allow_local_binding(self) -> bool:
        await _network_proxy_state_maybe_reload(self)
        return bool(self.state.config.network.allow_local_binding)

    async def network_mode(self) -> NetworkMode:
        await _network_proxy_state_maybe_reload(self)
        return NetworkMode(self.state.config.network.mode)

    async def set_network_mode(self, mode: NetworkMode | str) -> None:
        await _network_proxy_state_maybe_reload(self)
        candidate = _clone_network_proxy_config(self.state.config)
        candidate.network.mode = NetworkMode(mode)
        constraints = _clone_network_proxy_constraints(self.state.constraints)
        try:
            new_state = build_config_state(candidate, constraints)
        except NetworkProxyConstraintError as exc:
            raise ValueError(f"network.mode constrained by managed config: {exc}") from exc
        object.__setattr__(new_state, "blocked", list(self.state.blocked))
        object.__setattr__(new_state, "blocked_total", self.state.blocked_total)
        object.__setattr__(self, "state", new_state)


@dataclass(frozen=True)
class BlockedRequestArgs:
    host: str
    reason: str
    client: str | None = None
    method: str | None = None
    mode: NetworkMode | str | None = None
    protocol: str = "http"
    decision: str | None = None
    source: str | None = None
    port: int | None = None


@dataclass(frozen=True)
class BlockedRequest:
    host: str
    reason: str
    client: str | None
    method: str | None
    mode: NetworkMode | None
    protocol: str
    decision: str | None = None
    source: str | None = None
    port: int | None = None
    timestamp: int = 0

    @classmethod
    def new(cls, args: BlockedRequestArgs) -> "BlockedRequest":
        return cls(
            host=args.host,
            reason=args.reason,
            client=args.client,
            method=args.method,
            mode=NetworkMode(args.mode) if args.mode is not None else None,
            protocol=args.protocol,
            decision=args.decision,
            source=args.source,
            port=args.port,
            timestamp=unix_timestamp(),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "host": self.host,
            "reason": self.reason,
            "client": self.client,
            "method": self.method,
            "mode": self.mode.value if self.mode is not None else None,
            "protocol": self.protocol,
        }
        if self.decision is not None:
            value["decision"] = self.decision
        if self.source is not None:
            value["source"] = self.source
        if self.port is not None:
            value["port"] = self.port
        value["timestamp"] = self.timestamp
        return value


def unix_timestamp() -> int:
    return int(time.time())


def blocked_request_violation_log_line(entry: BlockedRequest) -> str:
    try:
        payload = json.dumps(entry.to_mapping(), separators=(",", ":"))
    except Exception:
        return f"{NETWORK_POLICY_VIOLATION_PREFIX} host={entry.host} reason={entry.reason}"
    return f"{NETWORK_POLICY_VIOLATION_PREFIX} {payload}"


async def host_resolves_to_non_public_ip(
    host: str,
    port: int,
    lookup_timeout: float = DNS_LOOKUP_TIMEOUT_SECONDS,
    lookup: Callable[[str, int], object] | None = None,
) -> bool:
    """Mirror Rust `runtime.rs` DNS/private-address guard."""
    try:
        return is_non_public_ip(ipaddress.ip_address(host))
    except ValueError:
        pass

    resolver = lookup or _default_dns_lookup
    try:
        result = resolver(host, port)
        if inspect.isawaitable(result):
            addrs = await asyncio.wait_for(result, timeout=lookup_timeout)
        else:
            addrs = result
    except Exception:
        return True

    try:
        for addr in addrs or ():
            ip = _socket_addr_ip(addr)
            if ip is not None and is_non_public_ip(ip):
                return True
    except Exception:
        return True
    return False


async def _default_dns_lookup(host: str, port: int) -> list[tuple[Any, ...]]:
    return await asyncio.to_thread(socket.getaddrinfo, host, port)


def _socket_addr_ip(addr: object) -> str | None:
    if isinstance(addr, tuple):
        if len(addr) >= 5 and isinstance(addr[4], tuple) and addr[4]:
            return str(addr[4][0])
        if addr:
            return str(addr[0])
    if hasattr(addr, "ip"):
        value = getattr(addr, "ip")
        ip = value() if callable(value) else value
        return str(ip)
    if hasattr(addr, "host"):
        value = getattr(addr, "host")
        host = value() if callable(value) else value
        return str(host)
    if isinstance(addr, str):
        if addr.startswith("[") and "]" in addr:
            return addr[1 : addr.index("]")]
        if addr.count(":") == 1:
            return addr.rsplit(":", 1)[0]
        return addr
    return None


async def _network_proxy_state_allow_local_binding(state: NetworkProxyState) -> bool:
    await _network_proxy_state_maybe_reload(state)
    return bool(state.state.config.network.allow_local_binding)


async def _network_proxy_state_maybe_reload(state: NetworkProxyState) -> None:
    reloader = state.reloader
    maybe_reload = getattr(reloader, "maybe_reload", None)
    if callable(maybe_reload):
        loaded = maybe_reload()
        if inspect.isawaitable(loaded):
            loaded = await loaded
        if isinstance(loaded, ConfigState):
            _network_proxy_state_replace_preserving_blocked(state, loaded)


def _network_proxy_state_replace_preserving_blocked(state: NetworkProxyState, new_state: ConfigState) -> None:
    object.__setattr__(new_state, "blocked", list(state.state.blocked))
    object.__setattr__(new_state, "blocked_total", state.state.blocked_total)
    object.__setattr__(state, "state", new_state)


def _unix_socket_permissions_supported() -> bool:
    return os.name == "posix" and getattr(os, "uname", lambda: None)() is not None and os.uname().sysname == "Darwin"


async def _network_proxy_state_enabled(state: NetworkProxyState) -> bool:
    await _network_proxy_state_maybe_reload(state)
    return bool(state.state.config.network.enabled)


async def _network_proxy_state_network_mode(state: NetworkProxyState) -> NetworkMode:
    await _network_proxy_state_maybe_reload(state)
    return NetworkMode(state.state.config.network.mode)


async def _network_proxy_state_mitm_state(state: NetworkProxyState) -> object | None:
    mitm_state = getattr(state, "mitm_state", None)
    if callable(mitm_state):
        result = mitm_state()
        if inspect.isawaitable(result):
            result = await result
        return result
    return getattr(state, "_mitm_state", None)


def _is_explicit_local_allowlisted(allowed_domains: Sequence[str], host: Host) -> bool:
    host_str = host.as_str()
    return any(normalize_host(pattern) == host_str for pattern in allowed_domains)

from .config import (
    NetworkDomainPermission,
    NetworkMode,
    NetworkProxyConfig,
    _canonical_path_or_none,
)
from .mitm_hook import (
    MitmHookEvaluation,
    compile_mitm_hooks,
    evaluate_mitm_hooks,
)
from .policy import (
    Host,
    _unscoped_ip_literal,
    compile_allowlist_globset,
    compile_denylist_globset,
    is_loopback_host,
    is_non_public_ip,
    normalize_host,
)
from .state import (
    NetworkProxyConstraintError,
    NetworkProxyConstraints,
    _clone_network_proxy_config,
    _clone_network_proxy_constraints,
    build_config_state,
)

__all__ = [
    "BlockedRequest",
    "BlockedRequestArgs",
    "ConfigState",
    "DNS_LOOKUP_TIMEOUT_SECONDS",
    "HostBlockDecision",
    "HostBlockReason",
    "MAX_BLOCKED_EVENTS",
    "NETWORK_POLICY_VIOLATION_PREFIX",
    "NetworkProxyAuditMetadata",
    "NetworkProxyState",
    "blocked_request_violation_log_line",
    "host_resolves_to_non_public_ip",
    "unix_timestamp",
]
