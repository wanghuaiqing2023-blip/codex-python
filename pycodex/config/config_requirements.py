"""Requirements TOML data shapes ported from ``codex-config``."""

from __future__ import annotations

import fnmatch
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from . import toml_compat as _toml
from .constraint import Constrained, ConstraintError, RequirementSource
from .hook_config import ManagedHooksRequirementsToml
from .mcp_types import AppToolApproval
from .permissions_toml import PermissionProfileToml
from .requirements_exec_policy import RequirementsExecPolicy, RequirementsExecPolicyToml
from pycodex.protocol.config_types import ApprovalsReviewer, AskForApproval, WebSearchMode
from pycodex.protocol.models import PermissionProfile


JsonValue = Any


@dataclass(frozen=True)
class ConstrainedWithSource:
    value: Constrained
    source: RequirementSource | None = None


@dataclass(frozen=True)
class Sourced:
    value: Any
    source: RequirementSource


@dataclass(frozen=True)
class McpServerIdentity:
    kind: str
    value: str

    @classmethod
    def command(cls, command: str) -> "McpServerIdentity":
        return cls("command", command)

    @classmethod
    def url(cls, url: str) -> "McpServerIdentity":
        return cls("url", url)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "McpServerIdentity":
        has_command = value.get("command") is not None
        has_url = value.get("url") is not None
        if has_command == has_url:
            raise ValueError("MCP server identity requires exactly one of command or url")
        return cls.command(_required_str(value, "command")) if has_command else cls.url(_required_str(value, "url"))


@dataclass(frozen=True)
class McpServerRequirement:
    identity: McpServerIdentity

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "McpServerRequirement":
        identity = value.get("identity")
        if not isinstance(identity, Mapping):
            raise TypeError("mcp server requirement identity must be a table")
        return cls(McpServerIdentity.from_mapping(identity))


@dataclass(frozen=True)
class PluginRequirementsToml:
    mcp_servers: dict[str, McpServerRequirement] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "PluginRequirementsToml":
        value = _mapping_or_empty(value, "PluginRequirementsToml")
        mcp_servers = value.get("mcp_servers")
        if mcp_servers is not None and not isinstance(mcp_servers, Mapping):
            raise TypeError("mcp_servers must be a table")
        return cls(
            mcp_servers={
                str(name): McpServerRequirement.from_mapping(_mapping(server, f"mcp_servers.{name}"))
                for name, server in (mcp_servers or {}).items()
            }
            or None
        )

    def is_empty(self) -> bool:
        return not self.mcp_servers


class NetworkDomainPermissionToml(str, Enum):
    ALLOW = "allow"
    DENY = "deny"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class NetworkDomainPermissionsToml:
    entries: dict[str, NetworkDomainPermissionToml] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "NetworkDomainPermissionsToml":
        value = _mapping_or_empty(value, "NetworkDomainPermissionsToml")
        return cls({str(key): _enum(item, NetworkDomainPermissionToml, str(key)) for key, item in value.items()})

    def is_empty(self) -> bool:
        return not self.entries

    def allowed_domains(self) -> list[str] | None:
        allowed = [pattern for pattern, permission in self.entries.items() if permission is NetworkDomainPermissionToml.ALLOW]
        return allowed or None

    def denied_domains(self) -> list[str] | None:
        denied = [pattern for pattern, permission in self.entries.items() if permission is NetworkDomainPermissionToml.DENY]
        return denied or None


class NetworkUnixSocketPermissionToml(str, Enum):
    ALLOW = "allow"
    NONE = "none"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class NetworkUnixSocketPermissionsToml:
    entries: dict[str, NetworkUnixSocketPermissionToml] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "NetworkUnixSocketPermissionsToml":
        value = _mapping_or_empty(value, "NetworkUnixSocketPermissionsToml")
        return cls({str(key): _enum(item, NetworkUnixSocketPermissionToml, str(key)) for key, item in value.items()})

    def is_empty(self) -> bool:
        return not self.entries

    def allow_unix_sockets(self) -> list[str]:
        return [path for path, permission in self.entries.items() if permission is NetworkUnixSocketPermissionToml.ALLOW]


