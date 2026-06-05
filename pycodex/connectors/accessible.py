"""Accessible connector collection aligned with ``codex-rs/connectors/src/accessible.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pycodex.tools.tool_discovery import AppInfo

from .metadata import connector_install_url, normalize_connector_value, replace_app_info

JsonValue = Any


@dataclass(frozen=True)
class AccessibleConnectorTool:
    connector_id: str
    connector_name: str | None = None
    connector_description: str | None = None
    plugin_display_names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "connector_id", str(self.connector_id))
        object.__setattr__(self, "connector_name", _optional_str(self.connector_name))
        object.__setattr__(
            self,
            "connector_description",
            _optional_str(self.connector_description),
        )
        object.__setattr__(
            self,
            "plugin_display_names",
            _string_tuple(self.plugin_display_names),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AccessibleConnectorTool":
        return cls(
            connector_id=str(value["connector_id"]),
            connector_name=_optional_str(value.get("connector_name")),
            connector_description=_optional_str(
                value.get("connector_description", value.get("namespace_description"))
            ),
            plugin_display_names=_string_tuple(value.get("plugin_display_names", ())),
        )


def collect_accessible_connectors(
    tools: Iterable[AccessibleConnectorTool | Mapping[str, JsonValue]],
) -> list[AppInfo]:
    connectors: dict[str, tuple[AppInfo, set[str]]] = {}
    for raw_tool in tools:
        tool = (
            raw_tool
            if isinstance(raw_tool, AccessibleConnectorTool)
            else AccessibleConnectorTool.from_mapping(raw_tool)
        )
        connector_id = tool.connector_id
        connector_name = normalize_connector_value(tool.connector_name) or connector_id
        connector_description = normalize_connector_value(tool.connector_description)
        if connector_id in connectors:
            existing, plugin_display_names = connectors[connector_id]
            if existing.name == connector_id and connector_name != connector_id:
                existing = replace_app_info(existing, name=connector_name)
            if existing.description is None and connector_description is not None:
                existing = replace_app_info(existing, description=connector_description)
            plugin_display_names.update(tool.plugin_display_names)
            connectors[connector_id] = (existing, plugin_display_names)
            continue

        connectors[connector_id] = (
            AppInfo(
                id=connector_id,
                name=connector_name,
                description=connector_description,
                is_accessible=True,
                is_enabled=True,
            ),
            set(tool.plugin_display_names),
        )

    accessible = []
    for connector, plugin_display_names in connectors.values():
        accessible.append(
            replace_app_info(
                connector,
                install_url=connector_install_url(connector.name, connector.id),
                plugin_display_names=tuple(sorted(plugin_display_names)),
            )
        )
    accessible.sort(key=lambda connector: (not connector.is_accessible, connector.name, connector.id))
    return accessible


def _optional_str(value: JsonValue) -> str | None:
    return None if value is None else str(value)


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


__all__ = [
    "AccessibleConnectorTool",
    "collect_accessible_connectors",
]
