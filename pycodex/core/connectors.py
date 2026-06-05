"""Connector discovery helpers ported from Codex core.

This is the standard-library slice of ``core/src/connectors.rs`` and
``codex-rs/connectors`` that does not require auth, network, or MCP manager
runtime services: collect accessible connector metadata from MCP tools, build
ChatGPT install URLs, merge plugin connector placeholders, and apply app
enabled-state and tool-policy constraints.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.core.tools.handlers.mcp import ToolInfo
from pycodex.core.tools.handlers.request_plugin_install import CODEX_APPS_MCP_SERVER_NAME
from pycodex.tools.tool_discovery import AppInfo
from pycodex.connectors.accessible import (
    AccessibleConnectorTool as _AccessibleConnectorTool,
    collect_accessible_connectors as _collect_accessible_connectors,
)
from pycodex.connectors.metadata import (
    coerce_app_info as _coerce_app_info,
    replace_app_info as _replace_app_info,
)

JsonValue = Any


class AppToolApproval(str, Enum):
    AUTO = "auto"
    PROMPT = "prompt"
    APPROVE = "approve"




@dataclass(frozen=True)
class ToolAnnotations:
    destructive_hint: bool | None = None
    open_world_hint: bool | None = None
    read_only_hint: bool | None = None

    @classmethod
    def from_value(cls, value: JsonValue) -> "ToolAnnotations | None":
        if value is None:
            return None
        if isinstance(value, ToolAnnotations):
            return value
        if not isinstance(value, Mapping):
            return cls(
                destructive_hint=_optional_bool(getattr(value, "destructive_hint", None)),
                open_world_hint=_optional_bool(getattr(value, "open_world_hint", None)),
                read_only_hint=_optional_bool(getattr(value, "read_only_hint", None)),
            )
        return cls(
            destructive_hint=_optional_bool(
                value.get("destructiveHint", value.get("destructive_hint"))
            ),
            open_world_hint=_optional_bool(value.get("openWorldHint", value.get("open_world_hint"))),
            read_only_hint=_optional_bool(value.get("readOnlyHint", value.get("read_only_hint"))),
        )


@dataclass(frozen=True)
class AppToolPolicy:
    enabled: bool = True
    approval: AppToolApproval = AppToolApproval.AUTO

    def __post_init__(self) -> None:
        object.__setattr__(self, "approval", _app_tool_approval_or_default(self.approval))


@dataclass(frozen=True)
class AppToolConfig:
    enabled: bool | None = None
    approval_mode: AppToolApproval | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "enabled", _optional_bool(self.enabled))
        object.__setattr__(
            self,
            "approval_mode",
            _optional_app_tool_approval(self.approval_mode),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppToolConfig":
        if value is None:
            return cls()
        return cls(
            enabled=_optional_bool(value.get("enabled")),
            approval_mode=_optional_app_tool_approval(value.get("approval_mode")),
        )


@dataclass(frozen=True)
class AppToolsConfig:
    tools: Mapping[str, AppToolConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tools",
            {
                str(name): _coerce_app_tool_config(tool_config)
                for name, tool_config in self.tools.items()
            },
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppToolsConfig | None":
        if value is None:
            return None
        if isinstance(value, AppToolsConfig):
            return value
        return cls(
            {
                str(name): _coerce_app_tool_config(tool_config)
                for name, tool_config in value.items()
                if isinstance(tool_config, Mapping | AppToolConfig)
            }
        )


@dataclass(frozen=True)
class AppsDefaultConfig:
    enabled: bool = True
    destructive_enabled: bool = True
    open_world_enabled: bool = True

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppsDefaultConfig | None":
        if value is None:
            return None
        return cls(
            enabled=bool(value.get("enabled", True)),
            destructive_enabled=bool(value.get("destructive_enabled", True)),
            open_world_enabled=bool(value.get("open_world_enabled", True)),
        )


@dataclass(frozen=True)
class AppConfig:
    enabled: bool = True
    destructive_enabled: bool | None = None
    open_world_enabled: bool | None = None
    default_tools_approval_mode: AppToolApproval | None = None
    default_tools_enabled: bool | None = None
    tools: AppToolsConfig | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "default_tools_approval_mode",
            _optional_app_tool_approval(self.default_tools_approval_mode),
        )
        if self.tools is not None and not isinstance(self.tools, AppToolsConfig):
            object.__setattr__(self, "tools", AppToolsConfig.from_mapping(self.tools))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppConfig":
        if value is None:
            return cls()
        return cls(
            enabled=bool(value.get("enabled", True)),
            destructive_enabled=_optional_bool(value.get("destructive_enabled")),
            open_world_enabled=_optional_bool(value.get("open_world_enabled")),
            default_tools_approval_mode=_optional_app_tool_approval(
                value.get("default_tools_approval_mode")
            ),
            default_tools_enabled=_optional_bool(value.get("default_tools_enabled")),
            tools=AppToolsConfig.from_mapping(value.get("tools"))
            if isinstance(value.get("tools"), Mapping)
            else None,
        )

    def with_enabled(self, enabled: bool) -> "AppConfig":
        return AppConfig(
            enabled=enabled,
            destructive_enabled=self.destructive_enabled,
            open_world_enabled=self.open_world_enabled,
            default_tools_approval_mode=self.default_tools_approval_mode,
            default_tools_enabled=self.default_tools_enabled,
            tools=self.tools,
        )


@dataclass(frozen=True)
class AppsConfig:
    default: AppsDefaultConfig | None = None
    apps: Mapping[str, AppConfig] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "apps",
            {
                str(app_id): app_config
                if isinstance(app_config, AppConfig)
                else AppConfig.from_mapping(app_config)
                for app_id, app_config in self.apps.items()
                if isinstance(app_config, Mapping | AppConfig)
            },
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppsConfig | None":
        if value is None:
            return None
        if not isinstance(value, Mapping):
            return None
        raw_apps = value.get("apps", {})
        if not isinstance(raw_apps, Mapping):
            raw_apps = {}
        raw_default = value.get("_default", value.get("default"))
        return cls(
            default=AppsDefaultConfig.from_mapping(
                raw_default if isinstance(raw_default, Mapping) else None
            ),
            apps={
                str(app_id): AppConfig.from_mapping(app_config)
                for app_id, app_config in raw_apps.items()
                if isinstance(app_config, Mapping)
            },
        )

    def has_effective_state(self) -> bool:
        return self.default is not None or bool(self.apps)

    def with_app(self, app_id: str, app: AppConfig) -> "AppsConfig":
        apps = dict(self.apps)
        apps[app_id] = app
        return AppsConfig(default=self.default, apps=apps)


@dataclass(frozen=True)
class AppToolRequirement:
    approval_mode: AppToolApproval | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approval_mode",
            _optional_app_tool_approval(self.approval_mode),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppToolRequirement":
        if value is None:
            return cls()
        return cls(approval_mode=_optional_app_tool_approval(value.get("approval_mode")))


@dataclass(frozen=True)
class AppToolsRequirements:
    tools: Mapping[str, AppToolRequirement] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tools",
            {
                str(name): tool_requirement
                if isinstance(tool_requirement, AppToolRequirement)
                else AppToolRequirement.from_mapping(tool_requirement)
                for name, tool_requirement in self.tools.items()
                if isinstance(tool_requirement, Mapping | AppToolRequirement)
            },
        )

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue] | None
    ) -> "AppToolsRequirements | None":
        if value is None:
            return None
        if isinstance(value, AppToolsRequirements):
            return value
        return cls(
            {
                str(name): tool_requirement
                if isinstance(tool_requirement, AppToolRequirement)
                else AppToolRequirement.from_mapping(tool_requirement)
                for name, tool_requirement in value.items()
                if isinstance(tool_requirement, Mapping | AppToolRequirement)
            }
        )


@dataclass(frozen=True)
class AppRequirement:
    enabled: bool | None = None
    tools: AppToolsRequirements | None = None

    def __post_init__(self) -> None:
        if self.tools is not None and not isinstance(self.tools, AppToolsRequirements):
            object.__setattr__(self, "tools", AppToolsRequirements.from_mapping(self.tools))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppRequirement":
        if value is None:
            return cls()
        return cls(
            enabled=_optional_bool(value.get("enabled")),
            tools=AppToolsRequirements.from_mapping(value.get("tools"))
            if isinstance(value.get("tools"), Mapping)
            else None,
        )


@dataclass(frozen=True)
class AppsRequirements:
    apps: Mapping[str, AppRequirement] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "apps",
            {
                str(app_id): app_requirement
                if isinstance(app_requirement, AppRequirement)
                else AppRequirement.from_mapping(app_requirement)
                for app_id, app_requirement in self.apps.items()
                if isinstance(app_requirement, Mapping | AppRequirement)
            },
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None) -> "AppsRequirements | None":
        if value is None:
            return None
        if not isinstance(value, Mapping):
            return None
        raw_apps = value.get("apps", value)
        if not isinstance(raw_apps, Mapping):
            return cls()
        return cls(
            apps={
                str(app_id): AppRequirement.from_mapping(app_requirement)
                for app_id, app_requirement in raw_apps.items()
                if isinstance(app_requirement, Mapping)
            }
        )












def accessible_connectors_from_mcp_tools(
    mcp_tools: Iterable[ToolInfo | Mapping[str, JsonValue]],
) -> list[AppInfo]:
    connector_tools = []
    for raw_tool in mcp_tools:
        tool = raw_tool if isinstance(raw_tool, ToolInfo) else ToolInfo.from_mapping(raw_tool)
        if tool.server_name != CODEX_APPS_MCP_SERVER_NAME:
            continue
        if tool.connector_id is None:
            continue
        connector_tools.append(
            _AccessibleConnectorTool(
                connector_id=tool.connector_id,
                connector_name=tool.connector_name,
                connector_description=tool.namespace_description,
                plugin_display_names=tool.plugin_display_names,
            )
        )
    return _collect_accessible_connectors(connector_tools)








def app_is_enabled(apps_config: AppsConfig | Mapping[str, JsonValue], connector_id: str | None) -> bool:
    config = apps_config if isinstance(apps_config, AppsConfig) else AppsConfig.from_mapping(apps_config)
    if config is None:
        return True
    default_enabled = config.default.enabled if config.default is not None else True
    if connector_id is not None and connector_id in config.apps:
        return config.apps[connector_id].enabled
    return default_enabled


def managed_app_tool_approval(
    requirements_apps_config: AppsRequirements | Mapping[str, JsonValue] | None,
    connector_id: str | None,
    tool_name: str,
) -> AppToolApproval | None:
    if connector_id is None:
        return None
    requirements = (
        requirements_apps_config
        if isinstance(requirements_apps_config, AppsRequirements)
        else AppsRequirements.from_mapping(requirements_apps_config)
    )
    if requirements is None:
        return None
    app_requirement = requirements.apps.get(connector_id)
    if app_requirement is None or app_requirement.tools is None:
        return None
    tool_requirement = app_requirement.tools.tools.get(tool_name)
    if tool_requirement is None:
        return None
    return tool_requirement.approval_mode


def app_tool_policy(
    apps_config: AppsConfig | Mapping[str, JsonValue] | None,
    requirements_apps_config: AppsRequirements | Mapping[str, JsonValue] | None,
    connector_id: str | None,
    tool_name: str,
    tool_title: str | None = None,
    annotations: ToolAnnotations | Mapping[str, JsonValue] | None = None,
) -> AppToolPolicy:
    config = apps_config if isinstance(apps_config, AppsConfig) else AppsConfig.from_mapping(apps_config)
    requirements = (
        requirements_apps_config
        if isinstance(requirements_apps_config, AppsRequirements)
        else AppsRequirements.from_mapping(requirements_apps_config)
    )
    managed_approval = managed_app_tool_approval(requirements, connector_id, tool_name)
    effective_config = apply_requirements_apps_constraints(config or AppsConfig(), requirements)
    effective_config_or_none = effective_config if effective_config.has_effective_state() else None
    return app_tool_policy_from_apps_config(
        effective_config_or_none,
        connector_id,
        tool_name,
        tool_title,
        annotations,
        managed_approval,
    )


def app_tool_policy_from_apps_config(
    apps_config: AppsConfig | Mapping[str, JsonValue] | None,
    connector_id: str | None,
    tool_name: str,
    tool_title: str | None = None,
    annotations: ToolAnnotations | Mapping[str, JsonValue] | None = None,
    managed_approval: AppToolApproval | str | None = None,
) -> AppToolPolicy:
    config = apps_config if isinstance(apps_config, AppsConfig) else AppsConfig.from_mapping(apps_config)
    managed_approval = _optional_app_tool_approval(managed_approval)
    if config is None:
        return AppToolPolicy(approval=managed_approval or AppToolApproval.AUTO)

    app = config.apps.get(connector_id) if connector_id is not None else None
    tools = app.tools if app is not None else None
    tool_config = None
    if tools is not None:
        tool_config = tools.tools.get(tool_name)
        if tool_config is None and tool_title is not None:
            tool_config = tools.tools.get(tool_title)

    approval = (
        managed_approval
        or (tool_config.approval_mode if tool_config is not None else None)
        or (app.default_tools_approval_mode if app is not None else None)
        or AppToolApproval.AUTO
    )

    if not app_is_enabled(config, connector_id):
        return AppToolPolicy(enabled=False, approval=approval)

    if tool_config is not None and tool_config.enabled is not None:
        return AppToolPolicy(enabled=tool_config.enabled, approval=approval)

    if app is not None and app.default_tools_enabled is not None:
        return AppToolPolicy(enabled=app.default_tools_enabled, approval=approval)

    app_defaults = config.default
    destructive_enabled = (
        app.destructive_enabled
        if app is not None and app.destructive_enabled is not None
        else app_defaults.destructive_enabled
        if app_defaults is not None
        else True
    )
    open_world_enabled = (
        app.open_world_enabled
        if app is not None and app.open_world_enabled is not None
        else app_defaults.open_world_enabled
        if app_defaults is not None
        else True
    )
    tool_annotations = ToolAnnotations.from_value(annotations)
    destructive_hint = (
        tool_annotations.destructive_hint
        if tool_annotations is not None and tool_annotations.destructive_hint is not None
        else True
    )
    open_world_hint = (
        tool_annotations.open_world_hint
        if tool_annotations is not None and tool_annotations.open_world_hint is not None
        else True
    )
    enabled = (destructive_enabled or not destructive_hint) and (
        open_world_enabled or not open_world_hint
    )
    return AppToolPolicy(enabled=enabled, approval=approval)


def codex_app_tool_is_enabled(
    tool_info: ToolInfo | Mapping[str, JsonValue],
    apps_config: AppsConfig | Mapping[str, JsonValue] | None = None,
    requirements_apps_config: AppsRequirements | Mapping[str, JsonValue] | None = None,
) -> bool:
    info = tool_info if isinstance(tool_info, ToolInfo) else ToolInfo.from_mapping(tool_info)
    if info.server_name != CODEX_APPS_MCP_SERVER_NAME:
        return True
    return app_tool_policy(
        apps_config,
        requirements_apps_config,
        info.connector_id,
        info.tool.name,
        info.tool.title,
        info.tool.annotations,
    ).enabled


def apply_requirements_apps_constraints(
    apps_config: AppsConfig | Mapping[str, JsonValue],
    requirements_apps_config: AppsRequirements | Mapping[str, JsonValue] | None,
) -> AppsConfig:
    config = apps_config if isinstance(apps_config, AppsConfig) else AppsConfig.from_mapping(apps_config)
    config = config or AppsConfig()
    requirements = (
        requirements_apps_config
        if isinstance(requirements_apps_config, AppsRequirements)
        else AppsRequirements.from_mapping(requirements_apps_config)
    )
    if requirements is None:
        return config
    for app_id, requirement in requirements.apps.items():
        if requirement.enabled is False:
            config = config.with_app(
                app_id,
                config.apps.get(app_id, AppConfig()).with_enabled(False),
            )
    return config


def with_app_enabled_state(
    connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    user_apps_config: AppsConfig | Mapping[str, JsonValue] | None = None,
    requirements_apps_config: AppsRequirements | Mapping[str, JsonValue] | None = None,
) -> list[AppInfo]:
    parsed_connectors = [_coerce_app_info(connector) for connector in connectors]
    user_config = (
        user_apps_config
        if isinstance(user_apps_config, AppsConfig)
        else AppsConfig.from_mapping(user_apps_config)
    )
    requirements = (
        requirements_apps_config
        if isinstance(requirements_apps_config, AppsRequirements)
        else AppsRequirements.from_mapping(requirements_apps_config)
    )
    if (user_config is None or not user_config.has_effective_state()) and (
        requirements is None or not requirements.apps
    ):
        return parsed_connectors

    result = []
    for connector in parsed_connectors:
        enabled = connector.is_enabled
        if user_config is not None and (
            user_config.default is not None or connector.id in user_config.apps
        ):
            enabled = app_is_enabled(user_config, connector.id)
        if (
            requirements is not None
            and requirements.apps.get(connector.id) is not None
            and requirements.apps[connector.id].enabled is False
        ):
            enabled = False
        result.append(_replace_app_info(connector, is_enabled=enabled))
    return result


def with_app_plugin_sources(
    connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    plugin_sources: Mapping[str, Iterable[str]],
) -> list[AppInfo]:
    return [
        _replace_app_info(
            _coerce_app_info(connector),
            plugin_display_names=tuple(str(name) for name in plugin_sources.get(_coerce_app_info(connector).id, ())),
        )
        for connector in connectors
    ]








def _coerce_app_tool_config(value: AppToolConfig | Mapping[str, JsonValue]) -> AppToolConfig:
    return value if isinstance(value, AppToolConfig) else AppToolConfig.from_mapping(value)


def _app_tool_approval_or_default(value: AppToolApproval | str | None) -> AppToolApproval:
    return _optional_app_tool_approval(value) or AppToolApproval.AUTO


def _optional_app_tool_approval(value: JsonValue) -> AppToolApproval | None:
    if value is None:
        return None
    if isinstance(value, AppToolApproval):
        return value
    return AppToolApproval(str(value))


def _optional_str(value: JsonValue) -> str | None:
    return None if value is None else str(value)


def _optional_bool(value: JsonValue) -> bool | None:
    return None if value is None else bool(value)


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


__all__ = [
    "AppConfig",
    "AppRequirement",
    "AppToolApproval",
    "AppToolConfig",
    "AppToolPolicy",
    "AppToolRequirement",
    "AppToolsConfig",
    "AppToolsRequirements",
    "AppsConfig",
    "AppsDefaultConfig",
    "AppsRequirements",
    "ToolAnnotations",
    "accessible_connectors_from_mcp_tools",
    "app_is_enabled",
    "app_tool_policy",
    "app_tool_policy_from_apps_config",
    "apply_requirements_apps_constraints",
    "codex_app_tool_is_enabled",
    "managed_app_tool_approval",
    "with_app_enabled_state",
    "with_app_plugin_sources",
]
