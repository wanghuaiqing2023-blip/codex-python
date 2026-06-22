"""Pure helpers from the network proxy loader.

Ported from the portable pieces of
``codex/codex-rs/core/src/network_proxy_loader.rs``.

The real Rust module also loads layered config and constructs a
``codex_network_proxy`` state.  This stdlib port keeps the deterministic helper
semantics that can be represented without that external runtime.
"""

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

AUDIT_TARGET = "codex_otel.network_proxy"
POLICY_DECISION_EVENT_NAME = "codex.network_proxy.policy_decision"
POLICY_SCOPE_DOMAIN = "domain"
POLICY_SCOPE_NON_DOMAIN = "non_domain"
POLICY_DECISION_ALLOW = "allow"
POLICY_DECISION_DENY = "deny"
POLICY_REASON_ALLOW = "allow"
DEFAULT_METHOD = "none"
DEFAULT_CLIENT_ADDRESS = "unknown"
MAX_BLOCKED_EVENTS = 200
DNS_LOOKUP_TIMEOUT_SECONDS = 2.0
NETWORK_POLICY_VIOLATION_PREFIX = "CODEX_NETWORK_POLICY_VIOLATION"
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

REASON_DENIED = "denied"
REASON_METHOD_NOT_ALLOWED = "method_not_allowed"
REASON_MITM_HOOK_DENIED = "mitm_hook_denied"
REASON_MITM_REQUIRED = "mitm_required"
REASON_NOT_ALLOWED = "not_allowed"
REASON_NOT_ALLOWED_LOCAL = "not_allowed_local"
REASON_POLICY_DENIED = "policy_denied"
REASON_PROXY_DISABLED = "proxy_disabled"
REASON_UNIX_SOCKET_UNSUPPORTED = "unix_socket_unsupported"
MANAGED_MITM_CA_DIR = "proxy"
MANAGED_MITM_CA_CERT = "ca.pem"
MANAGED_MITM_CA_KEY = "ca.key"


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


class NetworkProtocol(str, Enum):
    HTTP = "http"
    HTTPS_CONNECT = "https_connect"
    SOCKS5_TCP = "socks5_tcp"
    SOCKS5_UDP = "socks5_udp"

    def as_policy_protocol(self) -> str:
        return self.value


class NetworkPolicyDecision(str, Enum):
    DENY = "deny"
    ASK = "ask"

    def as_str(self) -> str:
        return self.value


class NetworkDecisionSource(str, Enum):
    BASELINE_POLICY = "baseline_policy"
    MODE_GUARD = "mode_guard"
    PROXY_STATE = "proxy_state"
    DECIDER = "decider"

    def as_str(self) -> str:
        return self.value


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


@dataclass(frozen=True)
class InjectedHeaderConfig:
    name: str
    secret_env_var: str | None = None
    secret_file: str | None = None
    prefix: str | None = None


@dataclass(frozen=True)
class MitmHookActionsConfig:
    strip_request_headers: list[str] = field(default_factory=list)
    inject_request_headers: list[InjectedHeaderConfig] = field(default_factory=list)


@dataclass(frozen=True)
class MitmHookMatchConfig:
    methods: list[str] = field(default_factory=list)
    path_prefixes: list[str] = field(default_factory=list)
    query: Mapping[str, list[str]] = field(default_factory=dict)
    headers: Mapping[str, list[str]] = field(default_factory=dict)
    body: JsonValue | None = None


@dataclass(frozen=True)
class MitmHookConfig:
    host: str
    matcher: MitmHookMatchConfig = field(default_factory=MitmHookMatchConfig)
    actions: MitmHookActionsConfig = field(default_factory=MitmHookActionsConfig)


@dataclass(frozen=True)
class CompiledGlobMatcher:
    pattern: str
    literal_separator: bool = False

    def __post_init__(self) -> None:
        _validate_glob_pattern(self.pattern)

    def is_match(self, candidate: str) -> bool:
        if self.literal_separator:
            return re.fullmatch(_glob_to_regex(self.pattern, literal_separator=True), candidate) is not None
        return fnmatch.fnmatchcase(candidate, self.pattern)


@dataclass(frozen=True)
class PathMatcher:
    kind: str
    value: str
    glob: CompiledGlobMatcher | None = None

    @classmethod
    def prefix(cls, value: str) -> "PathMatcher":
        return cls("prefix", value)

    @classmethod
    def glob_matcher(cls, pattern: str) -> "PathMatcher":
        return cls("glob", pattern, CompiledGlobMatcher(pattern, literal_separator=True))

    def matches(self, candidate: str) -> bool:
        if self.kind == "prefix":
            return candidate.startswith(self.value)
        assert self.glob is not None
        return self.glob.is_match(candidate)


@dataclass(frozen=True)
class ValueMatcher:
    kind: str
    value: str
    glob: CompiledGlobMatcher | None = None

    @classmethod
    def exact(cls, value: str) -> "ValueMatcher":
        return cls("exact", value)

    @classmethod
    def glob_matcher(cls, pattern: str) -> "ValueMatcher":
        return cls("glob", pattern, CompiledGlobMatcher(pattern, literal_separator=False))

    def matches(self, candidate: str) -> bool:
        if self.kind == "exact":
            return candidate == self.value
        assert self.glob is not None
        return self.glob.is_match(candidate)


@dataclass(frozen=True)
class QueryConstraint:
    name: str
    allowed_values: tuple[ValueMatcher, ...]


@dataclass(frozen=True)
class HeaderConstraint:
    name: str
    allowed_values: tuple[ValueMatcher, ...]


@dataclass(frozen=True)
class SecretSource:
    kind: str
    value: str

    @classmethod
    def env_var(cls, name: str) -> "SecretSource":
        return cls("env_var", name)

    @classmethod
    def file(cls, path: str) -> "SecretSource":
        return cls("file", str(Path(path)))


@dataclass(frozen=True)
class ResolvedInjectedHeader:
    name: str
    value: str
    source: SecretSource


@dataclass(frozen=True)
class MitmHookActions:
    strip_request_headers: tuple[str, ...] = ()
    inject_request_headers: tuple[ResolvedInjectedHeader, ...] = ()


@dataclass(frozen=True)
class MitmHookMatcher:
    methods: tuple[str, ...] = ()
    path_prefixes: tuple[PathMatcher, ...] = ()
    query: tuple[QueryConstraint, ...] = ()
    headers: tuple[HeaderConstraint, ...] = ()
    body: JsonValue | None = None


@dataclass(frozen=True)
class MitmHook:
    host: str
    matcher: MitmHookMatcher
    actions: MitmHookActions


class HookEvaluation(Enum):
    NO_HOOKS_FOR_HOST = "NoHooksForHost"
    HOOKED_HOST_NO_MATCH = "HookedHostNoMatch"
    MATCHED = "Matched"


@dataclass(frozen=True)
class MitmHookEvaluation:
    kind: HookEvaluation
    actions: MitmHookActions | None = None

    @classmethod
    def no_hooks_for_host(cls) -> "MitmHookEvaluation":
        return cls(HookEvaluation.NO_HOOKS_FOR_HOST)

    @classmethod
    def hooked_host_no_match(cls) -> "MitmHookEvaluation":
        return cls(HookEvaluation.HOOKED_HOST_NO_MATCH)

    @classmethod
    def matched(cls, actions: MitmHookActions) -> "MitmHookEvaluation":
        return cls(HookEvaluation.MATCHED, actions)

    def is_matched(self) -> bool:
        return self.kind is HookEvaluation.MATCHED


@dataclass(frozen=True)
class MitmPolicyContext:
    target_host: str
    target_port: int
    mode: NetworkMode
    app_state: "NetworkProxyState"


@dataclass(frozen=True)
class MitmPolicyDecision:
    allowed: bool
    response: "NetworkProxyResponse | None" = None
    hook_actions: MitmHookActions | None = None

    @classmethod
    def allow(cls, hook_actions: MitmHookActions | None = None) -> "MitmPolicyDecision":
        return cls(True, hook_actions=hook_actions)

    @classmethod
    def block(cls, response: "NetworkProxyResponse") -> "MitmPolicyDecision":
        return cls(False, response=response)


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
class NetworkPolicyRequestArgs:
    protocol: NetworkProtocol
    host: str
    port: int
    client_addr: str | None = None
    method: str | None = None
    command: str | None = None
    exec_policy_hint: str | None = None


@dataclass(frozen=True)
class NetworkPolicyRequest:
    protocol: NetworkProtocol
    host: str
    port: int
    client_addr: str | None = None
    method: str | None = None
    command: str | None = None
    exec_policy_hint: str | None = None

    @classmethod
    def new(cls, args: NetworkPolicyRequestArgs) -> "NetworkPolicyRequest":
        return cls(
            protocol=NetworkProtocol(args.protocol),
            host=args.host,
            port=args.port,
            client_addr=args.client_addr,
            method=args.method,
            command=args.command,
            exec_policy_hint=args.exec_policy_hint,
        )


@dataclass(frozen=True)
class NetworkDecision:
    kind: str
    reason: str | None = None
    source: NetworkDecisionSource | None = None
    decision: NetworkPolicyDecision | None = None

    @classmethod
    def allow(cls) -> "NetworkDecision":
        return cls("allow")

    @classmethod
    def deny(cls, reason: str) -> "NetworkDecision":
        return cls.deny_with_source(reason, NetworkDecisionSource.DECIDER)

    @classmethod
    def ask(cls, reason: str) -> "NetworkDecision":
        return cls.ask_with_source(reason, NetworkDecisionSource.DECIDER)

    @classmethod
    def deny_with_source(
        cls,
        reason: str,
        source: NetworkDecisionSource | str,
    ) -> "NetworkDecision":
        return cls(
            "deny",
            reason or REASON_POLICY_DENIED,
            NetworkDecisionSource(source),
            NetworkPolicyDecision.DENY,
        )

    @classmethod
    def ask_with_source(
        cls,
        reason: str,
        source: NetworkDecisionSource | str,
    ) -> "NetworkDecision":
        return cls(
            "deny",
            reason or REASON_POLICY_DENIED,
            NetworkDecisionSource(source),
            NetworkPolicyDecision.ASK,
        )

    @property
    def is_allow(self) -> bool:
        return self.kind == "allow"


@dataclass(frozen=True)
class BlockDecisionAuditEventArgs:
    source: NetworkDecisionSource
    reason: str
    protocol: NetworkProtocol
    server_address: str
    server_port: int
    method: str | None = None
    client_addr: str | None = None


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


@dataclass(frozen=True)
class PolicyDecisionDetails:
    decision: NetworkPolicyDecision
    reason: str
    source: NetworkDecisionSource
    protocol: NetworkProtocol
    host: str
    port: int


@dataclass(frozen=True)
class NetworkProxyResponse:
    status: int
    body: str
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HttpConnectRequest:
    uri: str
    headers: Mapping[str, object] = field(default_factory=dict)
    client: str | None = None


@dataclass(frozen=True)
class HttpConnectAccepted:
    host: str
    port: int
    mitm_enabled: bool
    mode: NetworkMode
    mitm_state: object | None = None


@dataclass(frozen=True)
class HttpConnectAcceptResult:
    response: NetworkProxyResponse
    request: HttpConnectRequest
    accepted: HttpConnectAccepted


@dataclass(frozen=True)
class HttpPlainRequest:
    method: str
    uri: str
    headers: Mapping[str, object] = field(default_factory=dict)
    client: str | None = None


@dataclass(frozen=True)
class Socks5TcpRequest:
    host: str
    port: int
    client: str | None = None


@dataclass(frozen=True)
class Socks5UdpRequest:
    host: str
    port: int
    payload: bytes = b""
    client: str | None = None


@dataclass(frozen=True)
class Socks5PolicyResult:
    protocol: str
    host: str
    port: int
    payload: bytes | None = None


class Socks5PolicyError(PermissionError):
    def __init__(self, reason: str, details: PolicyDecisionDetails) -> None:
        self.reason = reason
        self.details = details
        super().__init__(blocked_message_with_policy(reason, details))


@dataclass(frozen=True)
class ManagedMitmCaPaths:
    cert_path: Path
    key_path: Path


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


class TargetRejectedError(PermissionError):
    """Raised when connect_policy rejects a direct TCP target."""


@dataclass(frozen=True)
class TargetCheckedTcpConnector:
    policy: bool | NetworkProxyState

    @classmethod
    def new(cls, state: NetworkProxyState) -> "TargetCheckedTcpConnector":
        return cls(state)

    @classmethod
    def from_allow_local_binding(cls, allow_local_binding: bool) -> "TargetCheckedTcpConnector":
        return cls(bool(allow_local_binding))

    async def allow_local_binding(self) -> bool:
        if isinstance(self.policy, bool):
            return self.policy
        return await _network_proxy_state_allow_local_binding(self.policy)

    async def check_target(
        self,
        host: str,
        port: int,
        *,
        proxy_address: object | None = None,
    ) -> None:
        if proxy_address is not None:
            return
        if not await self.allow_local_binding():
            try:
                address = ipaddress.ip_address(_unscoped_ip_literal(normalize_host(host)) or normalize_host(host))
            except ValueError:
                return
            if is_non_public_ip(address):
                raise TargetRejectedError("network target rejected by policy")

    async def connect(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
        proxy_address: object | None = None,
    ) -> socket.socket:
        await self.check_target(host, port, proxy_address=proxy_address)
        return socket.create_connection((host, port), timeout=timeout)


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


def validate_absolute_form_host_header(url: str, headers: Mapping[str, object]) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme:
        return None
    target_host = parsed.hostname
    if not target_host:
        return None
    host_header = _header_value(headers, "host")
    if host_header is None:
        return None
    try:
        header_host, header_port = _parse_host_header(str(host_header))
    except ValueError:
        return "invalid Host header"
    if normalize_host(header_host) != normalize_host(target_host):
        return "Host header does not match request target"
    target_port = parsed.port
    if header_port is not None:
        if header_port != target_port:
            return "Host header does not match request target"
        return None
    if target_port is not None and target_port != _default_port_for_scheme(parsed.scheme):
        return "Host header does not match request target"
    return None


