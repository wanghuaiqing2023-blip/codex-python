"""Pure helpers from the network proxy loader.

Ported from the portable pieces of
``codex/codex-rs/core/src/network_proxy_loader.rs``.

The real Rust module also loads layered config and constructs a
``codex_network_proxy`` state.  This stdlib port keeps the deterministic helper
semantics that can be represented without that external runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

JsonValue = Any


class NetworkDomainPermission(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class NetworkMode(str, Enum):
    FULL = "full"
    LIMITED = "limited"


@dataclass
class NetworkProxyNetworkConfig:
    enabled: bool = False
    proxy_url: str = "http://127.0.0.1:3128"
    enable_socks5: bool = False
    socks_url: str = "http://127.0.0.1:1080"
    enable_socks5_udp: bool = False
    allow_upstream_proxy: bool = False
    dangerously_allow_non_loopback_proxy: bool = False
    dangerously_allow_all_unix_sockets: bool = False
    mode: NetworkMode = NetworkMode.LIMITED
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
        return list(self._allowed_domains) if self._allowed_domains else None

    def denied_domains(self) -> list[str] | None:
        return list(self._denied_domains) if self._denied_domains else None

    def set_allow_unix_sockets(self, sockets: Sequence[str] | None) -> None:
        self.allow_unix_sockets = list(_string_tuple(sockets or (), "allow unix sockets"))

    def upsert_domain_permission(self, host: str, permission: NetworkDomainPermission) -> None:
        normalized = normalize_host(host)
        permission = NetworkDomainPermission(permission)
        self._allowed_domains = [item for item in self._allowed_domains if item != normalized]
        self._denied_domains = [item for item in self._denied_domains if item != normalized]
        if permission is NetworkDomainPermission.ALLOW:
            self._allowed_domains.append(normalized)
        else:
            self._denied_domains.append(normalized)


@dataclass
class NetworkProxyConfig:
    network: NetworkProxyNetworkConfig = field(default_factory=NetworkProxyNetworkConfig)


@dataclass
class NetworkProxyConstraints:
    enabled: bool | None = None
    mode: str | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    allowed_domains: list[str] | None = None
    denied_domains: list[str] | None = None
    allowlist_expansion_enabled: bool | None = None
    denylist_expansion_enabled: bool | None = None
    allow_unix_sockets: list[str] | None = None
    allow_local_binding: bool | None = None


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

    @classmethod
    def system(cls, file: Path | str) -> "ConfigLayerSource":
        return cls("system", file=Path(file))

    @classmethod
    def user(cls, file: Path | str) -> "ConfigLayerSource":
        return cls("user", file=Path(file))

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
    return host.strip().rstrip(".").lower()


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


def _host_and_port_from_url(url: str, default_port: int) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or default_port
    return f"{host}:{port}"


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
    "ConfigLayerEntry",
    "ConfigLayerSource",
    "LayerMtime",
    "MtimeConfigReloader",
    "NetworkConstraints",
    "NetworkDomainPermission",
    "NetworkMode",
    "NetworkProxyConfig",
    "NetworkProxyConstraints",
    "NetworkProxyNetworkConfig",
    "NetworkProxySpec",
    "NetworkTablesToml",
    "NetworkToml",
    "apply_exec_policy_network_rules",
    "apply_network_tables",
    "apply_network_constraints",
    "collect_layer_mtimes",
    "config_from_layers",
    "is_user_controlled_layer",
    "network_constraints_from_trusted_layers",
    "network_tables_from_toml",
    "normalize_host",
    "overlay_network_domain_permissions",
    "selected_network_from_tables",
    "upsert_network_domain",
]