@dataclass(frozen=True)
class NetworkRequirementsToml:
    enabled: bool | None = None
    http_port: int | None = None
    socks_port: int | None = None
    allow_upstream_proxy: bool | None = None
    dangerously_allow_non_loopback_proxy: bool | None = None
    dangerously_allow_all_unix_sockets: bool | None = None
    domains: NetworkDomainPermissionsToml | None = None
    managed_allowed_domains_only: bool | None = None
    unix_sockets: NetworkUnixSocketPermissionsToml | None = None
    allow_local_binding: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "NetworkRequirementsToml":
        value = _mapping_or_empty(value, "NetworkRequirementsToml")
        domains = value.get("domains")
        allowed_domains = value.get("allowed_domains")
        denied_domains = value.get("denied_domains")
        if domains is not None and (allowed_domains is not None or denied_domains is not None):
            raise ValueError(
                "`experimental_network.domains` cannot be combined with legacy `allowed_domains` or `denied_domains`"
            )
        unix_sockets = value.get("unix_sockets")
        allow_unix_sockets = value.get("allow_unix_sockets")
        if unix_sockets is not None and allow_unix_sockets is not None:
            raise ValueError(
                "`experimental_network.unix_sockets` cannot be combined with legacy `allow_unix_sockets`"
            )
        return cls(
            enabled=_optional_bool(value, "enabled"),
            http_port=_optional_u16(value, "http_port"),
            socks_port=_optional_u16(value, "socks_port"),
            allow_upstream_proxy=_optional_bool(value, "allow_upstream_proxy"),
            dangerously_allow_non_loopback_proxy=_optional_bool(value, "dangerously_allow_non_loopback_proxy"),
            dangerously_allow_all_unix_sockets=_optional_bool(value, "dangerously_allow_all_unix_sockets"),
            domains=NetworkDomainPermissionsToml.from_mapping(domains)
            if isinstance(domains, Mapping)
            else _legacy_domain_permissions_from_lists(allowed_domains, denied_domains),
            managed_allowed_domains_only=_optional_bool(value, "managed_allowed_domains_only"),
            unix_sockets=NetworkUnixSocketPermissionsToml.from_mapping(unix_sockets)
            if isinstance(unix_sockets, Mapping)
            else _legacy_unix_socket_permissions_from_list(allow_unix_sockets),
            allow_local_binding=_optional_bool(value, "allow_local_binding"),
        )


@dataclass(frozen=True)
class NetworkConstraints(NetworkRequirementsToml):
    @classmethod
    def from_requirements(cls, value: NetworkRequirementsToml) -> "NetworkConstraints":
        return cls(**value.__dict__)


@dataclass(frozen=True)
class FilesystemDenyReadPattern:
    value: str

    @classmethod
    def from_input(cls, input_value: str) -> "FilesystemDenyReadPattern":
        if not isinstance(input_value, str):
            raise TypeError("deny_read entries must be strings")
        if not _contains_glob(input_value):
            return cls(str(Path(input_value).resolve(strict=False)))
        prefix, suffix = _split_glob_pattern(input_value)
        normalized_prefix = str(Path(prefix or ".").resolve(strict=False))
        normalized = normalized_prefix if not suffix else str(Path(normalized_prefix) / suffix)
        return cls(normalized)

    def as_str(self) -> str:
        return self.value

    def contains_glob(self) -> bool:
        return _contains_glob(self.value)


@dataclass(frozen=True)
class FilesystemRequirementsToml:
    deny_read: tuple[FilesystemDenyReadPattern, ...] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "FilesystemRequirementsToml":
        value = _mapping_or_empty(value, "FilesystemRequirementsToml")
        forbidden = {"description", "extends", "workspace_roots", "filesystem", "network"}
        if any(key in value for key in forbidden):
            raise ValueError(
                "`permissions.filesystem` is reserved for requirements-level filesystem constraints and cannot define a profile"
            )
        deny_read = value.get("deny_read")
        return cls(
            deny_read=tuple(FilesystemDenyReadPattern.from_input(item) for item in _sequence(deny_read, "deny_read"))
            if deny_read is not None
            else None
        )


@dataclass(frozen=True)
class PermissionsRequirementsToml:
    filesystem: FilesystemRequirementsToml | None = None
    profiles: dict[str, PermissionProfileToml] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "PermissionsRequirementsToml":
        value = _mapping_or_empty(value, "PermissionsRequirementsToml")
        filesystem = value.get("filesystem")
        return cls(
            filesystem=FilesystemRequirementsToml.from_mapping(filesystem) if isinstance(filesystem, Mapping) else None,
            profiles={
                str(key): item if isinstance(item, PermissionProfileToml) else PermissionProfileToml.from_mapping(_mapping(item, str(key)))
                for key, item in value.items()
                if key != "filesystem"
            },
        )


@dataclass(frozen=True)
class FilesystemConstraints:
    deny_read: tuple[FilesystemDenyReadPattern, ...] = ()

    @classmethod
    def from_permissions(cls, value: PermissionsRequirementsToml) -> "FilesystemConstraints":
        return cls(value.filesystem.deny_read or () if value.filesystem is not None else ())