async def http_connect_accept(
    request: HttpConnectRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> HttpConnectAcceptResult:
    http_request = _http_connect_request(request)
    authority = _http_connect_authority(http_request)
    if authority is None:
        raise HttpConnectRejected(text_response(400, "missing authority"))

    host = normalize_host(authority[0])
    port = authority[1]
    if not host:
        raise HttpConnectRejected(text_response(400, "invalid host"))

    client = http_request.client
    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.HTTPS_CONNECT,
            host=host,
            port=port,
        )
        await _record_http_connect_blocked(state, host, port, client, None, details)
        raise HttpConnectRejected(blocked_text_response_with_policy(REASON_PROXY_DISABLED, details))

    decision = await evaluate_host_policy(
        state,
        decider,
        NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.HTTPS_CONNECT,
                host=host,
                port=port,
                client_addr=client,
                method="CONNECT",
                command=None,
                exec_policy_hint=None,
            )
        ),
    )
    if not decision.is_allow:
        if decision.reason is None or decision.source is None or decision.decision is None:
            raise ValueError("deny network decision must carry decision, source, and reason")
        details = PolicyDecisionDetails(
            decision=decision.decision,
            reason=decision.reason,
            source=decision.source,
            protocol=NetworkProtocol.HTTPS_CONNECT,
            host=host,
            port=port,
        )
        await _record_http_connect_blocked(state, host, port, client, None, details)
        raise HttpConnectRejected(blocked_text_response_with_policy(decision.reason, details))

    mode = await _network_proxy_state_network_mode(state)
    mitm_state = await _network_proxy_state_mitm_state(state)
    host_has_hooks = await state.host_has_mitm_hooks(host)
    connect_needs_mitm = mode is NetworkMode.LIMITED or host_has_hooks

    if connect_needs_mitm and mitm_state is None:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_MITM_REQUIRED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.HTTPS_CONNECT,
            host=host,
            port=port,
        )
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.MODE_GUARD,
                reason=REASON_MITM_REQUIRED,
                protocol=NetworkProtocol.HTTPS_CONNECT,
                server_address=host,
                server_port=port,
                method="CONNECT",
                client_addr=client,
            ),
        )
        await _record_http_connect_blocked(state, host, port, client, mode, details)
        raise HttpConnectRejected(blocked_text_response_with_policy(REASON_MITM_REQUIRED, details))

    return HttpConnectAcceptResult(
        response=NetworkProxyResponse(status=200, body="", headers={}),
        request=http_request,
        accepted=HttpConnectAccepted(
            host=host,
            port=port,
            mitm_enabled=connect_needs_mitm,
            mode=mode,
            mitm_state=mitm_state if connect_needs_mitm else None,
        ),
    )


class HttpConnectRejected(PermissionError):
    def __init__(self, response: NetworkProxyResponse) -> None:
        self.response = response
        super().__init__(response.body)


async def run_http_proxy(
    state: NetworkProxyState,
    addr: tuple[str, int] | str,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> None:
    """Run the dependency-light HTTP/1 proxy listener.

    Rust source: codex-network-proxy/src/http_proxy.rs `run_http_proxy`.
    Contract: bind an HTTP proxy listener and serve HTTP/1 CONNECT/plain
    requests through the same policy helpers as the direct Python facades.
    """

    host, port = _parse_socket_addr(addr)
    server = await asyncio.start_server(
        lambda reader, writer: _handle_http_proxy_client(reader, writer, state, decider),
        host=host,
        port=port,
    )
    try:
        async with server:
            await server.serve_forever()
    finally:
        server.close()
        await server.wait_closed()


async def run_http_proxy_with_std_listener(
    state: NetworkProxyState,
    listener: socket.socket,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> None:
    """Serve HTTP proxy traffic from an existing stdlib listener socket."""

    listener.setblocking(False)
    server = await asyncio.start_server(
        lambda reader, writer: _handle_http_proxy_client(reader, writer, state, decider),
        sock=listener,
    )
    try:
        async with server:
            await server.serve_forever()
    finally:
        server.close()
        await server.wait_closed()


async def http_plain_proxy(
    request: HttpPlainRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> NetworkProxyResponse:
    http_request = _http_plain_request(request)
    method = http_request.method.upper()
    method_allowed = await state.method_allowed(method)
    socket_path = _header_value(http_request.headers, "x-unix-socket")
    if socket_path is None:
        authority = _http_plain_authority(http_request)
        if authority is None:
            return text_response(400, "missing host")
        host = normalize_host(authority[0])
        port = authority[1]
        mismatch_reason = validate_absolute_form_host_header(http_request.uri, http_request.headers)
        if mismatch_reason is not None:
            return text_response(400, mismatch_reason)

        if not await _network_proxy_state_enabled(state):
            details = PolicyDecisionDetails(
                decision=NetworkPolicyDecision.DENY,
                reason=REASON_PROXY_DISABLED,
                source=NetworkDecisionSource.PROXY_STATE,
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
            )
            emit_block_decision_audit_event(
                state,
                BlockDecisionAuditEventArgs(
                    source=NetworkDecisionSource.PROXY_STATE,
                    reason=REASON_PROXY_DISABLED,
                    protocol=NetworkProtocol.HTTP,
                    server_address=host,
                    server_port=port,
                    method=method,
                    client_addr=http_request.client,
                ),
            )
            await _record_plain_http_blocked(state, host, port, http_request.client, method, None, details)
            return text_response(503, blocked_message_with_policy(REASON_PROXY_DISABLED, details))

        policy_request = NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
                client_addr=http_request.client,
                method=method,
                command=None,
                exec_policy_hint=None,
            )
        )
        decision = await evaluate_host_policy(state, decider, policy_request)
        if not decision.is_allow:
            if decision.reason is None or decision.source is None or decision.decision is None:
                raise ValueError("deny network decision must carry decision, source, and reason")
            details = PolicyDecisionDetails(
                decision=decision.decision,
                reason=decision.reason,
                source=decision.source,
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
            )
            await _record_plain_http_blocked(state, host, port, http_request.client, method, None, details)
            return json_blocked(host, decision.reason, details)

        if not method_allowed:
            details = PolicyDecisionDetails(
                decision=NetworkPolicyDecision.DENY,
                reason=REASON_METHOD_NOT_ALLOWED,
                source=NetworkDecisionSource.MODE_GUARD,
                protocol=NetworkProtocol.HTTP,
                host=host,
                port=port,
            )
            emit_block_decision_audit_event(
                state,
                BlockDecisionAuditEventArgs(
                    source=NetworkDecisionSource.MODE_GUARD,
                    reason=REASON_METHOD_NOT_ALLOWED,
                    protocol=NetworkProtocol.HTTP,
                    server_address=host,
                    server_port=port,
                    method=method,
                    client_addr=http_request.client,
                ),
            )
            await _record_plain_http_blocked(state, host, port, http_request.client, method, NetworkMode.LIMITED, details)
            return json_blocked(host, REASON_METHOD_NOT_ALLOWED, details)

        try:
            allow_upstream_proxy = await state.allow_upstream_proxy()
        except Exception:
            allow_upstream_proxy = False
        upstream_proxy = ProxyConfig.from_env().proxy_for_protocol(False) if allow_upstream_proxy else None
        try:
            return await _serve_plain_http_upstream(http_request, host, port, upstream_proxy)
        except OSError:
            return text_response(502, "upstream failure")
    socket_path = str(socket_path)

    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.HTTP,
            host=socket_path,
            port=0,
        )
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.PROXY_STATE,
                reason=REASON_PROXY_DISABLED,
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        await _record_plain_http_blocked(state, socket_path, 0, http_request.client, method, None, details)
        return text_response(503, blocked_message_with_policy(REASON_PROXY_DISABLED, details))

    if not method_allowed:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_METHOD_NOT_ALLOWED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.HTTP,
            host="unix-socket",
            port=0,
        )
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.MODE_GUARD,
                reason=REASON_METHOD_NOT_ALLOWED,
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        return json_blocked("unix-socket", REASON_METHOD_NOT_ALLOWED, None)

    if not _unix_socket_permissions_supported():
        emit_block_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.PROXY_STATE,
                reason=REASON_UNIX_SOCKET_UNSUPPORTED,
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        return text_response(501, "unix sockets unsupported")

    if await state.is_unix_socket_allowed(socket_path):
        emit_allow_decision_audit_event(
            state,
            BlockDecisionAuditEventArgs(
                source=NetworkDecisionSource.PROXY_STATE,
                reason="allow",
                protocol=NetworkProtocol.HTTP,
                server_address="unix-socket",
                server_port=0,
                method=method,
                client_addr=http_request.client,
            ),
        )
        return text_response(502, "unix socket proxy failed")

    emit_block_decision_audit_event(
        state,
        BlockDecisionAuditEventArgs(
            source=NetworkDecisionSource.PROXY_STATE,
            reason=REASON_NOT_ALLOWED,
            protocol=NetworkProtocol.HTTP,
            server_address="unix-socket",
            server_port=0,
            method=method,
            client_addr=http_request.client,
        ),
    )
    return json_blocked("unix-socket", REASON_NOT_ALLOWED, None)


def remove_hop_by_hop_request_headers(headers: MutableMapping[str, object]) -> None:
    while True:
        connection_key = _header_key(headers, "connection")
        if connection_key is None:
            break
        raw_connection = headers.pop(connection_key)
        for token in _connection_header_tokens(raw_connection):
            key = _header_key(headers, token)
            if key is not None:
                headers.pop(key, None)
    for name in (
        "keep-alive",
        "proxy-connection",
        "proxy-authorization",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "te",
    ):
        key = _header_key(headers, name)
        if key is not None:
            headers.pop(key, None)


async def _serve_plain_http_upstream(
    request: HttpPlainRequest,
    host: str,
    port: int,
    proxy: ProxyAddress | None,
) -> NetworkProxyResponse:
    connect_host = proxy.host if proxy is not None else host
    if not connect_host:
        raise OSError("missing upstream host")
    if proxy is not None:
        connect_port = proxy.port or 80
    else:
        connect_port = port

    reader, writer = await asyncio.open_connection(connect_host, connect_port)
    try:
        headers: dict[str, object] = dict(request.headers)
        remove_hop_by_hop_request_headers(headers)
        if _header_key(headers, "host") is None:
            headers["host"] = _authority_header_for_host_port(host, port)

        target = _plain_http_request_target(request.uri, host, port, proxy is not None)
        lines = [f"{request.method.upper()} {target} HTTP/1.1"]
        for key, value in headers.items():
            if value is None:
                continue
            lines.append(f"{key}: {value}")
        lines.append("")
        lines.append("")
        writer.write("\r\n".join(lines).encode("iso-8859-1", "replace"))
        await writer.drain()

        response_head = await reader.readuntil(b"\r\n\r\n")
        status, response_headers, content_length = _parse_plain_http_response_head(response_head)
        if content_length is None:
            body = await reader.read()
        else:
            body = await reader.readexactly(content_length)
        return NetworkProxyResponse(
            status=status,
            body=body.decode("utf-8", "replace"),
            headers=response_headers,
        )
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError) as exc:
        raise OSError("upstream failure") from exc
    finally:
        await _close_stream_writer(writer)


def _plain_http_request_target(uri: str, host: str, port: int, via_proxy: bool) -> str:
    parsed = urlparse(uri)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    if via_proxy:
        if parsed.scheme and parsed.netloc:
            return uri
        return f"http://{_authority_header_for_host_port(host, port)}{path}"
    return path


def _authority_header_for_host_port(host: str, port: int) -> str:
    if ":" in host and not (host.startswith("[") and host.endswith("]")):
        host = f"[{host}]"
    return host if port == 80 else f"{host}:{port}"


def _parse_plain_http_response_head(head: bytes) -> tuple[int, dict[str, str], int | None]:
    text = head.decode("iso-8859-1")
    lines = text.split("\r\n")
    if not lines or not lines[0].startswith("HTTP/"):
        raise ValueError("invalid HTTP response")
    parts = lines[0].split(" ", 2)
    if len(parts) < 2:
        raise ValueError("missing HTTP status")
    status = int(parts[1])
    headers: dict[str, str] = {}
    content_length: int | None = None
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        lower_name = name.strip().lower()
        stripped = value.strip()
        headers[lower_name] = stripped
        if lower_name == "content-length":
            content_length = int(stripped)
    return status, headers, content_length


@dataclass(frozen=True)
class StartedNetworkProxy:
    proxy_value: Any
    handle: Any

    def proxy(self) -> Any:
        return self.proxy_value


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


@dataclass(frozen=True)
class StaticNetworkProxyReloader:
    state: ConfigState

    async def maybe_reload(self) -> None:
        return None

    async def reload_now(self) -> ConfigState:
        return self.state

    def source_label(self) -> str:
        return "StaticNetworkProxyReloader"


NetworkProxyBuilderCallback = Callable[
    [NetworkProxyState, object, object | None, object | None, bool, NetworkProxyAuditMetadata],
    StartedNetworkProxy | Awaitable[StartedNetworkProxy],
]
ConfigLayersLoader = Callable[
    [],
    Sequence["ConfigLayerEntry"] | Awaitable[Sequence["ConfigLayerEntry"]],
]


@dataclass(frozen=True)
class NetworkConstraints:
    enabled: bool | None = None
    http_port: int | None = None
    socks_port: int | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    domains: Mapping[str, str | NetworkDomainPermission] | None = None
    unix_sockets: Sequence[str] | None = None
    allow_local_binding: bool | None = None
    managed_allowed_domains_only: bool | None = None


@dataclass(frozen=True)
class NetworkToml:
    enabled: bool | None = None
    mode: str | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    domains: Mapping[str, str | NetworkDomainPermission] | None = None
    unix_sockets: Sequence[str] | None = None
    allow_local_binding: bool | None = None


@dataclass(frozen=True)
class NetworkTablesToml:
    default_permissions: str | None = None
    permissions: Mapping[str, Mapping[str, JsonValue]] | None = None


@dataclass(frozen=True)
class ConfigLayerSource:
    type: str
    file: Path | None = None
    dot_codex_folder: Path | None = None
    profile: str | None = None

    @classmethod
    def system(cls, file: Path | str) -> "ConfigLayerSource":
        return cls("system", file=Path(file))

    @classmethod
    def user(cls, file: Path | str, profile: str | None = None) -> "ConfigLayerSource":
        return cls("user", file=Path(file), profile=profile)

    @classmethod
    def project(cls, dot_codex_folder: Path | str) -> "ConfigLayerSource":
        return cls("project", dot_codex_folder=Path(dot_codex_folder))

    @classmethod
    def legacy_managed_config_toml_from_file(cls, file: Path | str) -> "ConfigLayerSource":
        return cls("legacy_managed_config_toml_from_file", file=Path(file))

    @classmethod
    def session_flags(cls) -> "ConfigLayerSource":
        return cls("session_flags")

    @classmethod
    def other(cls, label: str = "other") -> "ConfigLayerSource":
        return cls(label)

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.file is not None and not isinstance(self.file, Path):
            object.__setattr__(self, "file", Path(self.file))
        if self.dot_codex_folder is not None and not isinstance(self.dot_codex_folder, Path):
            object.__setattr__(self, "dot_codex_folder", Path(self.dot_codex_folder))
        if self.profile is not None and not isinstance(self.profile, str):
            object.__setattr__(self, "profile", str(self.profile))


