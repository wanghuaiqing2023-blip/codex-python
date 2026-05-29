"""Discoverable tool helpers ported from Codex.

This mirrors the dependency-free data transformations in
``codex-rs/tools/src/tool_discovery.rs``: connector/plugin discovery metadata,
client-specific filtering, and the list entries consumed by the
``request_plugin_install`` tool flow.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.core.tool_search_handler import (
    TOOL_SEARCH_DEFAULT_LIMIT,
    TOOL_SEARCH_TOOL_NAME,
)
from pycodex.core.tool_search_entry import ToolSearchSourceInfo

JsonValue = Any

TUI_CLIENT_NAME = "codex-tui"
LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME = "list_available_plugins_to_install"
REQUEST_PLUGIN_INSTALL_TOOL_NAME = "request_plugin_install"


class DiscoverableToolType(str, Enum):
    CONNECTOR = "connector"
    PLUGIN = "plugin"


class DiscoverableToolAction(str, Enum):
    INSTALL = "install"
    ENABLE = "enable"


@dataclass(frozen=True)
class AppInfo:
    id: str
    name: str
    description: str | None = None
    logo_url: str | None = None
    logo_url_dark: str | None = None
    distribution_channel: str | None = None
    branding: JsonValue | None = None
    app_metadata: JsonValue | None = None
    labels: tuple[str, ...] | None = None
    install_url: str | None = None
    is_accessible: bool = False
    is_enabled: bool = False
    plugin_display_names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _optional_str(self.description))
        object.__setattr__(self, "logo_url", _optional_str(self.logo_url))
        object.__setattr__(self, "logo_url_dark", _optional_str(self.logo_url_dark))
        object.__setattr__(
            self,
            "distribution_channel",
            _optional_str(self.distribution_channel),
        )
        object.__setattr__(self, "labels", _optional_tuple(self.labels))
        object.__setattr__(self, "install_url", _optional_str(self.install_url))
        object.__setattr__(self, "is_accessible", _ensure_bool(self.is_accessible, "is_accessible"))
        object.__setattr__(self, "is_enabled", _ensure_bool(self.is_enabled, "is_enabled"))
        object.__setattr__(
            self,
            "plugin_display_names",
            _string_tuple(self.plugin_display_names),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AppInfo":
        if not isinstance(value, Mapping):
            raise TypeError("AppInfo mapping must be a mapping")
        return cls(
            id=_ensure_str(value["id"], "id"),
            name=_ensure_str(value["name"], "name"),
            description=_optional_str(value.get("description")),
            logo_url=_optional_str(value.get("logo_url")),
            logo_url_dark=_optional_str(value.get("logo_url_dark")),
            distribution_channel=_optional_str(value.get("distribution_channel")),
            branding=copy.deepcopy(value.get("branding")),
            app_metadata=copy.deepcopy(value.get("app_metadata")),
            labels=_optional_tuple(value.get("labels")),
            install_url=_optional_str(value.get("install_url")),
            is_accessible=_ensure_bool(value.get("is_accessible", False), "is_accessible"),
            is_enabled=_ensure_bool(value.get("is_enabled", False), "is_enabled"),
            plugin_display_names=_string_tuple(value.get("plugin_display_names", ())),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "logo_url": self.logo_url,
            "logo_url_dark": self.logo_url_dark,
            "distribution_channel": self.distribution_channel,
            "branding": copy.deepcopy(self.branding),
            "app_metadata": copy.deepcopy(self.app_metadata),
            "labels": None if self.labels is None else list(self.labels),
            "install_url": self.install_url,
            "is_accessible": self.is_accessible,
            "is_enabled": self.is_enabled,
            "plugin_display_names": list(self.plugin_display_names),
        }


@dataclass(frozen=True)
class DiscoverablePluginInfo:
    id: str
    name: str
    description: str | None = None
    has_skills: bool = False
    mcp_server_names: tuple[str, ...] = field(default_factory=tuple)
    app_connector_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _optional_str(self.description))
        object.__setattr__(self, "has_skills", _ensure_bool(self.has_skills, "has_skills"))
        object.__setattr__(self, "mcp_server_names", _string_tuple(self.mcp_server_names))
        object.__setattr__(self, "app_connector_ids", _string_tuple(self.app_connector_ids))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "DiscoverablePluginInfo":
        if not isinstance(value, Mapping):
            raise TypeError("DiscoverablePluginInfo mapping must be a mapping")
        return cls(
            id=_ensure_str(value["id"], "id"),
            name=_ensure_str(value["name"], "name"),
            description=_optional_str(value.get("description")),
            has_skills=_ensure_bool(value.get("has_skills", False), "has_skills"),
            mcp_server_names=_string_tuple(value.get("mcp_server_names", ())),
            app_connector_ids=_string_tuple(value.get("app_connector_ids", ())),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "has_skills": self.has_skills,
            "mcp_server_names": list(self.mcp_server_names),
            "app_connector_ids": list(self.app_connector_ids),
        }


@dataclass(frozen=True)
class DiscoverableTool:
    kind: DiscoverableToolType
    connector_info: AppInfo | None = None
    plugin_info: DiscoverablePluginInfo | None = None

    def __post_init__(self) -> None:
        kind = _coerce_tool_type(self.kind)
        object.__setattr__(self, "kind", kind)
        if kind == DiscoverableToolType.CONNECTOR:
            if self.connector_info is None or self.plugin_info is not None:
                raise ValueError("connector discoverable tool must contain only connector_info")
            if not isinstance(self.connector_info, AppInfo):
                raise TypeError("connector_info must be AppInfo")
        else:
            if self.plugin_info is None or self.connector_info is not None:
                raise ValueError("plugin discoverable tool must contain only plugin_info")
            if not isinstance(self.plugin_info, DiscoverablePluginInfo):
                raise TypeError("plugin_info must be DiscoverablePluginInfo")

    @classmethod
    def connector(cls, value: AppInfo | Mapping[str, JsonValue]) -> "DiscoverableTool":
        info = value if isinstance(value, AppInfo) else AppInfo.from_mapping(value)
        return cls(DiscoverableToolType.CONNECTOR, connector_info=info)

    @classmethod
    def plugin(
        cls,
        value: DiscoverablePluginInfo | Mapping[str, JsonValue],
    ) -> "DiscoverableTool":
        info = value if isinstance(value, DiscoverablePluginInfo) else DiscoverablePluginInfo.from_mapping(value)
        return cls(DiscoverableToolType.PLUGIN, plugin_info=info)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "DiscoverableTool":
        if not isinstance(value, Mapping):
            raise TypeError("DiscoverableTool mapping must be a mapping")
        kind = _coerce_tool_type(value.get("type", value.get("tool_type")))
        if kind == DiscoverableToolType.CONNECTOR:
            return cls.connector(value.get("connector", value))
        return cls.plugin(value.get("plugin", value))

    def tool_type(self) -> DiscoverableToolType:
        return self.kind

    def id(self) -> str:
        return self._inner().id

    def name(self) -> str:
        return self._inner().name

    def install_url(self) -> str | None:
        if self.connector_info is None:
            return None
        return self.connector_info.install_url

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.connector_info is not None:
            return {
                "type": DiscoverableToolType.CONNECTOR.value,
                "connector": self.connector_info.to_mapping(),
            }
        if self.plugin_info is not None:
            return {
                "type": DiscoverableToolType.PLUGIN.value,
                "plugin": self.plugin_info.to_mapping(),
            }
        raise ValueError("discoverable tool is missing inner metadata")

    def _inner(self) -> AppInfo | DiscoverablePluginInfo:
        if self.connector_info is not None:
            return self.connector_info
        if self.plugin_info is not None:
            return self.plugin_info
        raise ValueError("discoverable tool is missing inner metadata")


@dataclass(frozen=True)
class RequestPluginInstallEntry:
    id: str
    name: str
    description: str | None
    tool_type: DiscoverableToolType
    has_skills: bool
    mcp_server_names: tuple[str, ...] = field(default_factory=tuple)
    app_connector_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "description", _optional_str(self.description))
        object.__setattr__(self, "tool_type", _coerce_tool_type(self.tool_type))
        object.__setattr__(self, "has_skills", _ensure_bool(self.has_skills, "has_skills"))
        object.__setattr__(self, "mcp_server_names", _string_tuple(self.mcp_server_names))
        object.__setattr__(self, "app_connector_ids", _string_tuple(self.app_connector_ids))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RequestPluginInstallEntry":
        if not isinstance(value, Mapping):
            raise TypeError("RequestPluginInstallEntry mapping must be a mapping")
        return cls(
            id=_ensure_str(value["id"], "id"),
            name=_ensure_str(value["name"], "name"),
            description=_optional_str(value.get("description")),
            tool_type=_coerce_tool_type(value["tool_type"]),
            has_skills=_ensure_bool(value.get("has_skills", False), "has_skills"),
            mcp_server_names=_string_tuple(value.get("mcp_server_names", ())),
            app_connector_ids=_string_tuple(value.get("app_connector_ids", ())),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "tool_type": self.tool_type.value,
            "has_skills": self.has_skills,
            "mcp_server_names": list(self.mcp_server_names),
            "app_connector_ids": list(self.app_connector_ids),
        }


@dataclass(frozen=True)
class ListAvailablePluginsToInstallResult:
    tools: tuple[RequestPluginInstallEntry, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tools",
            tuple(
                tool
                if isinstance(tool, RequestPluginInstallEntry)
                else RequestPluginInstallEntry.from_mapping(tool)
                for tool in self.tools
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"tools": [tool.to_mapping() for tool in self.tools]}


def filter_request_plugin_install_discoverable_tools_for_client(
    discoverable_tools: Iterable[DiscoverableTool | Mapping[str, JsonValue]],
    app_server_client_name: str | None,
) -> list[DiscoverableTool]:
    if app_server_client_name is not None:
        _ensure_str(app_server_client_name, "app_server_client_name")
    tools = [_coerce_discoverable_tool(tool) for tool in discoverable_tools]
    if app_server_client_name != TUI_CLIENT_NAME:
        return tools
    return [tool for tool in tools if tool.tool_type() != DiscoverableToolType.PLUGIN]


def collect_request_plugin_install_entries(
    discoverable_tools: Iterable[DiscoverableTool | Mapping[str, JsonValue]],
) -> list[RequestPluginInstallEntry]:
    entries: list[RequestPluginInstallEntry] = []
    for tool in discoverable_tools:
        discoverable = _coerce_discoverable_tool(tool)
        if discoverable.connector_info is not None:
            connector = discoverable.connector_info
            entries.append(
                RequestPluginInstallEntry(
                    id=connector.id,
                    name=connector.name,
                    description=connector.description,
                    tool_type=DiscoverableToolType.CONNECTOR,
                    has_skills=False,
                    mcp_server_names=(),
                    app_connector_ids=(),
                )
            )
        elif discoverable.plugin_info is not None:
            plugin = discoverable.plugin_info
            entries.append(
                RequestPluginInstallEntry(
                    id=plugin.id,
                    name=plugin.name,
                    description=plugin.description,
                    tool_type=DiscoverableToolType.PLUGIN,
                    has_skills=plugin.has_skills,
                    mcp_server_names=plugin.mcp_server_names,
                    app_connector_ids=plugin.app_connector_ids,
                )
            )
    return entries


def _coerce_discoverable_tool(
    value: DiscoverableTool | Mapping[str, JsonValue],
) -> DiscoverableTool:
    if isinstance(value, DiscoverableTool):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("discoverable tool must be DiscoverableTool or mapping")
    return DiscoverableTool.from_mapping(value)


def _coerce_tool_type(value: DiscoverableToolType | str | JsonValue) -> DiscoverableToolType:
    if isinstance(value, DiscoverableToolType):
        return value
    if isinstance(value, str):
        return DiscoverableToolType(value)
    raise ValueError(f"unknown discoverable tool type: {value!r}")


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_str(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, "optional string")


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError("string list must be an iterable of strings, not a string")
    if not isinstance(value, Iterable):
        raise TypeError("string list must be iterable")
    result: list[str] = []
    for item in value:
        result.append(_ensure_str(item, "string list item"))
    return tuple(result)


def _optional_tuple(value: JsonValue) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _string_tuple(value)


__all__ = [
    "AppInfo",
    "DiscoverablePluginInfo",
    "DiscoverableTool",
    "DiscoverableToolAction",
    "DiscoverableToolType",
    "LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME",
    "ListAvailablePluginsToInstallResult",
    "REQUEST_PLUGIN_INSTALL_TOOL_NAME",
    "RequestPluginInstallEntry",
    "TOOL_SEARCH_DEFAULT_LIMIT",
    "TOOL_SEARCH_TOOL_NAME",
    "TUI_CLIENT_NAME",
    "ToolSearchSourceInfo",
    "collect_request_plugin_install_entries",
    "filter_request_plugin_install_discoverable_tools_for_client",
]
