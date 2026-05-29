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

from pycodex.core.exec_policy import Decision

JsonValue = Any


class NetworkDomainPermission(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class NetworkMode(str, Enum):
    FULL = "full"
    LIMITED = "limited"


@dataclass
class NetworkProxyNetworkConfig:
    mode: NetworkMode = NetworkMode.LIMITED
    mitm: bool = False
    mitm_hooks: list[JsonValue] = field(default_factory=list)
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
    allow_unix_sockets: list[str] | None = None
    allow_local_binding: bool | None = None


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
    "NetworkDomainPermission",
    "NetworkMode",
    "NetworkProxyConfig",
    "NetworkProxyConstraints",
    "NetworkProxyNetworkConfig",
    "NetworkToml",
    "apply_exec_policy_network_rules",
    "apply_network_constraints",
    "collect_layer_mtimes",
    "is_user_controlled_layer",
    "normalize_host",
    "overlay_network_domain_permissions",
    "upsert_network_domain",
]