@dataclass(frozen=True)
class ConfigLayerEntry:
    name: ConfigLayerSource
    config: Mapping[str, JsonValue] = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, ConfigLayerSource):
            raise TypeError("name must be ConfigLayerSource")
        if not isinstance(self.config, Mapping):
            raise TypeError("config must be a mapping")
        if not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")


@dataclass(frozen=True)
class LayerMtime:
    path: Path
    mtime: int | None = None

    @classmethod
    def new(cls, path: Path | str) -> "LayerMtime":
        path = Path(path)
        return cls(path=path, mtime=_path_mtime_ns(path))

    def current_mtime(self) -> int | None:
        return _path_mtime_ns(self.path)

    def changed(self) -> bool:
        current = self.current_mtime()
        if current is not None and self.mtime is not None:
            return current > self.mtime
        if current is not None and self.mtime is None:
            return True
        if current is None and self.mtime is not None:
            return True
        return False


class MtimeConfigReloader:
    def __init__(self, layer_mtimes: Sequence[LayerMtime]) -> None:
        if not isinstance(layer_mtimes, Sequence):
            raise TypeError("layer_mtimes must be a sequence")
        if not all(isinstance(item, LayerMtime) for item in layer_mtimes):
            raise TypeError("layer_mtimes must contain LayerMtime values")
        self.layer_mtimes = list(layer_mtimes)

    def source_label(self) -> str:
        return "config layers"

    def needs_reload(self) -> bool:
        return any(layer.changed() for layer in self.layer_mtimes)

    def reload_now(self, layer_mtimes: Sequence[LayerMtime]) -> None:
        if not all(isinstance(item, LayerMtime) for item in layer_mtimes):
            raise TypeError("layer_mtimes must contain LayerMtime values")
        self.layer_mtimes = list(layer_mtimes)


@dataclass(frozen=True)
class NetworkProxySpec:
    base_config: NetworkProxyConfig
    requirements: NetworkConstraints | None
    config: NetworkProxyConfig
    constraints: NetworkProxyConstraints
    hard_deny_allowlist_misses: bool = False

    @classmethod
    def from_config_and_constraints(
        cls,
        config: NetworkProxyConfig,
        requirements: NetworkConstraints | None,
        permission_profile: object,
    ) -> "NetworkProxySpec":
        if not isinstance(config, NetworkProxyConfig):
            raise TypeError("config must be NetworkProxyConfig")
        if requirements is not None and not isinstance(requirements, NetworkConstraints):
            raise TypeError("requirements must be NetworkConstraints")
        base_config = _clone_network_proxy_config(config)
        if requirements is None:
            return cls(base_config, None, _clone_network_proxy_config(config), NetworkProxyConstraints())
        hard_deny = cls.managed_allowed_domains_only(requirements)
        effective, constraints = cls.apply_requirements(
            _clone_network_proxy_config(config),
            requirements,
            permission_profile,
            hard_deny,
        )
        return cls(base_config, requirements, effective, constraints, hard_deny)

    def enabled(self) -> bool:
        return self.config.network.enabled

    def proxy_host_and_port(self) -> str:
        return _host_and_port_from_url(self.config.network.proxy_url, 3128)

    def socks_enabled(self) -> bool:
        return self.config.network.enable_socks5

    async def start_proxy(
        self,
        permission_profile: object,
        policy_decider: object | None,
        blocked_request_observer: object | None,
        enable_network_approval_flow: bool,
        audit_metadata: NetworkProxyAuditMetadata | Mapping[str, JsonValue] | None,
        *,
        network_proxy_builder: NetworkProxyBuilderCallback,
    ) -> StartedNetworkProxy:
        if not isinstance(enable_network_approval_flow, bool):
            raise TypeError("enable_network_approval_flow must be a bool")
        if audit_metadata is None:
            audit_metadata = NetworkProxyAuditMetadata()
        elif isinstance(audit_metadata, Mapping):
            audit_metadata = NetworkProxyAuditMetadata(dict(audit_metadata))
        elif not isinstance(audit_metadata, NetworkProxyAuditMetadata):
            raise TypeError("audit_metadata must be NetworkProxyAuditMetadata, mapping, or None")
        if not callable(network_proxy_builder):
            raise TypeError("network_proxy_builder must be callable")
        effective_policy_decider = policy_decider
        if (
            enable_network_approval_flow
            and not self.hard_deny_allowlist_misses
            and effective_policy_decider is None
            and self.managed_sandbox_active(permission_profile)
        ):
            effective_policy_decider = ask_not_allowed_policy_decider
        state = self.build_state_with_audit_metadata(audit_metadata)
        started = network_proxy_builder(
            state,
            permission_profile,
            effective_policy_decider,
            blocked_request_observer,
            enable_network_approval_flow,
            audit_metadata,
        )
        if inspect.isawaitable(started):
            started = await started
        if not isinstance(started, StartedNetworkProxy):
            raise TypeError("network_proxy_builder must return StartedNetworkProxy")
        return started

    def recompute_for_permission_profile(self, permission_profile: object) -> "NetworkProxySpec":
        return type(self).from_config_and_constraints(self.base_config, self.requirements, permission_profile)

    def with_exec_policy_network_rules(self, exec_policy: object) -> "NetworkProxySpec":
        config = _clone_network_proxy_config(self.config)
        apply_exec_policy_network_rules(config, exec_policy)
        return type(self)(
            _clone_network_proxy_config(self.base_config),
            self.requirements,
            config,
            _clone_network_proxy_constraints(self.constraints),
            self.hard_deny_allowlist_misses,
        )

    async def apply_to_started_proxy(self, started_proxy: StartedNetworkProxy) -> None:
        if not isinstance(started_proxy, StartedNetworkProxy):
            raise TypeError("started_proxy must be StartedNetworkProxy")
        proxy = started_proxy.proxy()
        replacer = getattr(proxy, "replace_config_state", None)
        if not callable(replacer):
            raise AttributeError("started proxy must provide replace_config_state")
        result = replacer(self.build_config_state_for_spec())
        if inspect.isawaitable(result):
            await result

    def build_state_with_audit_metadata(
        self,
        audit_metadata: NetworkProxyAuditMetadata | Mapping[str, JsonValue] | None,
    ) -> NetworkProxyState:
        if audit_metadata is None:
            audit_metadata = NetworkProxyAuditMetadata()
        elif isinstance(audit_metadata, Mapping):
            audit_metadata = NetworkProxyAuditMetadata(dict(audit_metadata))
        elif not isinstance(audit_metadata, NetworkProxyAuditMetadata):
            raise TypeError("audit_metadata must be NetworkProxyAuditMetadata, mapping, or None")
        return NetworkProxyState(
            self.build_config_state_for_spec(),
            reloader=None,
            audit_metadata=audit_metadata,
        )

    def build_config_state_for_spec(self) -> ConfigState:
        return ConfigState(
            _clone_network_proxy_config(self.config),
            _clone_network_proxy_constraints(self.constraints),
        )

    @staticmethod
    def apply_requirements(
        config: NetworkProxyConfig,
        requirements: NetworkConstraints,
        permission_profile: object,
        hard_deny_allowlist_misses: bool,
    ) -> tuple[NetworkProxyConfig, NetworkProxyConstraints]:
        constraints = NetworkProxyConstraints()
        allowlist_expansion_enabled = NetworkProxySpec.allowlist_expansion_enabled(
            permission_profile,
            hard_deny_allowlist_misses,
        )
        denylist_expansion_enabled = NetworkProxySpec.denylist_expansion_enabled(permission_profile)

        if requirements.enabled is not None:
            config.network.enabled = requirements.enabled
            constraints.enabled = requirements.enabled
        if requirements.http_port is not None:
            config.network.proxy_url = f"http://127.0.0.1:{requirements.http_port}"
        if requirements.socks_port is not None:
            config.network.socks_url = f"http://127.0.0.1:{requirements.socks_port}"
        if requirements.allow_upstream_proxy is not None:
            config.network.allow_upstream_proxy = requirements.allow_upstream_proxy
            constraints.allow_upstream_proxy = requirements.allow_upstream_proxy
        if requirements.dangerously_allow_non_loopback_proxy is not None:
            config.network.dangerously_allow_non_loopback_proxy = requirements.dangerously_allow_non_loopback_proxy
            constraints.dangerously_allow_non_loopback_proxy = requirements.dangerously_allow_non_loopback_proxy
        if requirements.dangerously_allow_all_unix_sockets is not None:
            config.network.dangerously_allow_all_unix_sockets = requirements.dangerously_allow_all_unix_sockets
            constraints.dangerously_allow_all_unix_sockets = requirements.dangerously_allow_all_unix_sockets

        managed_allowed_domains = _allowed_domains(requirements.domains)
        if hard_deny_allowlist_misses:
            managed_allowed_domains = managed_allowed_domains or []
        if managed_allowed_domains is not None:
            user_allowed = config.network.allowed_domains() or []
            effective_allowed = (
                NetworkProxySpec.merge_domain_lists(managed_allowed_domains, user_allowed)
                if allowlist_expansion_enabled
                else list(managed_allowed_domains)
            )
            user_denied = set(config.network.denied_domains() or [])
            config.network.set_allowed_domains([domain for domain in effective_allowed if normalize_host(domain) not in user_denied])
            constraints.allowed_domains = list(managed_allowed_domains)
            constraints.allowlist_expansion_enabled = allowlist_expansion_enabled

        managed_denied_domains = _denied_domains(requirements.domains)
        if managed_denied_domains is not None:
            user_denied = config.network.denied_domains() or []
            effective_denied = (
                NetworkProxySpec.merge_domain_lists(managed_denied_domains, user_denied)
                if denylist_expansion_enabled
                else list(managed_denied_domains)
            )
            config.network.set_denied_domains(effective_denied)
            constraints.denied_domains = list(managed_denied_domains)
            constraints.denylist_expansion_enabled = denylist_expansion_enabled

        if requirements.unix_sockets is not None:
            sockets = list(_string_tuple(requirements.unix_sockets, "network unix sockets"))
            config.network.set_allow_unix_sockets(sockets)
            constraints.allow_unix_sockets = sockets
        if requirements.allow_local_binding is not None:
            config.network.allow_local_binding = requirements.allow_local_binding
            constraints.allow_local_binding = requirements.allow_local_binding
        return config, constraints

    @staticmethod
    def allowlist_expansion_enabled(permission_profile: object, hard_deny_allowlist_misses: bool) -> bool:
        return NetworkProxySpec.managed_sandbox_active(permission_profile) and not hard_deny_allowlist_misses

    @staticmethod
    def managed_allowed_domains_only(requirements: NetworkConstraints) -> bool:
        return bool(requirements.managed_allowed_domains_only)

    @staticmethod
    def denylist_expansion_enabled(permission_profile: object) -> bool:
        return NetworkProxySpec.managed_sandbox_active(permission_profile)

    @staticmethod
    def managed_sandbox_active(permission_profile: object) -> bool:
        return getattr(permission_profile, "type", None) == "managed"

    @staticmethod
    def merge_domain_lists(managed: Sequence[str], user_entries: Sequence[str]) -> list[str]:
        merged = list(_string_tuple(managed, "managed domains"))
        for entry in _string_tuple(user_entries, "user domains"):
            if not any(existing.lower() == entry.lower() for existing in merged):
                merged.append(entry)
        return merged


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


def is_global_wildcard_domain_pattern(pattern: str) -> bool:
    return _is_global_wildcard_domain_pattern(pattern)


def compile_allowlist_globset(patterns: Sequence[str]) -> "DomainGlobSet":
    return _compile_globset_with_policy(patterns, allow_global_wildcard=True)


def compile_denylist_globset(patterns: Sequence[str]) -> "DomainGlobSet":
    return _compile_globset_with_policy(patterns, allow_global_wildcard=False)


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


async def ask_not_allowed_policy_decider(_request: object) -> str:
    return "ask:not_allowed"


async def evaluate_host_policy(
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
    request: NetworkPolicyRequest,
) -> NetworkDecision:
    host_blocked = getattr(state, "host_blocked", None)
    if not callable(host_blocked):
        raise TypeError("state must provide host_blocked(host, port)")
    host_decision = host_blocked(request.host, request.port)
    if inspect.isawaitable(host_decision):
        host_decision = await host_decision
    if not isinstance(host_decision, HostBlockDecision):
        raise TypeError("host_blocked must return HostBlockDecision")

    if host_decision.allowed:
        decision = NetworkDecision.allow()
        policy_override = False
    elif host_decision.reason is HostBlockReason.NOT_ALLOWED:
        if decider is not None:
            decider_decision = await _call_network_policy_decider(decider, request)
            decision = map_decider_decision(decider_decision)
            policy_override = decision.is_allow
        else:
            decision = NetworkDecision.deny_with_source(
                HostBlockReason.NOT_ALLOWED.as_str(),
                NetworkDecisionSource.BASELINE_POLICY,
            )
            policy_override = False
    else:
        reason = host_decision.reason or HostBlockReason.NOT_ALLOWED
        decision = NetworkDecision.deny_with_source(
            reason.as_str(),
            NetworkDecisionSource.BASELINE_POLICY,
        )
        policy_override = False

    if decision.is_allow:
        policy_decision = POLICY_DECISION_ALLOW
        source = NetworkDecisionSource.DECIDER if policy_override else NetworkDecisionSource.BASELINE_POLICY
        reason = HostBlockReason.NOT_ALLOWED.as_str() if policy_override else POLICY_REASON_ALLOW
    else:
        if decision.decision is None or decision.source is None or decision.reason is None:
            raise ValueError("deny network decision must carry decision, source, and reason")
        policy_decision = decision.decision.as_str()
        source = decision.source
        reason = decision.reason

    _emit_policy_audit_event(
        state,
        scope=POLICY_SCOPE_DOMAIN,
        decision=policy_decision,
        source=source.as_str(),
        reason=reason,
        protocol=request.protocol,
        server_address=request.host,
        server_port=request.port,
        method=request.method,
        client_addr=request.client_addr,
        policy_override=policy_override,
    )
    return decision


def emit_block_decision_audit_event(
    state: NetworkProxyState,
    args: BlockDecisionAuditEventArgs,
) -> None:
    _emit_non_domain_policy_decision_audit_event(state, args, POLICY_DECISION_DENY)


def emit_allow_decision_audit_event(
    state: NetworkProxyState,
    args: BlockDecisionAuditEventArgs,
) -> None:
    _emit_non_domain_policy_decision_audit_event(state, args, POLICY_DECISION_ALLOW)


def text_response(status: int, body: str) -> NetworkProxyResponse:
    return NetworkProxyResponse(
        status=int(status),
        body=str(body),
        headers={"content-type": "text/plain"},
    )


def json_response(value: object) -> NetworkProxyResponse:
    try:
        body = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        body = "{}"
    return NetworkProxyResponse(
        status=200,
        body=body,
        headers={"content-type": "application/json"},
    )