class WebSearchModeRequirement(str, Enum):
    DISABLED = "disabled"
    CACHED = "cached"
    LIVE = "live"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ComputerUseRequirementsToml:
    allow_locked_computer_use: bool | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ComputerUseRequirementsToml":
        value = _mapping_or_empty(value, "ComputerUseRequirementsToml")
        return cls(_optional_bool(value, "allow_locked_computer_use"))

    def is_empty(self) -> bool:
        return self.allow_locked_computer_use is None


@dataclass(frozen=True)
class FeatureRequirementsToml:
    entries: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "FeatureRequirementsToml":
        value = _mapping_or_empty(value, "FeatureRequirementsToml")
        return cls({str(key): _bool(item, str(key)) for key, item in value.items()})

    def is_empty(self) -> bool:
        return not self.entries


@dataclass(frozen=True)
class AppToolRequirementToml:
    approval_mode: AppToolApproval | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppToolRequirementToml":
        value = _mapping_or_empty(value, "AppToolRequirementToml")
        approval = value.get("approval_mode")
        return cls(AppToolApproval.from_value(approval) if approval is not None else None)

    def is_empty(self) -> bool:
        return self.approval_mode is None


@dataclass(frozen=True)
class AppToolsRequirementsToml:
    tools: dict[str, AppToolRequirementToml] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppToolsRequirementsToml":
        value = _mapping_or_empty(value, "AppToolsRequirementsToml")
        return cls({str(key): AppToolRequirementToml.from_mapping(_mapping(item, str(key))) for key, item in value.items()})

    def is_empty(self) -> bool:
        return all(tool.is_empty() for tool in self.tools.values())


@dataclass(frozen=True)
class AppRequirementToml:
    enabled: bool | None = None
    tools: AppToolsRequirementsToml | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppRequirementToml":
        value = _mapping_or_empty(value, "AppRequirementToml")
        tools = value.get("tools")
        return cls(
            enabled=_optional_bool(value, "enabled"),
            tools=AppToolsRequirementsToml.from_mapping(tools) if isinstance(tools, Mapping) else None,
        )

    def is_empty(self) -> bool:
        return self.enabled is None and (self.tools is None or self.tools.is_empty())


@dataclass(frozen=True)
class AppsRequirementsToml:
    apps: dict[str, AppRequirementToml] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "AppsRequirementsToml":
        value = _mapping_or_empty(value, "AppsRequirementsToml")
        return cls({str(key): AppRequirementToml.from_mapping(_mapping(item, str(key))) for key, item in value.items()})

    def is_empty(self) -> bool:
        return all(app.is_empty() for app in self.apps.values())


def merge_app_requirements_descending(base: AppsRequirementsToml, incoming: AppsRequirementsToml) -> AppsRequirementsToml:
    merged = {name: AppRequirementToml(app.enabled, app.tools) for name, app in base.apps.items()}
    for app_id, incoming_requirement in incoming.apps.items():
        current = merged.get(app_id, AppRequirementToml())
        enabled = False if current.enabled is False or incoming_requirement.enabled is False else current.enabled if current.enabled is not None else incoming_requirement.enabled
        tools = current.tools or AppToolsRequirementsToml()
        if incoming_requirement.tools is not None:
            tool_map = dict(tools.tools)
            for tool_name, incoming_tool in incoming_requirement.tools.tools.items():
                current_tool = tool_map.get(tool_name, AppToolRequirementToml())
                if current_tool.approval_mode is None:
                    current_tool = AppToolRequirementToml(incoming_tool.approval_mode)
                tool_map[tool_name] = current_tool
            tools = AppToolsRequirementsToml(tool_map)
        merged[app_id] = AppRequirementToml(enabled, tools if tools.tools else current.tools)
    return AppsRequirementsToml(merged)


