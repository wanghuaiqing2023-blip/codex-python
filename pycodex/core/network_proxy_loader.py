"""Layered network proxy loading owned by ``core::network_proxy_loader``."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.app_server_protocol.config import ConfigLayerSource
from pycodex.config.config_requirements import NetworkConstraints
from pycodex.config.permissions_toml import NetworkToml
from pycodex.config.state import ConfigLayerEntry
from pycodex.network_proxy import (
    ConfigState,
    NetworkDomainPermission,
    NetworkMode,
    NetworkProxyConfig,
    NetworkProxyConstraints,
    NetworkProxyState,
)
from pycodex.network_proxy.config import _string_tuple

JsonValue = Any
ConfigLayersLoader = Callable[
    [],
    Sequence[ConfigLayerEntry] | Awaitable[Sequence[ConfigLayerEntry]],
]
@dataclass(frozen=True)
class NetworkTablesToml:
    default_permissions: str | None = None
    permissions: Mapping[str, Mapping[str, JsonValue]] | None = None

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
        if not layer.is_disabled():
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
        if not layer.is_disabled() and not is_user_controlled_layer(layer.name):
            _deep_merge_mapping(merged, layer.config)
    constraints = NetworkProxyConstraints()
    network = selected_network_from_tables(network_tables_from_toml(merged))
    if network is not None:
        apply_network_constraints(network, constraints)
    return constraints


def overlay_network_domain_permissions(
    config: NetworkProxyConfig,
    domains: object,
) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    entries = getattr(domains, "entries", domains)
    if not isinstance(entries, Mapping):
        raise TypeError("domains must be a mapping")
    for host, permission in entries.items():
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
        if layer.is_disabled():
            continue
        path = _layer_config_path(layer.name)
        if path is not None:
            mtimes.append(LayerMtime.new(path))
    return mtimes


def is_user_controlled_layer(layer: ConfigLayerSource) -> bool:
    if not isinstance(layer, ConfigLayerSource):
        raise TypeError("layer must be ConfigLayerSource")
    return layer.type in {"user", "project", "sessionFlags"}


def _layer_config_path(layer: ConfigLayerSource) -> Path | None:
    if layer.type in {"system", "user", "legacyManagedConfigTomlFromFile"}:
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
    return NetworkToml.from_mapping(value)


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

def _path_mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None

__all__ = [
    "LayerMtime",
    "MtimeConfigReloader",
    "apply_exec_policy_network_rules",
    "apply_network_constraints",
    "build_network_proxy_state",
    "build_network_proxy_state_and_reloader",
    "collect_layer_mtimes",
    "config_from_layers",
    "is_user_controlled_layer",
    "network_constraints_from_trusted_layers",
    "network_tables_from_toml",
    "overlay_network_domain_permissions",
    "selected_network_from_tables",
    "upsert_network_domain",
]