def blocked_header_value(reason: str) -> str:
    if reason in {REASON_NOT_ALLOWED, REASON_NOT_ALLOWED_LOCAL}:
        return "blocked-by-allowlist"
    if reason == REASON_DENIED:
        return "blocked-by-denylist"
    if reason == REASON_METHOD_NOT_ALLOWED:
        return "blocked-by-method-policy"
    if reason == REASON_MITM_HOOK_DENIED:
        return "blocked-by-mitm-hook"
    if reason == REASON_MITM_REQUIRED:
        return "blocked-by-mitm-required"
    return "blocked-by-policy"


def blocked_message(reason: str) -> str:
    if reason == REASON_NOT_ALLOWED:
        return "Domain not in allowlist."
    if reason == REASON_NOT_ALLOWED_LOCAL:
        return "Sandbox policy blocks local/private network addresses."
    if reason == REASON_DENIED:
        return "Domain denied by the sandbox policy."
    if reason == REASON_METHOD_NOT_ALLOWED:
        return "Method not allowed in limited mode."
    if reason == REASON_MITM_HOOK_DENIED:
        return "HTTPS request denied by MITM hook policy."
    if reason == REASON_MITM_REQUIRED:
        return "MITM required for limited HTTPS."
    if reason == REASON_PROXY_DISABLED:
        return "network proxy is disabled"
    return "Request blocked by network policy."


def blocked_text_response(reason: str) -> NetworkProxyResponse:
    return NetworkProxyResponse(
        status=403,
        body=blocked_message(reason),
        headers={
            "content-type": "text/plain",
            "x-proxy-error": blocked_header_value(reason),
        },
    )


def blocked_message_with_policy(reason: str, details: PolicyDecisionDetails) -> str:
    if not isinstance(details, PolicyDecisionDetails):
        raise TypeError("details must be PolicyDecisionDetails")
    return blocked_message(reason)


def blocked_text_response_with_policy(
    reason: str,
    details: PolicyDecisionDetails,
) -> NetworkProxyResponse:
    return NetworkProxyResponse(
        status=403,
        body=blocked_message_with_policy(reason, details),
        headers={
            "content-type": "text/plain",
            "x-proxy-error": blocked_header_value(reason),
        },
    )


def json_blocked(
    host: str,
    reason: str,
    details: PolicyDecisionDetails | None = None,
) -> NetworkProxyResponse:
    payload: dict[str, JsonValue] = {
        "status": "blocked",
        "host": host,
        "reason": reason,
    }
    if details is not None:
        payload["decision"] = details.decision.as_str()
        payload["source"] = details.source.as_str()
        payload["protocol"] = details.protocol.as_policy_protocol()
        payload["port"] = details.port
        payload["message"] = blocked_message_with_policy(reason, details)
    response = json_response(payload)
    return NetworkProxyResponse(
        status=403,
        body=response.body,
        headers={**dict(response.headers), "x-proxy-error": blocked_header_value(reason)},
    )


async def handle_socks5_tcp_policy(
    request: Socks5TcpRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> Socks5PolicyResult:
    host = normalize_host(_socks_request_host(request))
    port = _socks_request_port(request)
    client = _socks_request_client(request)
    if not host:
        raise ValueError("invalid host")

    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", None, details)
        raise policy_denied_error(REASON_PROXY_DISABLED, details)

    mode = await _network_proxy_state_network_mode(state)
    if mode is NetworkMode.LIMITED:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_METHOD_NOT_ALLOWED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", NetworkMode.LIMITED, details)
        raise policy_denied_error(REASON_METHOD_NOT_ALLOWED, details)

    if await state.host_has_mitm_hooks(host):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_MITM_REQUIRED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", NetworkMode.FULL, details)
        raise policy_denied_error(REASON_MITM_REQUIRED, details)

    decision = await evaluate_host_policy(
        state,
        decider,
        NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.SOCKS5_TCP,
                host=host,
                port=port,
                client_addr=client,
                method=None,
                command=None,
                exec_policy_hint=None,
            )
        ),
    )
    if not decision.is_allow:
        if decision.reason is None or decision.source is None or decision.decision is None:
            raise ValueError("deny network decision must carry decision, source, and reason")
        details = PolicyDecisionDetails(
            decision=decision.decision,
            reason=decision.reason,
            source=decision.source,
            protocol=NetworkProtocol.SOCKS5_TCP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5", None, details)
        raise policy_denied_error(decision.reason, details)

    return Socks5PolicyResult(protocol="socks5", host=host, port=port)


async def run_socks5_with_std_listener(
    state: NetworkProxyState,
    listener: socket.socket,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
    enable_socks5_udp: bool = False,
) -> None:
    listener.setblocking(False)
    server = await asyncio.start_server(
        lambda reader, writer: _handle_socks5_tcp_client(
            reader,
            writer,
            state,
            decider,
            enable_socks5_udp,
        ),
        sock=listener,
    )
    async with server:
        await server.serve_forever()


async def run_socks5(
    state: NetworkProxyState,
    addr: tuple[str, int],
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
    enable_socks5_udp: bool = False,
) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(addr)
    listener.listen()
    await run_socks5_with_std_listener(state, listener, decider, enable_socks5_udp)


async def _handle_socks5_tcp_client(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
    enable_socks5_udp: bool,
) -> None:
    udp_transport: asyncio.DatagramTransport | None = None
    try:
        greeting = await client_reader.readexactly(2)
        version, method_count = greeting[0], greeting[1]
        methods = await client_reader.readexactly(method_count)
        if version != 5 or 0 not in methods:
            client_writer.write(b"\x05\xff")
            await client_writer.drain()
            return
        client_writer.write(b"\x05\x00")
        await client_writer.drain()

        req_head = await client_reader.readexactly(4)
        version, command, _reserved, atyp = req_head
        if version != 5:
            await _write_socks5_reply(client_writer, 7)
            return
        host = await _read_socks5_address(client_reader, atyp)
        port = int.from_bytes(await client_reader.readexactly(2), "big")
        if command == 3:
            if not enable_socks5_udp:
                await _write_socks5_reply(client_writer, 7)
                return
            udp_transport = await _start_socks5_udp_relay(client_writer, state, decider)
            sockname = udp_transport.get_extra_info("sockname")
            if not isinstance(sockname, tuple) or len(sockname) < 2:
                await _write_socks5_reply(client_writer, 1)
                return
            await _write_socks5_reply(client_writer, 0, bound_addr=(str(sockname[0]), int(sockname[1])))
            await client_reader.read()
            return
        if command != 1:
            await _write_socks5_reply(client_writer, 7)
            return
        client = _stream_peer_addr(client_writer)
        try:
            await handle_socks5_tcp_policy(Socks5TcpRequest(host, port, client), state, decider)
        except (Socks5PolicyError, ValueError):
            await _write_socks5_reply(client_writer, 2)
            return

        try:
            target_reader, target_writer = await asyncio.open_connection(host, port)
        except OSError:
            await _write_socks5_reply(client_writer, 5)
            return
        await _write_socks5_reply(client_writer, 0, target_writer)
        await _relay_streams(client_reader, client_writer, target_reader, target_writer)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, OSError):
        return
    finally:
        if udp_transport is not None:
            udp_transport.close()
        if not client_writer.is_closing():
            await _close_stream_writer(client_writer)


async def _read_socks5_address(reader: asyncio.StreamReader, atyp: int) -> str:
    if atyp == 1:
        return str(ipaddress.IPv4Address(await reader.readexactly(4)))
    if atyp == 3:
        length = (await reader.readexactly(1))[0]
        return (await reader.readexactly(length)).decode("idna")
    if atyp == 4:
        return str(ipaddress.IPv6Address(await reader.readexactly(16)))
    raise ValueError("unsupported SOCKS5 address type")


async def _write_socks5_reply(
    writer: asyncio.StreamWriter,
    code: int,
    target_writer: asyncio.StreamWriter | None = None,
    bound_addr: tuple[str, int] | None = None,
) -> None:
    sockname = target_writer.get_extra_info("sockname") if target_writer is not None else None
    host = "0.0.0.0"
    port = 0
    if bound_addr is not None:
        host, port = bound_addr
    elif isinstance(sockname, tuple) and len(sockname) >= 2:
        host = str(sockname[0])
        port = int(sockname[1])
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = ipaddress.ip_address("0.0.0.0")
    if isinstance(address, ipaddress.IPv6Address):
        payload = b"\x05" + bytes([code]) + b"\x00\x04" + address.packed
    else:
        payload = b"\x05" + bytes([code]) + b"\x00\x01" + address.packed
    payload += int(port).to_bytes(2, "big")
    writer.write(payload)
    await writer.drain()


async def _start_socks5_udp_relay(
    client_writer: asyncio.StreamWriter,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
) -> asyncio.DatagramTransport:
    loop = asyncio.get_running_loop()
    peer = client_writer.get_extra_info("peername")
    allowed_client = str(peer[0]) if isinstance(peer, tuple) and len(peer) >= 1 else None
    bind_host = "127.0.0.1"
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _Socks5UdpRelayProtocol(state, decider, allowed_client),
        local_addr=(bind_host, 0),
    )
    return transport


class _Socks5UdpRelayProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        state: NetworkProxyState,
        decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
        allowed_client: str | None,
    ) -> None:
        self.state = state
        self.decider = decider
        self.allowed_client = allowed_client
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport if isinstance(transport, asyncio.DatagramTransport) else None

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.allowed_client is not None and addr[0] != self.allowed_client:
            return
        asyncio.create_task(self._relay_datagram(data, addr))

    async def _relay_datagram(self, data: bytes, client_addr: tuple[str, int]) -> None:
        if self.transport is None:
            return
        try:
            host, port, payload = _parse_socks5_udp_packet(data)
            result = await inspect_socks5_udp_policy(
                Socks5UdpRequest(host, port, payload, f"{client_addr[0]}:{client_addr[1]}"),
                self.state,
                self.decider,
            )
            response = await _udp_round_trip(result.host, result.port, result.payload or b"")
        except (OSError, ValueError, Socks5PolicyError):
            return
        self.transport.sendto(_build_socks5_udp_packet(host, port, response), client_addr)


def _parse_socks5_udp_packet(data: bytes) -> tuple[str, int, bytes]:
    if len(data) < 4 or data[0:2] != b"\x00\x00" or data[2] != 0:
        raise ValueError("unsupported SOCKS5 UDP packet")
    atyp = data[3]
    index = 4
    if atyp == 1:
        if len(data) < index + 4 + 2:
            raise ValueError("truncated SOCKS5 IPv4 UDP packet")
        host = str(ipaddress.IPv4Address(data[index : index + 4]))
        index += 4
    elif atyp == 3:
        if len(data) < index + 1:
            raise ValueError("truncated SOCKS5 domain UDP packet")
        length = data[index]
        index += 1
        if len(data) < index + length + 2:
            raise ValueError("truncated SOCKS5 domain UDP packet")
        host = data[index : index + length].decode("idna")
        index += length
    elif atyp == 4:
        if len(data) < index + 16 + 2:
            raise ValueError("truncated SOCKS5 IPv6 UDP packet")
        host = str(ipaddress.IPv6Address(data[index : index + 16]))
        index += 16
    else:
        raise ValueError("unsupported SOCKS5 UDP address type")
    port = int.from_bytes(data[index : index + 2], "big")
    index += 2
    return host, port, data[index:]


def _build_socks5_udp_packet(host: str, port: int, payload: bytes) -> bytes:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        encoded = host.encode("idna")
        if len(encoded) > 255:
            raise ValueError("SOCKS5 domain address too long")
        return b"\x00\x00\x00\x03" + bytes([len(encoded)]) + encoded + int(port).to_bytes(2, "big") + payload
    if isinstance(address, ipaddress.IPv6Address):
        return b"\x00\x00\x00\x04" + address.packed + int(port).to_bytes(2, "big") + payload
    return b"\x00\x00\x00\x01" + address.packed + int(port).to_bytes(2, "big") + payload


async def _udp_round_trip(host: str, port: int, payload: bytes) -> bytes:
    loop = asyncio.get_running_loop()
    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    try:
        await loop.sock_sendto(sock, payload, (host, port))
        response, _ = await asyncio.wait_for(loop.sock_recvfrom(sock, 65535), timeout=5)
        return response
    finally:
        sock.close()


async def _relay_streams(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_reader: asyncio.StreamReader,
    target_writer: asyncio.StreamWriter,
) -> None:
    async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        finally:
            await _close_stream_writer(writer)

    await asyncio.gather(
        pipe(client_reader, target_writer),
        pipe(target_reader, client_writer),
        return_exceptions=True,
    )