class SandboxModeRequirement(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"
    EXTERNAL_SANDBOX = "external-sandbox"


class ResidencyRequirement(str, Enum):
    US = "us"


@dataclass(frozen=True)
class RemoteSandboxConfigToml:
    hostname_patterns: tuple[str, ...]
    allowed_sandbox_modes: tuple[SandboxModeRequirement, ...]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RemoteSandboxConfigToml":
        return cls(
            hostname_patterns=tuple(_sequence(value.get("hostname_patterns"), "hostname_patterns")),
            allowed_sandbox_modes=tuple(_enum(item, SandboxModeRequirement, "allowed_sandbox_modes") for item in _sequence(value.get("allowed_sandbox_modes"), "allowed_sandbox_modes")),
        )


@dataclass
class ConfigRequirementsToml:
    allowed_approval_policies: tuple[AskForApproval, ...] | None = None
    allowed_approvals_reviewers: tuple[ApprovalsReviewer, ...] | None = None
    allowed_sandbox_modes: tuple[SandboxModeRequirement, ...] | None = None
    allowed_permissions: tuple[str, ...] | None = None
    remote_sandbox_config: tuple[RemoteSandboxConfigToml, ...] | None = None
    allowed_web_search_modes: tuple[WebSearchModeRequirement, ...] | None = None
    allow_managed_hooks_only: bool | None = None
    allow_appshots: bool | None = None
    computer_use: ComputerUseRequirementsToml | None = None
    feature_requirements: FeatureRequirementsToml | None = None
    hooks: ManagedHooksRequirementsToml | None = None
    mcp_servers: dict[str, McpServerRequirement] | None = None
    plugins: dict[str, PluginRequirementsToml] | None = None
    apps: AppsRequirementsToml | None = None
    rules: RequirementsExecPolicyToml | None = None
    enforce_residency: ResidencyRequirement | None = None
    network: NetworkRequirementsToml | None = None
    permissions: PermissionsRequirementsToml | None = None
    guardian_policy_config: str | None = None

    @classmethod
    def from_toml(cls, contents: str) -> "ConfigRequirementsToml":
        return cls.from_mapping(_toml.loads(contents))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "ConfigRequirementsToml":
        value = _mapping_or_empty(value, "ConfigRequirementsToml")
        features = value.get("features", value.get("feature_requirements"))
        return cls(
            allowed_approval_policies=_optional_protocol_enum_tuple(value, "allowed_approval_policies", AskForApproval),
            allowed_approvals_reviewers=_optional_protocol_enum_tuple(value, "allowed_approvals_reviewers", ApprovalsReviewer),
            allowed_sandbox_modes=_optional_enum_tuple(value, "allowed_sandbox_modes", SandboxModeRequirement),
            allowed_permissions=_optional_str_tuple(value, "allowed_permissions"),
            remote_sandbox_config=tuple(RemoteSandboxConfigToml.from_mapping(_mapping(item, "remote_sandbox_config")) for item in _sequence_of_mapping(value.get("remote_sandbox_config"), "remote_sandbox_config")) or None,
            allowed_web_search_modes=_optional_enum_tuple(value, "allowed_web_search_modes", WebSearchModeRequirement),
            allow_managed_hooks_only=_optional_bool(value, "allow_managed_hooks_only"),
            allow_appshots=_optional_bool(value, "allow_appshots"),
            computer_use=ComputerUseRequirementsToml.from_mapping(value["computer_use"]) if isinstance(value.get("computer_use"), Mapping) else None,
            feature_requirements=FeatureRequirementsToml.from_mapping(features) if isinstance(features, Mapping) else None,
            hooks=ManagedHooksRequirementsToml.from_mapping(value["hooks"]) if isinstance(value.get("hooks"), Mapping) else None,
            mcp_servers=_mcp_servers_from_mapping(value.get("mcp_servers")),
            plugins=_plugins_from_mapping(value.get("plugins")),
            apps=AppsRequirementsToml.from_mapping(value["apps"]) if isinstance(value.get("apps"), Mapping) else None,
            rules=RequirementsExecPolicyToml.from_mapping(value["rules"]) if isinstance(value.get("rules"), Mapping) else None,
            enforce_residency=_optional_enum(value, "enforce_residency", ResidencyRequirement),
            network=NetworkRequirementsToml.from_mapping(value["experimental_network"]) if isinstance(value.get("experimental_network"), Mapping) else None,
            permissions=PermissionsRequirementsToml.from_mapping(value["permissions"]) if isinstance(value.get("permissions"), Mapping) else None,
            guardian_policy_config=_optional_str(value, "guardian_policy_config"),
        )

    def apply_remote_sandbox_config(self, hostname: str | None) -> None:
        if not self.remote_sandbox_config or hostname is None:
            return
        normalized = _normalize_hostname(hostname)
        if normalized is None:
            return
        for config in self.remote_sandbox_config:
            if any(_hostname_matches(normalized, pattern) for pattern in config.hostname_patterns):
                self.allowed_sandbox_modes = config.allowed_sandbox_modes
                return

    def is_empty(self) -> bool:
        return (
            self.allowed_approval_policies is None
            and self.allowed_approvals_reviewers is None
            and self.allowed_sandbox_modes is None
            and self.allowed_permissions is None
            and self.remote_sandbox_config is None
            and self.allowed_web_search_modes is None
            and self.allow_managed_hooks_only is None
            and self.allow_appshots is None
            and (self.computer_use is None or self.computer_use.is_empty())
            and (self.feature_requirements is None or self.feature_requirements.is_empty())
            and (self.hooks is None or self.hooks.is_empty())
            and self.mcp_servers is None
            and (self.plugins is None or all(plugin.is_empty() for plugin in self.plugins.values()))
            and (self.apps is None or self.apps.is_empty())
            and self.rules is None
            and self.enforce_residency is None
            and self.network is None
            and self.permissions is None
            and (self.guardian_policy_config is None or not self.guardian_policy_config.strip())
        )


@dataclass
class ConfigRequirementsWithSources:
    allowed_approval_policies: Sourced | None = None
    allowed_approvals_reviewers: Sourced | None = None
    allowed_sandbox_modes: Sourced | None = None
    allowed_permissions: Sourced | None = None
    allowed_web_search_modes: Sourced | None = None
    allow_managed_hooks_only: Sourced | None = None
    allow_appshots: Sourced | None = None
    computer_use: Sourced | None = None
    feature_requirements: Sourced | None = None
    hooks: Sourced | None = None
    mcp_servers: Sourced | None = None
    plugins: Sourced | None = None
    apps: Sourced | None = None
    rules: Sourced | None = None
    enforce_residency: Sourced | None = None
    network: Sourced | None = None
    permissions: Sourced | None = None
    guardian_policy_config: Sourced | None = None

    def merge_unset_fields(self, source: RequirementSource, other: ConfigRequirementsToml) -> None:
        if other.guardian_policy_config is not None and not other.guardian_policy_config.strip():
            other.guardian_policy_config = None

        for field_name in (
            "allowed_approval_policies",
            "allowed_approvals_reviewers",
            "allowed_sandbox_modes",
            "allowed_permissions",
            "allowed_web_search_modes",
            "allow_managed_hooks_only",
            "allow_appshots",
            "computer_use",
            "feature_requirements",
            "hooks",
            "mcp_servers",
            "plugins",
            "rules",
            "enforce_residency",
            "network",
            "permissions",
            "guardian_policy_config",
        ):
            if getattr(self, field_name) is None:
                value = getattr(other, field_name)
                if value is not None:
                    setattr(self, field_name, Sourced(value, source))

        if other.apps is not None:
            if self.apps is None:
                self.apps = Sourced(other.apps, source)
            else:
                self.apps = Sourced(
                    merge_app_requirements_descending(self.apps.value, other.apps),
                    self.apps.source,
                )

    def into_toml(self) -> ConfigRequirementsToml:
        return ConfigRequirementsToml(
            allowed_approval_policies=_sourced_value(self.allowed_approval_policies),
            allowed_approvals_reviewers=_sourced_value(self.allowed_approvals_reviewers),
            allowed_sandbox_modes=_sourced_value(self.allowed_sandbox_modes),
            allowed_permissions=_sourced_value(self.allowed_permissions),
            remote_sandbox_config=None,
            allowed_web_search_modes=_sourced_value(self.allowed_web_search_modes),
            allow_managed_hooks_only=_sourced_value(self.allow_managed_hooks_only),
            allow_appshots=_sourced_value(self.allow_appshots),
            computer_use=_sourced_value(self.computer_use),
            feature_requirements=_sourced_value(self.feature_requirements),
            hooks=_sourced_value(self.hooks),
            mcp_servers=_sourced_value(self.mcp_servers),
            plugins=_sourced_value(self.plugins),
            apps=_sourced_value(self.apps),
            rules=_sourced_value(self.rules),
            enforce_residency=_sourced_value(self.enforce_residency),
            network=_sourced_value(self.network),
            permissions=_sourced_value(self.permissions),
            guardian_policy_config=_sourced_value(self.guardian_policy_config),
        )


@dataclass(frozen=True)
class ConfigRequirements:
    approval_policy: ConstrainedWithSource
    approvals_reviewer: ConstrainedWithSource
    permission_profile: ConstrainedWithSource
    web_search_mode: ConstrainedWithSource
    enforce_residency: ConstrainedWithSource
    allow_managed_hooks_only: Sourced | None = None
    allow_appshots: Sourced | None = None
    computer_use: Sourced | None = None
    feature_requirements: Sourced | None = None
    managed_hooks: ConstrainedWithSource | None = None
    mcp_servers: Sourced | None = None
    plugins: Sourced | None = None
    exec_policy: Sourced | None = None
    network: Sourced | None = None
    filesystem: Sourced | None = None
    guardian_policy_config_source: RequirementSource | None = None

    @classmethod
    def default(cls) -> "ConfigRequirements":
        return cls(
            approval_policy=ConstrainedWithSource(Constrained.allow_any_from_default(), None),
            approvals_reviewer=ConstrainedWithSource(Constrained.allow_any_from_default(), None),
            permission_profile=ConstrainedWithSource(Constrained.allow_any(PermissionProfile.read_only()), None),
            web_search_mode=ConstrainedWithSource(Constrained.allow_any(WebSearchMode.CACHED), None),
            enforce_residency=ConstrainedWithSource(Constrained.allow_any(None), None),
        )

    @classmethod
    def from_sources(cls, sources: ConfigRequirementsWithSources) -> "ConfigRequirements":
        defaults = cls.default()
        approval_policy = _constrained_members(
            sources.allowed_approval_policies,
            "allowed_approval_policies",
            "approval_policy",
            defaults.approval_policy,
        )
        approvals_reviewer = _constrained_members(
            sources.allowed_approvals_reviewers,
            "allowed_approvals_reviewers",
            "approvals_reviewer",
            defaults.approvals_reviewer,
        )
        permission_profile = _constrained_permission_profile(
            sources.allowed_sandbox_modes,
            defaults.permission_profile,
        )
        web_search_mode = _constrained_web_search(sources.allowed_web_search_modes, defaults.web_search_mode)
        enforce_residency = _constrained_exact_optional(
            sources.enforce_residency,
            "enforce_residency",
            defaults.enforce_residency,
        )
        network = (
            Sourced(NetworkConstraints.from_requirements(sources.network.value), sources.network.source)
            if sources.network is not None
            else None
        )
        filesystem = (
            Sourced(FilesystemConstraints.from_permissions(sources.permissions.value), sources.permissions.source)
            if sources.permissions is not None
            else None
        )
        exec_policy = _exec_policy_from_rules(sources.rules)
        managed_hooks = _constrained_managed_hooks(sources.hooks)
        return cls(
            approval_policy=approval_policy,
            approvals_reviewer=approvals_reviewer,
            permission_profile=permission_profile,
            web_search_mode=web_search_mode,
            enforce_residency=enforce_residency,
            allow_managed_hooks_only=sources.allow_managed_hooks_only,
            allow_appshots=sources.allow_appshots,
            computer_use=sources.computer_use,
            feature_requirements=sources.feature_requirements if sources.feature_requirements is None or not sources.feature_requirements.value.is_empty() else None,
            managed_hooks=managed_hooks,
            mcp_servers=sources.mcp_servers,
            plugins=sources.plugins,
            exec_policy=exec_policy,
            network=network,
            filesystem=filesystem,
            guardian_policy_config_source=sources.guardian_policy_config.source if sources.guardian_policy_config is not None else None,
        )

    def exec_policy_source(self) -> RequirementSource | None:
        return self.exec_policy.source if self.exec_policy is not None else None


def _legacy_domain_permissions_from_lists(allowed_domains: Any, denied_domains: Any) -> NetworkDomainPermissionsToml | None:
    entries: dict[str, NetworkDomainPermissionToml] = {}
    for pattern in _sequence_or_empty(allowed_domains, "allowed_domains"):
        entries[pattern] = NetworkDomainPermissionToml.ALLOW
    for pattern in _sequence_or_empty(denied_domains, "denied_domains"):
        entries[pattern] = NetworkDomainPermissionToml.DENY
    return NetworkDomainPermissionsToml(entries) if entries else None


def _legacy_unix_socket_permissions_from_list(value: Any) -> NetworkUnixSocketPermissionsToml | None:
    entries = {path: NetworkUnixSocketPermissionToml.ALLOW for path in _sequence_or_empty(value, "allow_unix_sockets")}
    return NetworkUnixSocketPermissionsToml(entries) if entries else None


def _mcp_servers_from_mapping(value: Any) -> dict[str, McpServerRequirement] | None:
    if value is None:
        return None
    mapping = _mapping(value, "mcp_servers")
    return {str(name): McpServerRequirement.from_mapping(_mapping(server, str(name))) for name, server in mapping.items()}


def _plugins_from_mapping(value: Any) -> dict[str, PluginRequirementsToml] | None:
    if value is None:
        return None
    mapping = _mapping(value, "plugins")
    return {str(name): PluginRequirementsToml.from_mapping(_mapping(plugin, str(name))) for name, plugin in mapping.items()}


def _contains_glob(value: str) -> bool:
    return any(ch in value for ch in "*?[")


def _split_glob_pattern(value: str) -> tuple[str, str]:
    first = min((idx for idx, ch in enumerate(value) if ch in "*?["), default=-1)
    if first < 0:
        return "", value
    prefix = value[:first]
    sep = max(prefix.rfind("/"), prefix.rfind("\\"))
    if sep < 0:
        return "", value
    if sep == 0:
        return "/", value[1:]
    return value[:sep], value[sep + 1 :]


def _normalize_hostname(hostname: str) -> str | None:
    normalized = hostname.strip().rstrip(".").lower()
    return normalized or None


def _hostname_matches(hostname: str, pattern: str) -> bool:
    normalized = _normalize_hostname(pattern)
    return bool(normalized and fnmatch.fnmatchcase(hostname.lower(), normalized.lower()))


def _constrained_members(
    sourced: Sourced | None,
    source_field_name: str,
    target_field_name: str,
    default: ConstrainedWithSource,
) -> ConstrainedWithSource:
    if sourced is None:
        return default
    allowed = tuple(sourced.value)
    if not allowed:
        raise ConstraintError.empty_field(source_field_name)
    source = sourced.source

    def validate(candidate: Any) -> None:
        if candidate in allowed:
            return
        raise ConstraintError.invalid_value(
            field_name=target_field_name,
            candidate=repr(candidate),
            allowed=repr(list(allowed)),
            requirement_source=source,
        )

    return ConstrainedWithSource(Constrained.new(allowed[0], validate), source)


def _constrained_web_search(
    sourced: Sourced | None,
    default: ConstrainedWithSource,
) -> ConstrainedWithSource:
    if sourced is None:
        return default
    accepted_requirements = set(sourced.value)
    accepted_requirements.add(WebSearchModeRequirement.DISABLED)
    if WebSearchModeRequirement.CACHED in accepted_requirements:
        initial = WebSearchMode.CACHED
    elif WebSearchModeRequirement.LIVE in accepted_requirements:
        initial = WebSearchMode.LIVE
    else:
        initial = WebSearchMode.DISABLED
    accepted_modes = {_web_search_mode_from_requirement(item) for item in accepted_requirements}
    source = sourced.source

    def validate(candidate: WebSearchMode) -> None:
        if candidate in accepted_modes:
            return
        raise ConstraintError.invalid_value(
            field_name="web_search_mode",
            candidate=repr(candidate),
            allowed=repr(sorted(mode.value for mode in accepted_modes)),
            requirement_source=source,
        )

    return ConstrainedWithSource(Constrained.new(initial, validate), source)


def _constrained_permission_profile(
    sourced: Sourced | None,
    default: ConstrainedWithSource,
) -> ConstrainedWithSource:
    if sourced is None:
        return default
    allowed = tuple(sourced.value)
    source = sourced.source
    if SandboxModeRequirement.READ_ONLY not in allowed:
        raise ConstraintError.invalid_value(
            field_name="allowed_sandbox_modes",
            candidate=repr(list(allowed)),
            allowed="must include 'read-only' to allow any PermissionProfile",
            requirement_source=source,
        )

    def validate(candidate: PermissionProfile) -> None:
        mode = sandbox_mode_requirement_for_permission_profile(candidate)
        if mode in allowed:
            return
        raise ConstraintError.invalid_value(
            field_name="sandbox_mode",
            candidate=repr(mode),
            allowed=repr(list(allowed)),
            requirement_source=source,
        )

    return ConstrainedWithSource(Constrained.new(PermissionProfile.read_only(), validate), source)


def sandbox_mode_requirement_for_permission_profile(
    permission_profile: PermissionProfile,
) -> SandboxModeRequirement:
    if permission_profile.type == "disabled":
        return SandboxModeRequirement.DANGER_FULL_ACCESS
    if permission_profile.type == "external":
        return SandboxModeRequirement.EXTERNAL_SANDBOX
    file_system_policy = permission_profile.file_system_sandbox_policy()
    if file_system_policy.has_full_disk_write_access():
        return SandboxModeRequirement.DANGER_FULL_ACCESS
    if any(entry.access.can_write() for entry in file_system_policy.entries):
        return SandboxModeRequirement.WORKSPACE_WRITE
    return SandboxModeRequirement.READ_ONLY


def _exec_policy_from_rules(sourced: Sourced | None) -> Sourced | None:
    if sourced is None:
        return None
    try:
        policy = sourced.value.to_requirements_policy()
    except ValueError as exc:
        raise ConstraintError.exec_policy_parse(
            requirement_source=sourced.source,
            reason=str(exc),
        ) from exc
    if not isinstance(policy, RequirementsExecPolicy):
        raise TypeError("rules.to_requirements_policy() must return RequirementsExecPolicy")
    return Sourced(policy, sourced.source)


def _constrained_managed_hooks(sourced: Sourced | None) -> ConstrainedWithSource | None:
    if sourced is None or sourced.value.handler_count() <= 0:
        return None
    allowed = sourced.value
    source = sourced.source

    def validate(candidate: ManagedHooksRequirementsToml) -> None:
        if candidate == allowed:
            return
        raise ConstraintError.invalid_value(
            field_name="hooks",
            candidate=repr(candidate),
            allowed=repr(allowed),
            requirement_source=source,
        )

    return ConstrainedWithSource(Constrained.new(allowed, validate), source)


def _constrained_exact_optional(
    sourced: Sourced | None,
    field_name: str,
    default: ConstrainedWithSource,
) -> ConstrainedWithSource:
    if sourced is None:
        return default
    required = sourced.value
    source = sourced.source

    def validate(candidate: Any) -> None:
        if candidate == required:
            return
        raise ConstraintError.invalid_value(
            field_name=field_name,
            candidate=repr(candidate),
            allowed=repr(required),
            requirement_source=source,
        )

    return ConstrainedWithSource(Constrained.new(required, validate), source)


def _web_search_mode_from_requirement(value: WebSearchModeRequirement) -> WebSearchMode:
    if value is WebSearchModeRequirement.DISABLED:
        return WebSearchMode.DISABLED
    if value is WebSearchModeRequirement.LIVE:
        return WebSearchMode.LIVE
    return WebSearchMode.CACHED


def _mapping_or_empty(value: Mapping[str, Any] | None, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    return _mapping(value, name)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a table")
    return value


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")
    return value


def _optional_bool(value: Mapping[str, Any], key: str) -> bool | None:
    return _bool(value[key], key) if key in value and value[key] is not None else None


def _optional_str(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


def _required_str(value: Mapping[str, Any], key: str) -> str:
    item = _optional_str(value, key)
    if item is None:
        raise ValueError(f"{key} is required")
    return item


def _optional_u16(value: Mapping[str, Any], key: str) -> int | None:
    item = value.get(key)
    if item is None:
        return None
    if isinstance(item, bool) or not isinstance(item, int) or item < 0 or item > 65535:
        raise TypeError(f"{key} must be a u16")
    return item


def _enum(value: Any, enum_type: type[Enum], name: str) -> Any:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return enum_type(value)


def _optional_enum(value: Mapping[str, Any], key: str, enum_type: type[Enum]) -> Any | None:
    return _enum(value[key], enum_type, key) if key in value and value[key] is not None else None


def _optional_enum_tuple(value: Mapping[str, Any], key: str, enum_type: type[Enum]) -> tuple[Any, ...] | None:
    if value.get(key) is None:
        return None
    return tuple(_enum(item, enum_type, key) for item in _sequence(value[key], key))


def _optional_protocol_enum_tuple(value: Mapping[str, Any], key: str, enum_type: Any) -> tuple[Any, ...] | None:
    if value.get(key) is None:
        return None
    return tuple(enum_type.parse(item) if hasattr(enum_type, "parse") else enum_type(item) for item in _sequence(value[key], key))


def _optional_str_tuple(value: Mapping[str, Any], key: str) -> tuple[str, ...] | None:
    if value.get(key) is None:
        return None
    return _sequence(value[key], key)


def _sourced_value(value: Sourced | None) -> Any:
    return value.value if value is not None else None


def _sequence(value: Any, name: str) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be an array")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{name} entries must be strings")
    return tuple(value)


def _sequence_or_empty(value: Any, name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    return _sequence(value, name)


def _sequence_of_mapping(value: Any, name: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise TypeError(f"{name} must be an array")
    return tuple(_mapping(item, name) for item in value)


__all__ = [
    "AppRequirementToml",
    "AppToolRequirementToml",
    "AppToolsRequirementsToml",
    "AppsRequirementsToml",
    "ComputerUseRequirementsToml",
    "ConfigRequirements",
    "ConfigRequirementsToml",
    "ConfigRequirementsWithSources",
    "ConstrainedWithSource",
    "FeatureRequirementsToml",
    "FilesystemConstraints",
    "FilesystemDenyReadPattern",
    "FilesystemRequirementsToml",
    "McpServerIdentity",
    "McpServerRequirement",
    "NetworkConstraints",
    "NetworkDomainPermissionToml",
    "NetworkDomainPermissionsToml",
    "NetworkRequirementsToml",
    "NetworkUnixSocketPermissionToml",
    "NetworkUnixSocketPermissionsToml",
    "PermissionsRequirementsToml",
    "PluginRequirementsToml",
    "RemoteSandboxConfigToml",
    "RequirementSource",
    "ResidencyRequirement",
    "SandboxModeRequirement",
    "Sourced",
    "WebSearchModeRequirement",
    "merge_app_requirements_descending",
    "sandbox_mode_requirement_for_permission_profile",
]
