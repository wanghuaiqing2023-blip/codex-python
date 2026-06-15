"""Permission TOML data helpers ported from ``codex-config::permissions_toml``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from pycodex.network_proxy import (
    InjectedHeaderConfig,
    MitmHookActionsConfig,
    MitmHookConfig,
    MitmHookMatchConfig,
    NetworkDomainPermission,
    NetworkMode,
    NetworkProxyConfig,
    normalize_host,
)


JsonValue = Any


class PermissionProfileResolutionError(ValueError):
    """Base error for permission profile inheritance resolution."""


class UndefinedProfile(PermissionProfileResolutionError):
    def __init__(self, profile_name: str):
        self.profile_name = profile_name
        super().__init__(f"default_permissions refers to undefined profile `{profile_name}`")


class UndefinedParent(PermissionProfileResolutionError):
    def __init__(self, profile_name: str, parent_profile_name: str):
        self.profile_name = profile_name
        self.parent_profile_name = parent_profile_name
        super().__init__(
            f"permissions profile `{profile_name}` extends undefined profile `{parent_profile_name}`"
        )


class UnsupportedBuiltInParent(PermissionProfileResolutionError):
    def __init__(self, profile_name: str, parent_profile_name: str):
        self.profile_name = profile_name
        self.parent_profile_name = parent_profile_name
        super().__init__(
            f"permissions profile `{profile_name}` cannot extend unsupported built-in profile `{parent_profile_name}`"
        )


class PermissionProfileCycle(PermissionProfileResolutionError):
    def __init__(self, cycle: tuple[str, ...]):
        self.cycle = cycle
        super().__init__(
            "permissions profile inheritance cycle detected: " + " -> ".join(cycle)
        )


class NetworkDomainPermissionToml(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class NetworkUnixSocketPermissionToml(str, Enum):
    ALLOW = "allow"
    NONE = "none"


class FilesystemPermissionToml(str, Enum):
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read-write"
    DENY = "deny"


@dataclass(frozen=True)
class WorkspaceRootsToml:
    entries: Mapping[str, bool]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "WorkspaceRootsToml":
        data = _mapping_or_empty(value, "workspace_roots")
        entries: dict[str, bool] = {}
        for path, enabled in data.items():
            if not isinstance(path, str):
                raise TypeError("workspace root paths must be strings")
            if not isinstance(enabled, bool):
                raise TypeError("workspace root enabled flags must be bools")
            entries[path] = enabled
        return cls(entries)

    def enabled_roots(self) -> tuple[str, ...]:
        return tuple(path for path, enabled in self.entries.items() if enabled)

    def to_mapping(self) -> dict[str, bool]:
        return dict(self.entries)


@dataclass(frozen=True)
class FilesystemPermissionsToml:
    entries: Mapping[str, JsonValue]
    glob_scan_max_depth: int | None = None

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue] | None
    ) -> "FilesystemPermissionsToml":
        data = _mapping_or_empty(value, "filesystem")
        glob_scan_max_depth = data.get("glob_scan_max_depth")
        if glob_scan_max_depth is not None and (
            isinstance(glob_scan_max_depth, bool)
            or not isinstance(glob_scan_max_depth, int)
            or glob_scan_max_depth < 1
        ):
            raise ValueError("glob_scan_max_depth must be a positive integer")
        entries = {str(path): permission for path, permission in data.items() if path != "glob_scan_max_depth"}
        return cls(entries, glob_scan_max_depth=glob_scan_max_depth)

    def is_empty(self) -> bool:
        return not self.entries

    def to_mapping(self) -> dict[str, JsonValue]:
        data = dict(self.entries)
        if self.glob_scan_max_depth is not None:
            data["glob_scan_max_depth"] = self.glob_scan_max_depth
        return data


@dataclass(frozen=True)
class NetworkDomainPermissionsToml:
    entries: Mapping[str, NetworkDomainPermissionToml]

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue] | None, *, normalize: bool = False
    ) -> "NetworkDomainPermissionsToml":
        data = _mapping_or_empty(value, "network domains")
        entries: dict[str, NetworkDomainPermissionToml] = {}
        for pattern, permission in data.items():
            if not isinstance(pattern, str):
                raise TypeError("network domain patterns must be strings")
            key = normalize_host(pattern) if normalize else pattern
            entries[key] = NetworkDomainPermissionToml(permission)
        return cls(entries)

    def is_empty(self) -> bool:
        return not self.entries

    def allowed_domains(self) -> tuple[str, ...] | None:
        allowed = tuple(
            pattern
            for pattern, permission in self.entries.items()
            if permission is NetworkDomainPermissionToml.ALLOW
        )
        return allowed or None

    def denied_domains(self) -> tuple[str, ...] | None:
        denied = tuple(
            pattern
            for pattern, permission in self.entries.items()
            if permission is NetworkDomainPermissionToml.DENY
        )
        return denied or None

    def to_mapping(self) -> dict[str, str]:
        return {pattern: permission.value for pattern, permission in self.entries.items()}


def overlay_network_domain_permissions(
    config: NetworkProxyConfig,
    domains: "NetworkDomainPermissionsToml",
) -> None:
    if not isinstance(config, NetworkProxyConfig):
        raise TypeError("config must be NetworkProxyConfig")
    if not isinstance(domains, NetworkDomainPermissionsToml):
        domains = NetworkDomainPermissionsToml.from_mapping(domains)  # type: ignore[arg-type]
    for pattern, permission in domains.entries.items():
        proxy_permission = (
            NetworkDomainPermission.ALLOW
            if permission is NetworkDomainPermissionToml.ALLOW
            else NetworkDomainPermission.DENY
        )
        config.network.upsert_domain_permission(pattern, proxy_permission)


@dataclass(frozen=True)
class NetworkUnixSocketPermissionsToml:
    entries: Mapping[str, NetworkUnixSocketPermissionToml]

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue] | None
    ) -> "NetworkUnixSocketPermissionsToml":
        data = _mapping_or_empty(value, "network unix sockets")
        entries: dict[str, NetworkUnixSocketPermissionToml] = {}
        for path, permission in data.items():
            if not isinstance(path, str):
                raise TypeError("network unix socket paths must be strings")
            entries[path] = NetworkUnixSocketPermissionToml(permission)
        return cls(entries)

    def is_empty(self) -> bool:
        return not self.entries

    def allow_unix_sockets(self) -> tuple[str, ...]:
        return tuple(
            path
            for path, permission in self.entries.items()
            if permission is NetworkUnixSocketPermissionToml.ALLOW
        )

    def to_mapping(self) -> dict[str, str]:
        return {path: permission.value for path, permission in self.entries.items()}


@dataclass(frozen=True)
class NetworkMitmInjectedHeaderToml:
    name: str
    secret_env_var: str | None = None
    secret_file: str | None = None
    prefix: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "NetworkMitmInjectedHeaderToml":
        data = _mapping(value, "network mitm injected header")
        _deny_unknown(data, _MITM_INJECTED_HEADER_FIELDS, "network mitm injected header")
        name = _required_str(data, "name")
        return cls(
            name=name,
            secret_env_var=_optional_str(data, "secret_env_var"),
            secret_file=_optional_str(data, "secret_file"),
            prefix=_optional_str(data, "prefix"),
        )

    def to_runtime(self) -> InjectedHeaderConfig:
        return InjectedHeaderConfig(
            name=self.name,
            secret_env_var=self.secret_env_var,
            secret_file=self.secret_file,
            prefix=self.prefix,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"name": self.name}
        if self.secret_env_var is not None:
            data["secret_env_var"] = self.secret_env_var
        if self.secret_file is not None:
            data["secret_file"] = self.secret_file
        if self.prefix is not None:
            data["prefix"] = self.prefix
        return data


@dataclass(frozen=True)
class NetworkMitmActionToml:
    strip_request_headers: tuple[str, ...] = ()
    inject_request_headers: tuple[NetworkMitmInjectedHeaderToml, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "NetworkMitmActionToml":
        data = _mapping_or_empty(value, "network mitm action")
        _deny_unknown(data, _MITM_ACTION_FIELDS, "network mitm action")
        return cls(
            strip_request_headers=_string_tuple(
                data.get("strip_request_headers", ()), "strip_request_headers"
            ),
            inject_request_headers=tuple(
                NetworkMitmInjectedHeaderToml.from_mapping(item)
                for item in _mapping_sequence(
                    data.get("inject_request_headers", ()), "inject_request_headers"
                )
            ),
        )

    def is_empty(self) -> bool:
        return not self.strip_request_headers and not self.inject_request_headers

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "strip_request_headers": list(self.strip_request_headers),
            "inject_request_headers": [
                header.to_mapping() for header in self.inject_request_headers
            ],
        }


@dataclass(frozen=True)
class NetworkMitmHookToml:
    host: str
    methods: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    query: Mapping[str, tuple[str, ...]] | None = None
    headers: Mapping[str, tuple[str, ...]] | None = None
    body: JsonValue | None = None
    action: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "NetworkMitmHookToml":
        data = _mapping(value, "network mitm hook")
        _deny_unknown(data, _MITM_HOOK_FIELDS, "network mitm hook")
        return cls(
            host=_required_str(data, "host"),
            methods=_string_tuple(data.get("methods", ()), "methods"),
            path_prefixes=_string_tuple(data.get("path_prefixes", ()), "path_prefixes"),
            query=_string_multimap(data.get("query"), "query"),
            headers=_string_multimap(data.get("headers"), "headers"),
            body=data.get("body"),
            action=_string_tuple(data.get("action", ()), "action"),
        )

    def to_runtime(
        self, actions_by_name: Mapping[str, NetworkMitmActionToml] | None
    ) -> MitmHookConfig:
        return MitmHookConfig(
            host=self.host,
            matcher=MitmHookMatchConfig(
                methods=list(self.methods),
                path_prefixes=list(self.path_prefixes),
                query={key: list(value) for key, value in (self.query or {}).items()},
                headers={key: list(value) for key, value in (self.headers or {}).items()},
                body=self.body,
            ),
            actions=self.selected_actions(actions_by_name),
        )

    def selected_actions(
        self, actions_by_name: Mapping[str, NetworkMitmActionToml] | None
    ) -> MitmHookActionsConfig:
        selected = MitmHookActionsConfig()
        if actions_by_name is None:
            return selected
        for action_name in self.action:
            action = actions_by_name.get(action_name)
            if action is None:
                continue
            selected.strip_request_headers.extend(action.strip_request_headers)
            selected.inject_request_headers.extend(
                header.to_runtime() for header in action.inject_request_headers
            )
        return selected

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "host": self.host,
            "methods": list(self.methods),
            "path_prefixes": list(self.path_prefixes),
            "action": list(self.action),
        }
        if self.query:
            data["query"] = {key: list(value) for key, value in self.query.items()}
        if self.headers:
            data["headers"] = {key: list(value) for key, value in self.headers.items()}
        if self.body is not None:
            data["body"] = self.body
        return data


@dataclass(frozen=True)
class NetworkMitmToml:
    hooks: Mapping[str, NetworkMitmHookToml] | None = None
    actions: Mapping[str, NetworkMitmActionToml] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "NetworkMitmToml | None":
        if value is None:
            return None
        data = _mapping(value, "network.mitm")
        _deny_unknown(data, _MITM_FIELDS, "network.mitm")
        hooks = _mitm_hooks(data.get("hooks")) if "hooks" in data else None
        actions = _mitm_actions(data.get("actions")) if "actions" in data else None
        mitm = cls(hooks=hooks, actions=actions)
        mitm.validate_action_definitions()
        return mitm

    def validate_action_definitions(self) -> None:
        for action_name, action in (self.actions or {}).items():
            if action.is_empty():
                raise ValueError(
                    f"network.mitm.actions.{action_name} must define at least one operation"
                )
        for hook_name, hook in (self.hooks or {}).items():
            if not hook.action:
                raise ValueError(f"network.mitm.hooks.{hook_name}.action must not be empty")

    def validate_action_references(
        self, actions_by_name: Mapping[str, NetworkMitmActionToml]
    ) -> None:
        self.validate_action_definitions()
        for hook_name, hook in (self.hooks or {}).items():
            for action_name in hook.action:
                if action_name not in actions_by_name:
                    raise ValueError(
                        f"network.mitm.hooks.{hook_name}.action references undefined action `{action_name}`"
                    )

    def to_runtime_hooks(
        self, actions_by_name: Mapping[str, NetworkMitmActionToml] | None = None
    ) -> list[MitmHookConfig]:
        return [
            hook.to_runtime(actions_by_name)
            for hook in (self.hooks or {}).values()
        ]

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.hooks is not None:
            data["hooks"] = {name: hook.to_mapping() for name, hook in self.hooks.items()}
        if self.actions is not None:
            data["actions"] = {
                name: action.to_mapping() for name, action in self.actions.items()
            }
        return data


@dataclass(frozen=True)
class NetworkToml:
    enabled: bool | None = None
    proxy_url: str | None = None
    enable_socks5: bool | None = None
    socks_url: str | None = None
    enable_socks5_udp: bool | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    mode: str | None = None
    domains: NetworkDomainPermissionsToml | None = None
    unix_sockets: NetworkUnixSocketPermissionsToml | None = None
    allow_local_binding: bool | None = None
    mitm: NetworkMitmToml | None = None

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue] | None, *, normalize_domains: bool = False
    ) -> "NetworkToml | None":
        if value is None:
            return None
        data = _mapping(value, "network")
        _deny_unknown(data, _NETWORK_FIELDS, "network")
        mode = _optional_str(data, "mode")
        if mode is not None and mode not in {"limited", "full"}:
            raise ValueError("mode must be 'limited' or 'full'")
        return cls(
            enabled=_optional_bool(data, "enabled"),
            proxy_url=_optional_str(data, "proxy_url"),
            enable_socks5=_optional_bool(data, "enable_socks5"),
            socks_url=_optional_str(data, "socks_url"),
            enable_socks5_udp=_optional_bool(data, "enable_socks5_udp"),
            allow_upstream_proxy=_optional_bool(data, "allow_upstream_proxy"),
            dangerously_allow_non_loopback_proxy=_optional_bool(
                data, "dangerously_allow_non_loopback_proxy"
            ),
            dangerously_allow_all_unix_sockets=_optional_bool(
                data, "dangerously_allow_all_unix_sockets"
            ),
            mode=mode,
            domains=NetworkDomainPermissionsToml.from_mapping(
                data.get("domains"), normalize=normalize_domains
            )
            if "domains" in data
            else None,
            unix_sockets=NetworkUnixSocketPermissionsToml.from_mapping(
                data.get("unix_sockets")
            )
            if "unix_sockets" in data
            else None,
            allow_local_binding=_optional_bool(data, "allow_local_binding"),
            mitm=NetworkMitmToml.from_mapping(data.get("mitm")),
        )

    def apply_to_network_proxy_config(self, config: NetworkProxyConfig) -> None:
        if not isinstance(config, NetworkProxyConfig):
            raise TypeError("config must be NetworkProxyConfig")
        network = config.network
        if self.enabled is not None:
            network.enabled = self.enabled
        if self.proxy_url is not None:
            network.proxy_url = self.proxy_url
        if self.enable_socks5 is not None:
            network.enable_socks5 = self.enable_socks5
        if self.socks_url is not None:
            network.socks_url = self.socks_url
        if self.enable_socks5_udp is not None:
            network.enable_socks5_udp = self.enable_socks5_udp
        if self.allow_upstream_proxy is not None:
            network.allow_upstream_proxy = self.allow_upstream_proxy
        if self.dangerously_allow_non_loopback_proxy is not None:
            network.dangerously_allow_non_loopback_proxy = (
                self.dangerously_allow_non_loopback_proxy
            )
        if self.dangerously_allow_all_unix_sockets is not None:
            network.dangerously_allow_all_unix_sockets = (
                self.dangerously_allow_all_unix_sockets
            )
        if self.mode is not None:
            network.mode = NetworkMode(self.mode)
        if self.domains is not None:
            overlay_network_domain_permissions(config, self.domains)
        if self.unix_sockets is not None:
            for path, permission in self.unix_sockets.entries.items():
                if permission is NetworkUnixSocketPermissionToml.ALLOW:
                    if path not in network.allow_unix_sockets:
                        network.allow_unix_sockets.append(path)
                else:
                    network.allow_unix_sockets = [
                        item for item in network.allow_unix_sockets if item != path
                    ]
        if self.allow_local_binding is not None:
            network.allow_local_binding = self.allow_local_binding
        if self.mitm is not None:
            network.mitm_hooks = self.mitm.to_runtime_hooks(self.mitm.actions)
        network.mitm = network.mode is NetworkMode.LIMITED or bool(network.mitm_hooks)

    def to_network_proxy_config(self) -> NetworkProxyConfig:
        config = NetworkProxyConfig()
        self.apply_to_network_proxy_config(config)
        return config

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        for key in (
            "enabled",
            "proxy_url",
            "enable_socks5",
            "socks_url",
            "enable_socks5_udp",
            "allow_upstream_proxy",
            "dangerously_allow_non_loopback_proxy",
            "dangerously_allow_all_unix_sockets",
            "mode",
            "allow_local_binding",
            "mitm",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value.to_mapping() if key == "mitm" else value
        if self.domains is not None:
            data["domains"] = self.domains.to_mapping()
        if self.unix_sockets is not None:
            data["unix_sockets"] = self.unix_sockets.to_mapping()
        return data


@dataclass(frozen=True)
class PermissionProfileToml:
    description: str | None = None
    extends: str | None = None
    workspace_roots: WorkspaceRootsToml | None = None
    filesystem: FilesystemPermissionsToml | None = None
    network: NetworkToml | None = None

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue] | None, *, normalize_domains: bool = False
    ) -> "PermissionProfileToml":
        if value is None:
            return cls()
        data = _mapping(value, "permission profile")
        _deny_unknown(data, _PROFILE_FIELDS, "permission profile")
        return cls(
            description=_optional_str(data, "description"),
            extends=_optional_str(data, "extends"),
            workspace_roots=WorkspaceRootsToml.from_mapping(data.get("workspace_roots"))
            if "workspace_roots" in data
            else None,
            filesystem=FilesystemPermissionsToml.from_mapping(data.get("filesystem"))
            if "filesystem" in data
            else None,
            network=NetworkToml.from_mapping(
                data.get("network"), normalize_domains=normalize_domains
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.description is not None:
            data["description"] = self.description
        if self.extends is not None:
            data["extends"] = self.extends
        if self.workspace_roots is not None:
            data["workspace_roots"] = self.workspace_roots.to_mapping()
        if self.filesystem is not None:
            data["filesystem"] = self.filesystem.to_mapping()
        if self.network is not None:
            data["network"] = self.network.to_mapping()
        return data


@dataclass(frozen=True)
class ResolvedPermissionProfileToml:
    profile: PermissionProfileToml
    inherited_profile_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class PermissionsToml:
    entries: Mapping[str, PermissionProfileToml]

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "PermissionsToml":
        data = _mapping_or_empty(value, "permissions")
        return cls(
            {
                str(name): PermissionProfileToml.from_mapping(profile)
                for name, profile in data.items()
            }
        )

    def is_empty(self) -> bool:
        return not self.entries

    def resolve_profile(
        self,
        profile_name: str,
        parent_profile: Callable[[str], PermissionProfileToml | Mapping[str, JsonValue] | None]
        | None = None,
    ) -> ResolvedPermissionProfileToml:
        if not isinstance(profile_name, str):
            raise TypeError("profile_name must be a string")
        parent_profile = parent_profile or (lambda _name: None)
        profile_names: list[str] = []
        profiles: list[PermissionProfileToml] = []
        next_profile_name = profile_name
        referenced_by: str | None = None

        while True:
            if next_profile_name in profile_names:
                cycle_start = profile_names.index(next_profile_name)
                cycle = tuple(profile_names[cycle_start:] + [next_profile_name])
                raise PermissionProfileCycle(cycle)

            profile = self.entries.get(next_profile_name)
            if profile is None:
                raw_parent = parent_profile(next_profile_name)
                profile = (
                    raw_parent
                    if isinstance(raw_parent, PermissionProfileToml)
                    else PermissionProfileToml.from_mapping(raw_parent)
                    if raw_parent is not None
                    else None
                )
            if profile is None:
                if referenced_by is None:
                    raise UndefinedProfile(next_profile_name)
                if next_profile_name.startswith(":"):
                    raise UnsupportedBuiltInParent(referenced_by, next_profile_name)
                raise UndefinedParent(referenced_by, next_profile_name)

            parent_profile_name = profile.extends
            profile_names.append(next_profile_name)
            if parent_profile_name is not None:
                profiles.append(profile)
                referenced_by = next_profile_name
                next_profile_name = parent_profile_name
                continue

            merged = profile
            for child in reversed(profiles):
                merged = merge_permission_profiles(merged, child)
            return ResolvedPermissionProfileToml(
                profile=merged,
                inherited_profile_names=tuple(profile_names[1:]),
            )


def merge_permission_profiles(
    parent: PermissionProfileToml, child: PermissionProfileToml
) -> PermissionProfileToml:
    if not isinstance(parent, PermissionProfileToml):
        parent = PermissionProfileToml.from_mapping(parent)  # type: ignore[arg-type]
    if not isinstance(child, PermissionProfileToml):
        child = PermissionProfileToml.from_mapping(child)  # type: ignore[arg-type]
    parent_map = parent.to_mapping()
    child_map = child.to_mapping()
    parent_map.pop("description", None)
    parent_map.pop("extends", None)
    if _has_network_domains(parent_map) and _has_network_domains(child_map):
        _normalize_network_domains(parent_map)
        _normalize_network_domains(child_map)
    merged = _deep_merge(parent_map, child_map)
    return PermissionProfileToml.from_mapping(merged)


def _deep_merge(parent: JsonValue, child: JsonValue) -> JsonValue:
    if isinstance(parent, Mapping) and isinstance(child, Mapping):
        merged = dict(parent)
        for key, value in child.items():
            merged[key] = _deep_merge(merged[key], value) if key in merged else value
        return merged
    return child


def _has_network_domains(profile: Mapping[str, JsonValue]) -> bool:
    network = profile.get("network")
    return isinstance(network, Mapping) and isinstance(network.get("domains"), Mapping)


def _normalize_network_domains(profile: Mapping[str, JsonValue]) -> None:
    network = profile.get("network")
    if not isinstance(network, dict):
        return
    domains = network.get("domains")
    if not isinstance(domains, Mapping):
        return
    network["domains"] = {normalize_host(pattern): value for pattern, value in domains.items()}


def _mapping(value: JsonValue, label: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _mapping_or_empty(value: Mapping[str, JsonValue] | None, label: str) -> Mapping[str, JsonValue]:
    if value is None:
        return {}
    return _mapping(value, label)


def _deny_unknown(value: Mapping[str, JsonValue], allowed: set[str], label: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise KeyError(f"{label} has unknown fields: {', '.join(unknown)}")


def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string or None")
    return item


def _optional_bool(value: Mapping[str, JsonValue], key: str) -> bool | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, bool):
        raise TypeError(f"{key} must be a bool or None")
    return item


def _optional_mapping(value: Mapping[str, JsonValue], key: str) -> Mapping[str, JsonValue] | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, Mapping):
        raise TypeError(f"{key} must be a mapping or None")
    return item


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


def _string_tuple(value: JsonValue, label: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise TypeError(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must be a sequence of strings")
    return tuple(value)


def _mapping_sequence(value: JsonValue, label: str) -> tuple[Mapping[str, JsonValue], ...]:
    if value is None:
        return ()
    if isinstance(value, Mapping) or isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise TypeError(f"{label} must be a sequence of mappings")
    if not all(isinstance(item, Mapping) for item in value):
        raise TypeError(f"{label} must be a sequence of mappings")
    return tuple(value)


def _string_multimap(value: JsonValue, label: str) -> Mapping[str, tuple[str, ...]] | None:
    if value is None:
        return None
    data = _mapping(value, label)
    return {str(key): _string_tuple(item, label) for key, item in data.items()}


def _mitm_hooks(value: JsonValue) -> dict[str, NetworkMitmHookToml]:
    data = _mapping(value, "network.mitm.hooks")
    hooks: dict[str, NetworkMitmHookToml] = {}
    for name, hook in data.items():
        if not isinstance(name, str):
            raise TypeError("network.mitm.hooks names must be strings")
        hooks[name] = NetworkMitmHookToml.from_mapping(hook)
    return hooks


def _mitm_actions(value: JsonValue) -> dict[str, NetworkMitmActionToml]:
    data = _mapping(value, "network.mitm.actions")
    actions: dict[str, NetworkMitmActionToml] = {}
    for name, action in data.items():
        if not isinstance(name, str):
            raise TypeError("network.mitm.actions names must be strings")
        actions[name] = NetworkMitmActionToml.from_mapping(action)
    return actions


_PROFILE_FIELDS = {"description", "extends", "workspace_roots", "filesystem", "network"}
_NETWORK_FIELDS = {
    "enabled",
    "proxy_url",
    "enable_socks5",
    "socks_url",
    "enable_socks5_udp",
    "allow_upstream_proxy",
    "dangerously_allow_non_loopback_proxy",
    "dangerously_allow_all_unix_sockets",
    "mode",
    "domains",
    "unix_sockets",
    "allow_local_binding",
    "mitm",
}
_MITM_FIELDS = {"hooks", "actions"}
_MITM_HOOK_FIELDS = {
    "host",
    "methods",
    "path_prefixes",
    "query",
    "headers",
    "body",
    "action",
}
_MITM_ACTION_FIELDS = {"strip_request_headers", "inject_request_headers"}
_MITM_INJECTED_HEADER_FIELDS = {"name", "secret_env_var", "secret_file", "prefix"}


__all__ = [
    "FilesystemPermissionToml",
    "FilesystemPermissionsToml",
    "NetworkDomainPermissionToml",
    "NetworkDomainPermissionsToml",
    "NetworkMitmActionToml",
    "NetworkMitmHookToml",
    "NetworkMitmInjectedHeaderToml",
    "NetworkMitmToml",
    "NetworkToml",
    "NetworkUnixSocketPermissionToml",
    "NetworkUnixSocketPermissionsToml",
    "PermissionProfileCycle",
    "PermissionProfileResolutionError",
    "PermissionProfileToml",
    "PermissionsToml",
    "ResolvedPermissionProfileToml",
    "UndefinedParent",
    "UndefinedProfile",
    "UnsupportedBuiltInParent",
    "WorkspaceRootsToml",
    "merge_permission_profiles",
    "overlay_network_domain_permissions",
]