async def inspect_socks5_udp_policy(
    request: Socks5UdpRequest | Mapping[str, object] | object,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None = None,
) -> Socks5PolicyResult:
    host = normalize_host(_socks_request_host(request))
    port = _socks_request_port(request)
    client = _socks_request_client(request)
    payload = _socks_udp_payload(request)
    if not host:
        raise ValueError("invalid host")

    if not await _network_proxy_state_enabled(state):
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_PROXY_DISABLED,
            source=NetworkDecisionSource.PROXY_STATE,
            protocol=NetworkProtocol.SOCKS5_UDP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5-udp", None, details)
        raise policy_denied_error(REASON_PROXY_DISABLED, details)

    mode = await _network_proxy_state_network_mode(state)
    if mode is NetworkMode.LIMITED:
        details = PolicyDecisionDetails(
            decision=NetworkPolicyDecision.DENY,
            reason=REASON_METHOD_NOT_ALLOWED,
            source=NetworkDecisionSource.MODE_GUARD,
            protocol=NetworkProtocol.SOCKS5_UDP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5-udp", NetworkMode.LIMITED, details)
        raise policy_denied_error(REASON_METHOD_NOT_ALLOWED, details)

    decision = await evaluate_host_policy(
        state,
        decider,
        NetworkPolicyRequest.new(
            NetworkPolicyRequestArgs(
                protocol=NetworkProtocol.SOCKS5_UDP,
                host=host,
                port=port,
                client_addr=client,
                method=None,
                command=None,
                exec_policy_hint=None,
            )
        ),
    )
    if not decision.is_allow:
        if decision.reason is None or decision.source is None or decision.decision is None:
            raise ValueError("deny network decision must carry decision, source, and reason")
        details = PolicyDecisionDetails(
            decision=decision.decision,
            reason=decision.reason,
            source=decision.source,
            protocol=NetworkProtocol.SOCKS5_UDP,
            host=host,
            port=port,
        )
        await _record_socks_blocked(state, host, port, client, "socks5-udp", None, details)
        raise policy_denied_error(decision.reason, details)

    return Socks5PolicyResult(protocol="socks5-udp", host=host, port=port, payload=payload)


def emit_socks_block_decision_audit_event(
    state: NetworkProxyState,
    source: NetworkDecisionSource | str,
    reason: str,
    protocol: NetworkProtocol | str,
    host: str,
    port: int,
    client_addr: str | None = None,
) -> None:
    emit_block_decision_audit_event(
        state,
        BlockDecisionAuditEventArgs(
            source=NetworkDecisionSource(source),
            reason=reason,
            protocol=NetworkProtocol(protocol),
            server_address=host,
            server_port=port,
            method=None,
            client_addr=client_addr,
        ),
    )


def policy_denied_error(reason: str, details: PolicyDecisionDetails) -> Socks5PolicyError:
    return Socks5PolicyError(reason, details)


def managed_ca_paths(codex_home: str | os.PathLike[str] | None = None) -> ManagedMitmCaPaths:
    if codex_home is None:
        home = os.environ.get("CODEX_HOME")
        if not home:
            home = str(Path.home() / ".codex")
        codex_home_path = Path(home)
    else:
        codex_home_path = Path(codex_home)
    proxy_dir = codex_home_path / MANAGED_MITM_CA_DIR
    return ManagedMitmCaPaths(
        cert_path=proxy_dir / MANAGED_MITM_CA_CERT,
        key_path=proxy_dir / MANAGED_MITM_CA_KEY,
    )


def validate_existing_ca_key_file(path: str | os.PathLike[str], *, unix: bool | None = None) -> None:
    check_unix = (os.name == "posix") if unix is None else bool(unix)
    if not check_unix:
        return

    key_path = Path(path)
    try:
        metadata = os.lstat(key_path)
    except OSError as exc:
        raise OSError(f"failed to stat CA key {key_path}") from exc

    if stat.S_ISLNK(metadata.st_mode):
        raise ValueError(f"refusing to use symlink for managed MITM CA key {key_path}")
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"managed MITM CA key is not a regular file: {key_path}")

    mode = stat.S_IMODE(metadata.st_mode) & 0o777
    if mode & 0o077:
        raise PermissionError(
            f"managed MITM CA key {key_path} must not be group/world accessible "
            f"(mode={mode:o}; expected <= 600)"
        )


def write_atomic_create_new(path: str | os.PathLike[str], contents: bytes | str, mode: int = 0o600) -> None:
    target = Path(path)
    parent = target.parent
    if str(parent) in {"", "."}:
        raise ValueError("missing parent directory")
    if not parent.exists():
        raise FileNotFoundError(parent)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing file {target}")

    payload = contents.encode() if isinstance(contents, str) else bytes(contents)
    nanos = time.time_ns()
    pid = os.getpid()
    tmp_path = parent / f".{target.name}.tmp.{pid}.{nanos}"
    fd: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(tmp_path, flags, mode)
        with os.fdopen(fd, "wb") as file:
            fd = None
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        try:
            os.link(tmp_path, target)
            tmp_path.unlink()
        except FileExistsError:
            tmp_path.unlink(missing_ok=True)
            raise FileExistsError(f"refusing to overwrite existing file {target}")
        except OSError:
            if target.exists() or target.is_symlink():
                tmp_path.unlink(missing_ok=True)
                raise FileExistsError(f"refusing to overwrite existing file {target}")
            tmp_path.replace(target)
        try:
            dir_fd = os.open(parent, os.O_RDONLY)
        except OSError:
            dir_fd = None
        if dir_fd is not None:
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
    except Exception:
        if fd is not None:
            os.close(fd)
        tmp_path.unlink(missing_ok=True)
        raise


async def _record_socks_blocked(
    state: NetworkProxyState,
    host: str,
    port: int,
    client: str | None,
    protocol_name: str,
    mode: NetworkMode | None,
    details: PolicyDecisionDetails,
) -> None:
    emit_socks_block_decision_audit_event(
        state,
        details.source,
        details.reason,
        details.protocol,
        host,
        port,
        client,
    )
    await state.record_blocked(
        BlockedRequest.new(
            BlockedRequestArgs(
                host=host,
                reason=details.reason,
                client=client,
                method=None,
                mode=mode,
                protocol=protocol_name,
                decision=details.decision.as_str(),
                source=details.source.as_str(),
                port=port,
            )
        )
    )


def map_decider_decision(decision: NetworkDecision) -> NetworkDecision:
    if not isinstance(decision, NetworkDecision):
        raise TypeError("decider must return NetworkDecision")
    if decision.is_allow:
        return decision
    if decision.reason is None or decision.decision is None:
        raise ValueError("deny network decision must carry reason and decision")
    return NetworkDecision(
        "deny",
        decision.reason,
        NetworkDecisionSource.DECIDER,
        decision.decision,
    )


async def _call_network_policy_decider(
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object,
    request: NetworkPolicyRequest,
) -> NetworkDecision:
    decide = getattr(decider, "decide", None)
    result = decide(request) if callable(decide) else decider(request)  # type: ignore[operator]
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, NetworkDecision):
        raise TypeError("decider must return NetworkDecision")
    return result


def _emit_non_domain_policy_decision_audit_event(
    state: NetworkProxyState,
    args: BlockDecisionAuditEventArgs,
    decision: str,
) -> None:
    _emit_policy_audit_event(
        state,
        scope=POLICY_SCOPE_NON_DOMAIN,
        decision=decision,
        source=NetworkDecisionSource(args.source).as_str(),
        reason=args.reason,
        protocol=NetworkProtocol(args.protocol),
        server_address=args.server_address,
        server_port=args.server_port,
        method=args.method,
        client_addr=args.client_addr,
        policy_override=False,
    )


def _emit_policy_audit_event(
    state: NetworkProxyState,
    *,
    scope: str,
    decision: str,
    source: str,
    reason: str,
    protocol: NetworkProtocol,
    server_address: str,
    server_port: int,
    method: str | None,
    client_addr: str | None,
    policy_override: bool,
) -> None:
    event: dict[str, str] = {
        "target": AUDIT_TARGET,
        "event.name": POLICY_DECISION_EVENT_NAME,
        "event.timestamp": _audit_timestamp(),
        "network.policy.scope": scope,
        "network.policy.decision": decision,
        "network.policy.source": source,
        "network.policy.reason": reason,
        "network.transport.protocol": NetworkProtocol(protocol).as_policy_protocol(),
        "server.address": server_address,
        "server.port": str(server_port),
        "http.request.method": method or DEFAULT_METHOD,
        "client.address": client_addr or DEFAULT_CLIENT_ADDRESS,
        "network.policy.override": str(policy_override).lower(),
    }
    metadata = _audit_metadata_mapping(getattr(state, "audit_metadata", None))
    for source_key, event_key in (
        ("conversation_id", "conversation.id"),
        ("app_version", "app.version"),
        ("auth_mode", "auth_mode"),
        ("originator", "originator"),
        ("user_account_id", "user.account_id"),
        ("user_email", "user.email"),
        ("terminal_type", "terminal.type"),
        ("model", "model"),
        ("slug", "slug"),
    ):
        value = metadata.get(source_key)
        if value is not None:
            event[event_key] = str(value)

    record = getattr(state, "record_audit_event", None)
    if callable(record):
        record(event)
        return
    events = getattr(state, "audit_events", None)
    if events is not None:
        events.append(event)


def _audit_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _audit_metadata_mapping(metadata: object) -> Mapping[str, JsonValue]:
    if metadata is None:
        return {}
    if isinstance(metadata, NetworkProxyAuditMetadata):
        return metadata.value
    if isinstance(metadata, Mapping):
        return metadata
    return {
        key: value
        for key in (
            "conversation_id",
            "app_version",
            "auth_mode",
            "originator",
            "user_account_id",
            "user_email",
            "terminal_type",
            "model",
            "slug",
        )
        if (value := getattr(metadata, key, None)) is not None
    }


def apply_network_constraints(network: NetworkToml, constraints: NetworkProxyConstraints) -> None:
    if not isinstance(network, NetworkToml):
        raise TypeError("network must be NetworkToml")
    if not isinstance(constraints, NetworkProxyConstraints):
        raise TypeError("constraints must be NetworkProxyConstraints")
    if network.enabled is not None:
        constraints.enabled = network.enabled
    if network.mode is not None:
        constraints.mode = network.mode
    if network.allow_upstream_proxy is not None:
        constraints.allow_upstream_proxy = network.allow_upstream_proxy
    if network.dangerously_allow_non_loopback_proxy is not None:
        constraints.dangerously_allow_non_loopback_proxy = network.dangerously_allow_non_loopback_proxy
    if network.dangerously_allow_all_unix_sockets is not None:
        constraints.dangerously_allow_all_unix_sockets = network.dangerously_allow_all_unix_sockets
    if network.domains is not None:
        config = NetworkProxyConfig()
        config.network.set_allowed_domains(constraints.allowed_domains)
        config.network.set_denied_domains(constraints.denied_domains)
        overlay_network_domain_permissions(config, network.domains)
        constraints.allowed_domains = config.network.allowed_domains()
        constraints.denied_domains = config.network.denied_domains()
    if network.unix_sockets is not None:
        constraints.allow_unix_sockets = tuple(network.unix_sockets)  # type: ignore[assignment]
    if network.allow_local_binding is not None:
        constraints.allow_local_binding = network.allow_local_binding


def network_tables_from_toml(value: Mapping[str, JsonValue]) -> NetworkTablesToml:
    if not isinstance(value, Mapping):
        raise TypeError("value must be a mapping")
    default_permissions = value.get("default_permissions")
    if default_permissions is not None and not isinstance(default_permissions, str):
        raise TypeError("default_permissions must be a string")
    permissions = value.get("permissions")
    if permissions is not None and not isinstance(permissions, Mapping):
        raise TypeError("permissions must be a mapping")
    return NetworkTablesToml(default_permissions, permissions)  # type: ignore[arg-type]


def selected_network_from_tables(parsed: NetworkTablesToml) -> NetworkToml | None:
    if not isinstance(parsed, NetworkTablesToml):
        raise TypeError("parsed must be NetworkTablesToml")
    if parsed.default_permissions is None:
        return None
    if _is_builtin_permission_profile_name(parsed.default_permissions):
        return None
    _reject_unknown_builtin_permission_profile(parsed.default_permissions)
    if parsed.permissions is None:
        raise ValueError("default_permissions requires a `[permissions]` table for network settings")
    profile = _resolve_permission_profile(parsed.permissions, parsed.default_permissions)
    return _network_from_mapping(profile.get("network"))


def apply_network_tables(config: NetworkProxyConfig, parsed: NetworkTablesToml) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    network = selected_network_from_tables(parsed)
    if network is not None:
        _apply_network_to_config(config, network)


def config_from_layers(
    layers: Sequence[ConfigLayerEntry],
    exec_policy: object | None = None,
) -> NetworkProxyConfig:
    if isinstance(layers, ConfigLayerEntry) or not isinstance(layers, Sequence):
        raise TypeError("layers must be a sequence of ConfigLayerEntry")
    merged: dict[str, JsonValue] = {}
    for layer in layers:
        if not isinstance(layer, ConfigLayerEntry):
            raise TypeError("layers must contain ConfigLayerEntry values")
        if layer.enabled:
            _deep_merge_mapping(merged, layer.config)
    config = NetworkProxyConfig()
    apply_network_tables(config, network_tables_from_toml(merged))
    if exec_policy is not None:
        apply_exec_policy_network_rules(config, exec_policy)
    return config


async def build_network_proxy_state(
    layers: Sequence[ConfigLayerEntry] | None = None,
    exec_policy: object | None = None,
    *,
    config_layers_loader: ConfigLayersLoader | None = None,
) -> NetworkProxyState:
    state, reloader = await build_network_proxy_state_and_reloader(
        layers,
        exec_policy,
        config_layers_loader=config_layers_loader,
    )
    return NetworkProxyState(state, reloader)


async def build_network_proxy_state_and_reloader(
    layers: Sequence[ConfigLayerEntry] | None = None,
    exec_policy: object | None = None,
    *,
    config_layers_loader: ConfigLayersLoader | None = None,
) -> tuple[ConfigState, MtimeConfigReloader]:
    if layers is None:
        if config_layers_loader is None:
            raise ValueError("layers or config_layers_loader must be provided")
        loaded_layers = config_layers_loader()
        if inspect.isawaitable(loaded_layers):
            loaded_layers = await loaded_layers
        layers = loaded_layers
    if isinstance(layers, ConfigLayerEntry) or not isinstance(layers, Sequence):
        raise TypeError("layers must be a sequence of ConfigLayerEntry")
    config = config_from_layers(layers, exec_policy)
    constraints = network_constraints_from_trusted_layers(layers)
    state = ConfigState(config, constraints)
    return state, MtimeConfigReloader(collect_layer_mtimes(layers))


def network_constraints_from_trusted_layers(layers: Sequence[ConfigLayerEntry]) -> NetworkProxyConstraints:
    if isinstance(layers, ConfigLayerEntry) or not isinstance(layers, Sequence):
        raise TypeError("layers must be a sequence of ConfigLayerEntry")
    merged: dict[str, JsonValue] = {}
    for layer in layers:
        if not isinstance(layer, ConfigLayerEntry):
            raise TypeError("layers must contain ConfigLayerEntry values")
        if layer.enabled and not is_user_controlled_layer(layer.name):
            _deep_merge_mapping(merged, layer.config)
    constraints = NetworkProxyConstraints()
    network = selected_network_from_tables(network_tables_from_toml(merged))
    if network is not None:
        apply_network_constraints(network, constraints)
    return constraints


def overlay_network_domain_permissions(
    config: NetworkProxyConfig,
    domains: Mapping[str, str | NetworkDomainPermission],
) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    if not isinstance(domains, Mapping):
        raise TypeError("domains must be a mapping")
    for host, permission in domains.items():
        config.network.upsert_domain_permission(host, NetworkDomainPermission(permission))


def apply_exec_policy_network_rules(config: NetworkProxyConfig, exec_policy: object) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    allowed_domains, denied_domains = _compiled_network_domains(exec_policy)
    for host in allowed_domains:
        upsert_network_domain(config, host, NetworkDomainPermission.ALLOW)
    for host in denied_domains:
        upsert_network_domain(config, host, NetworkDomainPermission.DENY)


def upsert_network_domain(
    config: NetworkProxyConfig,
    host: str,
    permission: NetworkDomainPermission,
) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    config.network.upsert_domain_permission(host, permission)


def collect_layer_mtimes(layers: Sequence[ConfigLayerEntry]) -> list[LayerMtime]:
    if isinstance(layers, ConfigLayerEntry) or not isinstance(layers, Sequence):
        raise TypeError("layers must be a sequence of ConfigLayerEntry")
    mtimes: list[LayerMtime] = []
    for layer in layers:
        if not isinstance(layer, ConfigLayerEntry):
            raise TypeError("layers must contain ConfigLayerEntry values")
        if not layer.enabled:
            continue
        path = _layer_config_path(layer.name)
        if path is not None:
            mtimes.append(LayerMtime.new(path))
    return mtimes


def is_user_controlled_layer(layer: ConfigLayerSource) -> bool:
    if not isinstance(layer, ConfigLayerSource):
        raise TypeError("layer must be ConfigLayerSource")
    return layer.type in {"user", "project", "session_flags"}


def _layer_config_path(layer: ConfigLayerSource) -> Path | None:
    if layer.type in {"system", "user", "legacy_managed_config_toml_from_file"}:
        return layer.file
    if layer.type == "project" and layer.dot_codex_folder is not None:
        return layer.dot_codex_folder / "config.toml"
    return None


def _compiled_network_domains(exec_policy: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    from pycodex.execpolicy import Decision

    method = getattr(exec_policy, "compiled_network_domains", None)
    if callable(method):
        allowed, denied = method()
        return _string_tuple(allowed, "allowed domains"), _string_tuple(denied, "denied domains")
    if isinstance(exec_policy, Mapping):
        allowed = exec_policy.get("allow", exec_policy.get("allowed", ()))
        denied = exec_policy.get("deny", exec_policy.get("denied", ()))
        return _string_tuple(allowed, "allowed domains"), _string_tuple(denied, "denied domains")
    rules = getattr(exec_policy, "network_rules", None)
    if rules is not None:
        allowed_hosts: list[str] = []
        denied_hosts: list[str] = []
        for rule in rules:
            host = getattr(rule, "host", None)
            decision = getattr(rule, "decision", None)
            if not isinstance(host, str):
                continue
            if decision in {Decision.ALLOW, "allow"}:
                allowed_hosts.append(host)
            elif decision in {Decision.FORBIDDEN, "forbidden", "deny"}:
                denied_hosts.append(host)
        return tuple(allowed_hosts), tuple(denied_hosts)
    raise TypeError("exec_policy must expose compiled_network_domains, mapping domains, or network_rules")


def _allowed_domains(domains: Mapping[str, str | NetworkDomainPermission] | None) -> list[str] | None:
    if domains is None:
        return None
    allowed = [
        normalize_host(host)
        for host, permission in domains.items()
        if NetworkDomainPermission(permission) is NetworkDomainPermission.ALLOW
    ]
    return allowed or None


def _denied_domains(domains: Mapping[str, str | NetworkDomainPermission] | None) -> list[str] | None:
    if domains is None:
        return None
    denied = [
        normalize_host(host)
        for host, permission in domains.items()
        if NetworkDomainPermission(permission) is NetworkDomainPermission.DENY
    ]
    return denied or None


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


def _is_loopback_host(host: str) -> bool:
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _validate_unix_socket_allowlist_paths(config: NetworkProxyConfig) -> None:
    for index, socket_path in enumerate(config.network.allow_unix_sockets_effective()):
        if not isinstance(socket_path, str):
            raise TypeError("network.allow_unix_sockets entries must be strings")
        path = Path(socket_path)
        if not path.is_absolute() and not socket_path.startswith("/"):
            raise ValueError(f"invalid network.allow_unix_sockets[{index}]: expected an absolute path, got {socket_path!r}")


def _unix_socket_permissions_supported() -> bool:
    return os.name == "posix" and getattr(os, "uname", lambda: None)() is not None and os.uname().sysname == "Darwin"


def _canonical_path_or_none(path: Path) -> Path | None:
    try:
        return path.resolve(strict=True)
    except OSError:
        return None


def _validate_mitm_hook_config(config: NetworkProxyConfig) -> None:
    try:
        validate_mitm_hook_config(config)
    except (TypeError, ValueError) as exc:
        raise NetworkProxyConstraintError(
            "network.mitm_hooks",
            str(exc),
            "valid MITM hook configuration",
        ) from exc


def validate_mitm_hook_config(config: NetworkProxyConfig) -> None:
    hooks = [_coerce_mitm_hook_config(hook) for hook in config.network.mitm_hooks]
    if not hooks:
        return
    if not config.network.mitm:
        raise ValueError("network.mitm_hooks requires network.mitm = true")
    for hook_index, hook in enumerate(hooks):
        try:
            host = _normalize_hook_host(hook.host)
            methods = _normalize_methods(hook.matcher.methods)
            if not methods:
                raise ValueError(f"network.mitm_hooks[{hook_index}].match.methods must not be empty")
            path_prefixes = _compile_path_matchers(hook.matcher.path_prefixes)
            if not path_prefixes:
                raise ValueError(f"network.mitm_hooks[{hook_index}].match.path_prefixes must not be empty")
            if hook.matcher.body is not None:
                raise ValueError(
                    f"network.mitm_hooks[{hook_index}].match.body is reserved for a future release and is not yet supported"
                )
            _validate_query_constraints(hook.matcher.query)
            _validate_header_constraints(hook.matcher.headers)
            _validate_strip_request_headers(hook.actions.strip_request_headers)
            _validate_injected_headers(hook.actions.inject_request_headers)
            if not host:
                raise ValueError(f"network.mitm_hooks[{hook_index}].host must not be empty")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid network.mitm_hooks[{hook_index}]: {exc}") from exc


def compile_mitm_hooks(config: NetworkProxyConfig) -> dict[str, list[MitmHook]]:
    return compile_mitm_hooks_with_resolvers(
        config,
        resolve_env_var=lambda name: os.environ.get(name),
        read_secret_file=lambda path: Path(path).read_text(encoding="utf-8").strip(),
    )


def compile_mitm_hooks_with_resolvers(
    config: NetworkProxyConfig,
    resolve_env_var: Callable[[str], str | None],
    read_secret_file: Callable[[str], str],
) -> dict[str, list[MitmHook]]:
    validate_mitm_hook_config(config)
    hooks_by_host: dict[str, list[MitmHook]] = {}
    for raw_hook in config.network.mitm_hooks:
        hook = _coerce_mitm_hook_config(raw_hook)
        host = _normalize_hook_host(hook.host)
        query = tuple(
            QueryConstraint(_normalize_query_name(name), tuple(_compile_value_matchers(values)))
            for name, values in hook.matcher.query.items()
        )
        headers = tuple(
            HeaderConstraint(_parse_header_name(name), tuple(_compile_value_matchers(values)))
            for name, values in hook.matcher.headers.items()
        )
        actions = MitmHookActions(
            strip_request_headers=tuple(_parse_header_name(name) for name in hook.actions.strip_request_headers),
            inject_request_headers=tuple(
                _compile_injected_header(header, resolve_env_var, read_secret_file)
                for header in hook.actions.inject_request_headers
            ),
        )
        compiled = MitmHook(
            host=host,
            matcher=MitmHookMatcher(
                methods=tuple(_normalize_methods(hook.matcher.methods)),
                path_prefixes=tuple(_compile_path_matchers(hook.matcher.path_prefixes)),
                query=query,
                headers=headers,
                body=None,
            ),
            actions=actions,
        )
        hooks_by_host.setdefault(host, []).append(compiled)
    return hooks_by_host


def evaluate_mitm_hooks(
    hooks_by_host: Mapping[str, Sequence[MitmHook]],
    host: str,
    request: Any,
) -> MitmHookEvaluation:
    hooks = hooks_by_host.get(normalize_host(host))
    if hooks is None:
        return MitmHookEvaluation.no_hooks_for_host()
    for hook in hooks:
        if _mitm_hook_matches(hook, request):
            return MitmHookEvaluation.matched(hook.actions)
    return MitmHookEvaluation.hooked_host_no_match()


async def mitm_blocking_response(request: Any, policy: MitmPolicyContext) -> NetworkProxyResponse | None:
    decision = await evaluate_mitm_policy(request, policy)
    return None if decision.allowed else decision.response


async def evaluate_mitm_policy(request: Any, policy: MitmPolicyContext) -> MitmPolicyDecision:
    method = _request_method(request).upper()
    if method == "CONNECT":
        return MitmPolicyDecision.block(text_response(405, "CONNECT not supported inside MITM"))

    log_path = _request_log_path(request)
    client = _request_client(request)
    request_host = _extract_request_host(request)
    if request_host is not None:
        normalized = normalize_host(request_host)
        if normalized and normalized != policy.target_host:
            return MitmPolicyDecision.block(text_response(400, "host mismatch"))

    host_decision = await policy.app_state.host_blocked(policy.target_host, policy.target_port)
    if host_decision.reason is HostBlockReason.NOT_ALLOWED_LOCAL:
        reason = HostBlockReason.NOT_ALLOWED_LOCAL.as_str()
        await policy.app_state.record_blocked(
            BlockedRequest.new(
                BlockedRequestArgs(
                    host=policy.target_host,
                    reason=reason,
                    client=client,
                    method=method,
                    mode=policy.mode,
                    protocol="https",
                    decision=None,
                    source=None,
                    port=policy.target_port,
                )
            )
        )
        return MitmPolicyDecision.block(blocked_text_response(reason))

    hook_evaluation = await policy.app_state.evaluate_mitm_hook_request(policy.target_host, request)
    hook_actions = None
    if hook_evaluation.kind is HookEvaluation.MATCHED:
        hook_actions = hook_evaluation.actions
    elif hook_evaluation.kind is HookEvaluation.HOOKED_HOST_NO_MATCH:
        await policy.app_state.record_blocked(
            BlockedRequest.new(
                BlockedRequestArgs(
                    host=policy.target_host,
                    reason=REASON_MITM_HOOK_DENIED,
                    client=client,
                    method=method,
                    mode=policy.mode,
                    protocol="https",
                    decision=None,
                    source=None,
                    port=policy.target_port,
                )
            )
        )
        return MitmPolicyDecision.block(blocked_text_response(REASON_MITM_HOOK_DENIED))

    if not policy.mode.allows_method(method):
        await policy.app_state.record_blocked(
            BlockedRequest.new(
                BlockedRequestArgs(
                    host=policy.target_host,
                    reason=REASON_METHOD_NOT_ALLOWED,
                    client=client,
                    method=method,
                    mode=policy.mode,
                    protocol="https",
                    decision=None,
                    source=None,
                    port=policy.target_port,
                )
            )
        )
        return MitmPolicyDecision.block(blocked_text_response(REASON_METHOD_NOT_ALLOWED))

    return MitmPolicyDecision.allow(hook_actions)


def apply_mitm_hook_actions(headers: MutableMapping[str, Any], actions: MitmHookActions | None) -> MutableMapping[str, Any]:
    if actions is None:
        return headers
    for header_name in actions.strip_request_headers:
        _remove_header_case_insensitive(headers, header_name)
    for injected_header in actions.inject_request_headers:
        _remove_header_case_insensitive(headers, injected_header.name)
        headers[injected_header.name] = injected_header.value
    return headers


def _compile_injected_header(
    header: InjectedHeaderConfig,
    resolve_env_var: Callable[[str], str | None],
    read_secret_file: Callable[[str], str],
) -> ResolvedInjectedHeader:
    name = _parse_header_name(header.name)
    if header.secret_env_var is not None and header.secret_file is None:
        secret = resolve_env_var(header.secret_env_var)
        if secret is None:
            raise ValueError(f"missing required environment variable {header.secret_env_var}")
        source = SecretSource.env_var(header.secret_env_var)
    elif header.secret_env_var is None and header.secret_file is not None:
        path = _parse_secret_file(header.secret_file)
        secret = read_secret_file(path)
        source = SecretSource.file(path)
    else:
        raise ValueError("expected exactly one of secret_env_var or secret_file")
    prefix = header.prefix or ""
    value = f"{prefix}{secret}"
    _validate_header_value(value, f"invalid value for injected header {header.name}")
    return ResolvedInjectedHeader(name=name, value=value, source=source)


def _mitm_hook_matches(hook: MitmHook, request: Any) -> bool:
    method = _request_method(request).upper()
    if method not in hook.matcher.methods:
        return False
    uri = _request_uri(request)
    parsed = urlparse(uri)
    path = parsed.path or uri.split("?", 1)[0] or "/"
    if not any(matcher.matches(path) for matcher in hook.matcher.path_prefixes):
        return False
    if not _mitm_query_matches(hook.matcher.query, parsed.query):
        return False
    return _mitm_headers_match(hook.matcher.headers, _request_headers(request))


def _mitm_query_matches(query_constraints: Sequence[QueryConstraint], raw_query: str) -> bool:
    if not query_constraints:
        return True
    actual_values: dict[str, list[str]] = {}
    for name, value in parse_qsl(raw_query, keep_blank_values=True):
        actual_values.setdefault(name, []).append(value)
    for constraint in query_constraints:
        actual = actual_values.get(constraint.name)
        if not actual:
            return False
        if not any(allowed.matches(candidate) for candidate in actual for allowed in constraint.allowed_values):
            return False
    return True


def _mitm_headers_match(header_constraints: Sequence[HeaderConstraint], headers: Mapping[str, Any]) -> bool:
    normalized: dict[str, list[str]] = {}
    for name, raw_value in headers.items():
        values = raw_value if isinstance(raw_value, list | tuple) else [raw_value]
        normalized.setdefault(name.lower(), []).extend(str(value) for value in values)
    for constraint in header_constraints:
        actual = normalized.get(constraint.name.lower())
        if not actual:
            return False
        if not constraint.allowed_values:
            continue
        if not any(allowed.matches(candidate) for candidate in actual for allowed in constraint.allowed_values):
            return False
    return True


def _coerce_mitm_hook_config(value: Any) -> MitmHookConfig:
    if isinstance(value, MitmHookConfig):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("MITM hook entries must be objects")
    matcher_value = value.get("match", value.get("matcher", {})) or {}
    actions_value = value.get("actions", {}) or {}
    if not isinstance(matcher_value, Mapping):
        raise TypeError("MITM hook match must be an object")
    if not isinstance(actions_value, Mapping):
        raise TypeError("MITM hook actions must be an object")
    injected = actions_value.get("inject_request_headers", []) or []
    if isinstance(injected, str) or not isinstance(injected, Sequence):
        raise TypeError("inject_request_headers must be a sequence")
    return MitmHookConfig(
        host=str(value.get("host", "")),
        matcher=MitmHookMatchConfig(
            methods=list(_string_tuple(matcher_value.get("methods", []), "methods")),
            path_prefixes=list(_string_tuple(matcher_value.get("path_prefixes", []), "path_prefixes")),
            query=_coerce_string_list_mapping(matcher_value.get("query", {}), "query"),
            headers=_coerce_string_list_mapping(matcher_value.get("headers", {}), "headers"),
            body=matcher_value.get("body"),
        ),
        actions=MitmHookActionsConfig(
            strip_request_headers=list(
                _string_tuple(actions_value.get("strip_request_headers", []), "strip_request_headers")
            ),
            inject_request_headers=_coerce_injected_headers(injected),
        ),
    )


def _coerce_injected_headers(values: Sequence[Any]) -> list[InjectedHeaderConfig]:
    result: list[InjectedHeaderConfig] = []
    for item in values:
        if isinstance(item, InjectedHeaderConfig):
            result.append(item)
            continue
        if not isinstance(item, Mapping):
            raise TypeError("inject_request_headers entries must be objects")
        result.append(
            InjectedHeaderConfig(
                name=str(item.get("name", "")),
                secret_env_var=item.get("secret_env_var"),
                secret_file=item.get("secret_file"),
                prefix=item.get("prefix"),
            )
        )
    return result


def _coerce_string_list_mapping(value: Any, field_name: str) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    return {str(key): list(_string_tuple(values, field_name)) for key, values in value.items()}


def _normalize_hook_host(host: str) -> str:
    normalized = normalize_host(host)
    if not normalized:
        raise ValueError("host must not be empty")
    if "*" in normalized:
        raise ValueError("MITM hook hosts must be exact hosts and cannot contain wildcards")
    return normalized


def _normalize_methods(methods: Sequence[str]) -> list[str]:
    result: list[str] = []
    for method in methods:
        normalized = method.strip().upper()
        if not normalized:
            raise ValueError("methods must not contain empty entries")
        result.append(normalized)
    return result


def _compile_path_matchers(path_prefixes: Sequence[str]) -> list[PathMatcher]:
    result: list[PathMatcher] = []
    for prefix in path_prefixes:
        kind, pattern = _parse_matcher_pattern(prefix)
        if kind == "literal":
            if pattern == "":
                raise ValueError("path_prefixes must not contain empty entries")
            result.append(PathMatcher.prefix(pattern))
        else:
            result.append(PathMatcher.glob_matcher(pattern))
    return result


def _compile_value_matchers(values: Sequence[str]) -> list[ValueMatcher]:
    result: list[ValueMatcher] = []
    for value in values:
        kind, pattern = _parse_matcher_pattern(value)
        result.append(ValueMatcher.exact(pattern) if kind == "literal" else ValueMatcher.glob_matcher(pattern))
    return result


def _parse_matcher_pattern(pattern: str) -> tuple[str, str]:
    if pattern.startswith("literal:"):
        return ("literal", pattern[len("literal:") :])
    if pattern.startswith("pattern:"):
        glob_pattern = pattern[len("pattern:") :]
        if not glob_pattern:
            raise ValueError("glob pattern must not be empty")
        _validate_glob_pattern(glob_pattern)
        return ("glob", glob_pattern)
    return ("literal", pattern)


def _validate_query_constraints(query: Mapping[str, Sequence[str]]) -> None:
    for name, values in query.items():
        normalized = _normalize_query_name(name)
        if not normalized:
            raise ValueError("query keys must not be empty")
        if not values:
            raise ValueError(f"query key {name!r} must list at least one allowed value")
        _compile_value_matchers(values)


def _normalize_query_name(name: str) -> str:
    if name == "":
        raise ValueError("query keys must not be empty")
    return name


def _validate_header_constraints(headers: Mapping[str, Sequence[str]]) -> None:
    for name, values in headers.items():
        _parse_header_name(name)
        _compile_value_matchers(values)


def _validate_strip_request_headers(header_names: Sequence[str]) -> None:
    for name in header_names:
        _parse_header_name(name)


def _validate_injected_headers(headers: Sequence[InjectedHeaderConfig]) -> None:
    for header in headers:
        _parse_header_name(header.name)
        if header.secret_env_var is not None and header.secret_file is None:
            if not header.secret_env_var.strip():
                raise ValueError("secret_env_var must not be empty")
        elif header.secret_env_var is None and header.secret_file is not None:
            _parse_secret_file(header.secret_file)
        else:
            raise ValueError("expected exactly one of secret_env_var or secret_file")


_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _parse_header_name(name: str) -> str:
    if not isinstance(name, str) or _HEADER_NAME_RE.fullmatch(name) is None:
        raise ValueError(f"invalid header name {name!r}")
    return name.lower()


def _parse_secret_file(path: str) -> str:
    if not path.strip():
        raise ValueError("secret_file must not be empty")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError(f"secret_file must be an absolute path: {path!r}")
    return str(candidate)


def _validate_header_value(value: str, message: str) -> None:
    if "\r" in value or "\n" in value:
        raise ValueError(message)


def _validate_glob_pattern(pattern: str) -> None:
    in_class = False
    escaped = False
    for ch in pattern:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "[":
            if in_class:
                raise ValueError(f"invalid glob pattern {pattern!r}")
            in_class = True
        elif ch == "]":
            if not in_class:
                raise ValueError(f"invalid glob pattern {pattern!r}")
            in_class = False
    if in_class:
        raise ValueError(f"invalid glob pattern {pattern!r}")


def _glob_to_regex(pattern: str, *, literal_separator: bool) -> str:
    pieces = ["^"]
    index = 0
    while index < len(pattern):
        ch = pattern[index]
        if ch == "*":
            pieces.append("[^/]*" if literal_separator else ".*")
        elif ch == "?":
            pieces.append("[^/]" if literal_separator else ".")
        elif ch == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                raise ValueError(f"invalid glob pattern {pattern!r}")
            cls = pattern[index : end + 1]
            pieces.append(cls)
            index = end
        elif ch == "\\" and index + 1 < len(pattern):
            index += 1
            pieces.append(re.escape(pattern[index]))
        else:
            pieces.append(re.escape(ch))
        index += 1
    pieces.append("$")
    return "".join(pieces)


def _request_method(request: Any) -> str:
    if isinstance(request, Mapping):
        return str(request.get("method", ""))
    return str(getattr(request, "method", ""))


def _request_uri(request: Any) -> str:
    if isinstance(request, Mapping):
        return str(request.get("uri", request.get("url", "")))
    return str(getattr(request, "uri", getattr(request, "url", "")))


def _request_headers(request: Any) -> Mapping[str, Any]:
    if isinstance(request, Mapping):
        headers = request.get("headers", {})
    else:
        headers = getattr(request, "headers", {})
    return headers if isinstance(headers, Mapping) else {}


def _request_client(request: Any) -> str | None:
    if isinstance(request, Mapping):
        client = request.get("client")
    else:
        client = getattr(request, "client", None)
    return str(client) if client is not None else None


def extract_request_host(request: Any) -> str | None:
    headers = _request_headers(request)
    for name, value in headers.items():
        if str(name).lower() == "host":
            return str(value)
    parsed = urlparse(_request_uri(request))
    if parsed.netloc:
        return parsed.netloc
    if parsed.scheme and parsed.path:
        return parsed.path.split("/", 1)[0] or None
    return None


def authority_header_value(host: str, port: int) -> str:
    if ":" in host:
        return f"[{host}]" if int(port) == 443 else f"[{host}]:{int(port)}"
    return host if int(port) == 443 else f"{host}:{int(port)}"


def build_https_uri(authority: str, path: str) -> str:
    target = f"https://{authority}{path}"
    parsed = urlparse(target)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"invalid https URI: {target}")
    return target


def path_and_query(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.path:
        return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
    if parsed.query:
        return f"?{parsed.query}"
    return "/"


def path_for_log(uri: str) -> str:
    return urlparse(uri).path or "/"


def _request_log_path(request: Any) -> str:
    return path_for_log(_request_uri(request))


def _socks_request_host(request: Socks5TcpRequest | Socks5UdpRequest | Mapping[str, object] | object) -> str:
    if isinstance(request, Mapping):
        return str(request.get("host", ""))
    return str(getattr(request, "host", ""))


def _socks_request_port(request: Socks5TcpRequest | Socks5UdpRequest | Mapping[str, object] | object) -> int:
    if isinstance(request, Mapping):
        port = request.get("port", 0)
    else:
        port = getattr(request, "port", 0)
    return int(port)


def _socks_request_client(request: Socks5TcpRequest | Socks5UdpRequest | Mapping[str, object] | object) -> str | None:
    if isinstance(request, Mapping):
        client = request.get("client")
    else:
        client = getattr(request, "client", None)
    return str(client) if client is not None else None


def _socks_udp_payload(request: Socks5UdpRequest | Mapping[str, object] | object) -> bytes:
    if isinstance(request, Mapping):
        payload = request.get("payload", b"")
    else:
        payload = getattr(request, "payload", b"")
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, str):
        return payload.encode()
    return bytes(payload)


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


def _extract_request_host(request: Any) -> str | None:
    return extract_request_host(request)


def _http_connect_request(request: HttpConnectRequest | Mapping[str, object] | object) -> HttpConnectRequest:
    if isinstance(request, HttpConnectRequest):
        return request
    return HttpConnectRequest(
        uri=_request_uri(request),
        headers=dict(_request_headers(request)),
        client=_request_client(request),
    )


def _http_plain_request(request: HttpPlainRequest | Mapping[str, object] | object) -> HttpPlainRequest:
    if isinstance(request, HttpPlainRequest):
        return request
    return HttpPlainRequest(
        method=_request_method(request),
        uri=_request_uri(request),
        headers=dict(_request_headers(request)),
        client=_request_client(request),
    )


def _http_connect_authority(request: HttpConnectRequest) -> tuple[str, int] | None:
    candidates: list[str] = []
    parsed = urlparse(request.uri)
    if parsed.netloc:
        candidates.append(parsed.netloc)
    elif request.uri:
        candidates.append(request.uri)
    host_header = _header_value(request.headers, "host")
    if host_header is not None:
        candidates.append(str(host_header))

    for candidate in candidates:
        try:
            host, port = _parse_host_header(candidate)
        except ValueError:
            continue
        if port is None:
            scheme = parsed.scheme.lower()
            port = _default_port_for_scheme(scheme) if scheme else 443
        if port is None:
            continue
        return host, port
    return None


def _http_plain_authority(request: HttpPlainRequest) -> tuple[str, int] | None:
    parsed = urlparse(request.uri)
    if parsed.hostname:
        port = parsed.port or _default_port_for_scheme(parsed.scheme) or 80
        return parsed.hostname, port
    host_header = _header_value(request.headers, "host")
    if host_header is None:
        return None
    try:
        host, port = _parse_host_header(str(host_header))
    except ValueError:
        return None
    return host, port or 80


async def _handle_http_proxy_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
) -> None:
    try:
        raw_head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        _write_http_proxy_response(writer, text_response(400, "bad request"))
        await _close_stream_writer(writer)
        return

    try:
        method, target, headers = _parse_http1_proxy_request_head(raw_head)
    except ValueError:
        _write_http_proxy_response(writer, text_response(400, "bad request"))
        await _close_stream_writer(writer)
        return

    client = _stream_peer_addr(writer)
    if method == "CONNECT":
        try:
            result = await http_connect_accept(
                HttpConnectRequest(uri=target, headers=headers, client=client),
                state,
                decider,
            )
        except HttpConnectRejected as exc:
            _write_http_proxy_response(writer, exc.response)
            await _close_stream_writer(writer)
            return
        _write_http_proxy_response(writer, result.response)
        await writer.drain()
        await _forward_connect_tunnel(reader, writer, result.accepted, state)
        return

    response = await http_plain_proxy(
        HttpPlainRequest(method=method, uri=target, headers=headers, client=client),
        state,
        decider,
    )
    _write_http_proxy_response(writer, response)
    await _close_stream_writer(writer)


def _parse_http1_proxy_request_head(raw_head: bytes) -> tuple[str, str, dict[str, str]]:
    text = raw_head.decode("iso-8859-1")
    lines = text.split("\r\n")
    if not lines or not lines[0]:
        raise ValueError("missing request line")
    parts = lines[0].split()
    if len(parts) != 3 or not parts[2].startswith("HTTP/1."):
        raise ValueError("invalid request line")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        if ":" not in line:
            raise ValueError("invalid header")
        name, value = line.split(":", 1)
        headers[name.strip()] = value.strip()
    return parts[0].upper(), parts[1], headers


def _write_http_proxy_response(writer: asyncio.StreamWriter, response: NetworkProxyResponse) -> None:
    body = response.body.encode("utf-8")
    headers: dict[str, str] = {
        "content-length": str(len(body)),
        "connection": "close",
    }
    headers.update({str(key): str(value) for key, value in response.headers.items()})
    lines = [f"HTTP/1.1 {response.status} {_http_reason_phrase(response.status)}"]
    lines.extend(f"{key}: {value}" for key, value in headers.items())
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1") + body)


def _http_reason_phrase(status: int) -> str:
    return {
        200: "OK",
        400: "Bad Request",
        403: "Forbidden",
        501: "Not Implemented",
        502: "Bad Gateway",
        503: "Service Unavailable",
    }.get(status, "OK")


def _stream_peer_addr(writer: asyncio.StreamWriter) -> str | None:
    peer = writer.get_extra_info("peername")
    if isinstance(peer, tuple) and len(peer) >= 2:
        return f"{peer[0]}:{peer[1]}"
    return None


async def _close_stream_writer(writer: asyncio.StreamWriter) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except (ConnectionError, RuntimeError):
        pass


async def _forward_connect_tunnel(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    accepted: HttpConnectAccepted,
    state: NetworkProxyState,
) -> None:
    if accepted.mitm_enabled:
        # MITM tunnel handling remains a separate runtime boundary.
        await _close_stream_writer(client_writer)
        return

    try:
        allow_upstream_proxy = await state.allow_upstream_proxy()
    except Exception:
        allow_upstream_proxy = False
    upstream_proxy = proxy_for_connect() if allow_upstream_proxy else None

    try:
        if upstream_proxy is not None:
            target_reader, target_writer = await _open_upstream_connect_tunnel(
                accepted,
                upstream_proxy,
            )
        else:
            target_reader, target_writer = await asyncio.open_connection(
                accepted.host,
                accepted.port,
            )
    except (OSError, ValueError):
        await _close_stream_writer(client_writer)
        return

    async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        finally:
            await _close_stream_writer(writer)

    await asyncio.gather(
        pipe(client_reader, target_writer),
        pipe(target_reader, client_writer),
        return_exceptions=True,
    )


async def _open_upstream_connect_tunnel(
    accepted: HttpConnectAccepted,
    proxy: ProxyAddress,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    if not proxy.host:
        raise ValueError("missing proxy host")
    proxy_port = proxy.port or 80
    reader, writer = await asyncio.open_connection(proxy.host, proxy_port)
    authority = f"{accepted.host}:{accepted.port}"
    request = (
        f"CONNECT {authority} HTTP/1.1\r\n"
        f"Host: {authority}\r\n"
        "\r\n"
    )
    writer.write(request.encode("ascii"))
    await writer.drain()

    try:
        response = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        await _close_stream_writer(writer)
        raise OSError("upstream CONNECT failed") from exc
    status_line = response.split(b"\r\n", 1)[0]
    if not (
        status_line.startswith(b"HTTP/1.1 200 ")
        or status_line == b"HTTP/1.1 200"
        or status_line.startswith(b"HTTP/1.0 200 ")
        or status_line == b"HTTP/1.0 200"
    ):
        await _close_stream_writer(writer)
        raise OSError("upstream CONNECT failed")
    return reader, writer


async def _record_http_connect_blocked(
    state: NetworkProxyState,
    host: str,
    port: int,
    client: str | None,
    mode: NetworkMode | None,
    details: PolicyDecisionDetails,
) -> None:
    await state.record_blocked(
        BlockedRequest.new(
            BlockedRequestArgs(
                host=host,
                reason=details.reason,
                client=client,
                method="CONNECT",
                mode=mode,
                protocol="http-connect",
                decision=details.decision.as_str(),
                source=details.source.as_str(),
                port=port,
            )
        )
    )


async def _record_plain_http_blocked(
    state: NetworkProxyState,
    host: str,
    port: int,
    client: str | None,
    method: str | None,
    mode: NetworkMode | None,
    details: PolicyDecisionDetails,
) -> None:
    await state.record_blocked(
        BlockedRequest.new(
            BlockedRequestArgs(
                host=host,
                reason=details.reason,
                client=client,
                method=method,
                mode=mode,
                protocol=NetworkProtocol.HTTP.as_policy_protocol(),
                decision=details.decision.as_str(),
                source=details.source.as_str(),
                port=port,
            )
        )
    )


def _remove_header_case_insensitive(headers: MutableMapping[str, Any], header_name: str) -> None:
    lowered = header_name.lower()
    for key in list(headers.keys()):
        if str(key).lower() == lowered:
            del headers[key]


def _validate_non_global_wildcard_domain_patterns(field_name: str, patterns: Sequence[str]) -> None:
    for pattern in patterns:
        if _is_global_wildcard_domain_pattern(pattern):
            raise NetworkProxyConstraintError(
                field_name,
                pattern.strip(),
                "exact hosts or scoped wildcards like *.example.com or **.example.com",
            )


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


def _is_explicit_local_allowlisted(allowed_domains: Sequence[str], host: Host) -> bool:
    host_str = host.as_str()
    return any(normalize_host(pattern) == host_str for pattern in allowed_domains)


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


def _network_mode_rank(mode: NetworkMode | str) -> int:
    mode = NetworkMode(mode)
    return 0 if mode is NetworkMode.LIMITED else 1


def _rust_debug_network_mode(mode: NetworkMode | str) -> str:
    mode = NetworkMode(mode)
    return "Limited" if mode is NetworkMode.LIMITED else "Full"


def _rust_debug_list(values: Sequence[str]) -> str:
    return "[" + ", ".join(f'"{value}"' for value in values) + "]"


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


def _header_key(headers: Mapping[str, object], name: str) -> str | None:
    lowered = name.lower()
    for key in headers:
        if str(key).lower() == lowered:
            return str(key)
    return None


def _header_value(headers: Mapping[str, object], name: str) -> object | None:
    key = _header_key(headers, name)
    if key is None:
        return None
    return headers[key]


def _connection_header_tokens(raw_connection: object) -> list[str]:
    if isinstance(raw_connection, bytes):
        try:
            raw_connection = raw_connection.decode("ascii")
        except UnicodeDecodeError:
            return []
    if isinstance(raw_connection, Sequence) and not isinstance(raw_connection, str):
        values = raw_connection
    else:
        values = (raw_connection,)
    tokens: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        tokens.extend(token.strip() for token in value.split(",") if token.strip())
    return tokens


def _parse_host_header(value: str) -> tuple[str, int | None]:
    text = value.strip()
    if not text:
        raise ValueError("empty Host header")
    parsed = urlparse(f"//{text}")
    host = parsed.hostname
    if not host:
        raise ValueError("invalid Host header")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid Host header") from exc
    return host, port


def _default_port_for_scheme(scheme: str) -> int | None:
    normalized = scheme.lower()
    if normalized == "http":
        return 80
    if normalized == "https":
        return 443
    return None


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


def _string_field(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    return value


def _apply_network_to_config(config: NetworkProxyConfig, network: NetworkToml) -> None:
    if network.mode is not None:
        config.network.mode = NetworkMode(network.mode)
    if network.domains is not None:
        overlay_network_domain_permissions(config, network.domains)
    if config.network.mode is NetworkMode.LIMITED:
        config.network.mitm = True


def _network_from_mapping(value: object) -> NetworkToml | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("network must be a mapping")
    domains = value.get("domains")
    if domains is not None and not isinstance(domains, Mapping):
        raise TypeError("network.domains must be a mapping")
    unix_sockets = value.get("unix_sockets")
    if unix_sockets is not None and (isinstance(unix_sockets, str) or not isinstance(unix_sockets, Sequence)):
        raise TypeError("network.unix_sockets must be a sequence")
    return NetworkToml(
        enabled=_optional_bool(value.get("enabled"), "network.enabled"),
        mode=_optional_mode(value.get("mode")),
        allow_upstream_proxy=_optional_bool(value.get("allow_upstream_proxy"), "network.allow_upstream_proxy"),
        dangerously_allow_non_loopback_proxy=_optional_bool(
            value.get("dangerously_allow_non_loopback_proxy"),
            "network.dangerously_allow_non_loopback_proxy",
        ),
        dangerously_allow_all_unix_sockets=_optional_bool(
            value.get("dangerously_allow_all_unix_sockets"),
            "network.dangerously_allow_all_unix_sockets",
        ),
        domains=domains,  # type: ignore[arg-type]
        unix_sockets=unix_sockets,  # type: ignore[arg-type]
        allow_local_binding=_optional_bool(value.get("allow_local_binding"), "network.allow_local_binding"),
    )


def _optional_bool(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{label} must be a bool")
    return value


def _optional_mode(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("network.mode must be a string")
    return NetworkMode(value).value


def _resolve_permission_profile(
    permissions: Mapping[str, Mapping[str, JsonValue]],
    profile_name: str,
    seen: frozenset[str] = frozenset(),
) -> dict[str, JsonValue]:
    if profile_name in seen:
        raise ValueError(f"permissions profile `{profile_name}` extends itself")
    if profile_name in {":read-only", ":workspace"}:
        return {}
    _reject_unknown_builtin_permission_profile(profile_name)
    raw = permissions.get(profile_name)
    if raw is None:
        raise ValueError(f"permissions profile `{profile_name}` is not defined")
    if not isinstance(raw, Mapping):
        raise TypeError(f"permissions profile `{profile_name}` must be a mapping")
    parent_name = raw.get("extends")
    if parent_name is not None and not isinstance(parent_name, str):
        raise TypeError("permissions profile extends must be a string")
    resolved: dict[str, JsonValue] = {}
    if parent_name is not None:
        resolved = _resolve_permission_profile(permissions, parent_name, seen | {profile_name})
    _deep_merge_mapping(resolved, raw)
    resolved.pop("extends", None)
    return resolved


def _deep_merge_mapping(target: dict[str, JsonValue], source: Mapping[str, JsonValue]) -> None:
    for key, value in source.items():
        if (
            isinstance(value, Mapping)
            and isinstance(target.get(key), Mapping)
        ):
            child = dict(target[key])  # type: ignore[index]
            _deep_merge_mapping(child, value)
            target[key] = child
        else:
            target[key] = value


def _is_builtin_permission_profile_name(profile_name: str) -> bool:
    return profile_name in {":read-only", ":workspace", ":danger-full-access"}


def _reject_unknown_builtin_permission_profile(profile_name: str) -> None:
    if profile_name.startswith(":"):
        raise ValueError(f"default_permissions refers to unknown built-in profile `{profile_name}`")


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


def _path_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


__all__ = [
    "ConfigState",
    "ConfigLayerEntry",
    "ConfigLayerSource",
    "DomainGlobSet",
    "Host",
    "LayerMtime",
    "MtimeConfigReloader",
    "ConfigLayersLoader",
    "AUDIT_TARGET",
    "ALLOW_LOCAL_BINDING_ENV_KEY",
    "ALL_PROXY_ENV_KEYS",
    "BlockedRequest",
    "BlockedRequestArgs",
    "BlockDecisionAuditEventArgs",
    "DEFAULT_CLIENT_ADDRESS",
    "DEFAULT_METHOD",
    "DNS_LOOKUP_TIMEOUT_SECONDS",
    "HostBlockDecision",
    "HostBlockReason",
    "MANAGED_MITM_CA_CERT",
    "MANAGED_MITM_CA_DIR",
    "MANAGED_MITM_CA_KEY",
    "NetworkConstraints",
    "NetworkDecision",
    "NetworkDecisionSource",
    "NetworkDomainPermission",
    "InjectedHeaderConfig",
    "CompiledGlobMatcher",
    "HeaderConstraint",
    "HookEvaluation",
    "HttpConnectAccepted",
    "HttpConnectAcceptResult",
    "HttpConnectRejected",
    "HttpConnectRequest",
    "HttpPlainRequest",
    "MitmPolicyContext",
    "MitmPolicyDecision",
    "MitmHookActionsConfig",
    "MitmHookActions",
    "MitmHookConfig",
    "MitmHook",
    "MitmHookEvaluation",
    "MitmHookMatcher",
    "MitmHookMatchConfig",
    "NetworkMode",
    "NetworkPolicyDecision",
    "NetworkPolicyRequest",
    "NetworkPolicyRequestArgs",
    "NetworkProtocol",
    "ManagedMitmCaPaths",
    "MAX_BLOCKED_EVENTS",
    "NETWORK_POLICY_VIOLATION_PREFIX",
    "DEFAULT_NO_PROXY_VALUE",
    "ELECTRON_GET_USE_PROXY_ENV_KEY",
    "FTP_PROXY_ENV_KEYS",
    "NODE_USE_ENV_PROXY_ENV_KEY",
    "POLICY_DECISION_ALLOW",
    "POLICY_DECISION_DENY",
    "POLICY_DECISION_EVENT_NAME",
    "POLICY_REASON_ALLOW",
    "POLICY_SCOPE_DOMAIN",
    "POLICY_SCOPE_NON_DOMAIN",
    "PROXY_ACTIVE_ENV_KEY",
    "PROXY_ENV_KEYS",
    "PROXY_GIT_SSH_COMMAND_ENV_KEY",
    "PROXY_URL_ENV_KEYS",
    "PolicyDecisionDetails",
    "ProxyAddress",
    "ProxyConfig",
    "PathMatcher",
    "QueryConstraint",
    "REASON_DENIED",
    "REASON_METHOD_NOT_ALLOWED",
    "REASON_MITM_HOOK_DENIED",
    "REASON_MITM_REQUIRED",
    "REASON_NOT_ALLOWED",
    "REASON_NOT_ALLOWED_LOCAL",
    "REASON_POLICY_DENIED",
    "REASON_PROXY_DISABLED",
    "REASON_UNIX_SOCKET_UNSUPPORTED",
    "NetworkProxyAuditMetadata",
    "NetworkProxyBuilder",
    "NetworkProxyBuilderCallback",
    "NetworkProxyConfig",
    "NetworkProxyConstraintError",
    "NetworkProxyConstraints",
    "NetworkProxy",
    "NetworkProxyHandle",
    "NetworkProxyNetworkConfig",
    "NetworkProxyResponse",
    "NetworkProxyRuntimeSettings",
    "NetworkProxyState",
    "NetworkProxySpec",
    "NetworkProxyTask",
    "NetworkTablesToml",
    "NetworkToml",
    "ReservedListenerSet",
    "RuntimeConfig",
    "ResolvedInjectedHeader",
    "SecretSource",
    "Socks5PolicyError",
    "Socks5PolicyResult",
    "Socks5TcpRequest",
    "Socks5UdpRequest",
    "StartedNetworkProxy",
    "StaticNetworkProxyReloader",
    "TargetCheckedTcpConnector",
    "TargetRejectedError",
    "UpstreamClient",
    "UpstreamRoute",
    "apply_exec_policy_network_rules",
    "apply_mitm_hook_actions",
    "apply_network_tables",
    "apply_network_constraints",
    "apply_proxy_env_overrides",
    "authority_header_value",
    "build_config_state",
    "build_https_uri",
    "build_network_proxy_state",
    "build_network_proxy_state_and_reloader",
    "ask_not_allowed_policy_decider",
    "blocked_header_value",
    "blocked_message",
    "blocked_message_with_policy",
    "blocked_request_violation_log_line",
    "blocked_text_response",
    "blocked_text_response_with_policy",
    "CODEX_PROXY_GIT_SSH_COMMAND_MARKER",
    "collect_layer_mtimes",
    "config_from_layers",
    "compile_allowlist_globset",
    "compile_denylist_globset",
    "compile_mitm_hooks",
    "compile_mitm_hooks_with_resolvers",
    "codex_proxy_git_ssh_command",
    "emit_allow_decision_audit_event",
    "emit_block_decision_audit_event",
    "emit_socks_block_decision_audit_event",
    "evaluate_host_policy",
    "evaluate_mitm_policy",
    "evaluate_mitm_hooks",
    "extract_request_host",
    "json_response",
    "json_blocked",
    "host_and_port_from_network_addr",
    "is_global_wildcard_domain_pattern",
    "is_loopback_host",
    "is_non_public_ip",
    "host_resolves_to_non_public_ip",
    "http_connect_accept",
    "http_plain_proxy",
    "run_http_proxy",
    "run_http_proxy_with_std_listener",
    "is_codex_proxy_git_ssh_command",
    "is_user_controlled_layer",
    "managed_ca_paths",
    "network_constraints_from_trusted_layers",
    "network_tables_from_toml",
    "normalize_host",
    "overlay_network_domain_permissions",
    "map_decider_decision",
    "mitm_blocking_response",
    "path_and_query",
    "path_for_log",
    "handle_socks5_tcp_policy",
    "proxy_for_connect",
    "proxy_url_env_value",
    "read_proxy_env",
    "reserve_loopback_ephemeral_listeners",
    "reserve_windows_managed_listeners",
    "remove_hop_by_hop_request_headers",
    "resolve_runtime",
    "run_socks5",
    "run_socks5_with_std_listener",
    "selected_network_from_tables",
    "inspect_socks5_udp_policy",
    "text_response",
    "upsert_network_domain",
    "unix_timestamp",
    "validate_absolute_form_host_header",
    "validate_existing_ca_key_file",
    "validate_mitm_hook_config",
    "validate_policy_against_constraints",
    "ValueMatcher",
    "windows_managed_loopback_addr",
    "write_atomic_create_new",
]

