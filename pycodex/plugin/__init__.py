"""Source-verified public interface slice for ``codex-plugin``.

Rust source:
- ``codex/codex-rs/plugin/src/lib.rs``
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PluginIdError(ValueError):
    pass


def validate_plugin_segment(segment: str) -> None:
    if not segment or not re.fullmatch(r"[A-Za-z0-9._-]+", segment):
        raise PluginIdError(f"invalid plugin id segment: {segment}")


@dataclass(frozen=True)
class PluginId:
    value: str

    @classmethod
    def parse(cls, value: str) -> "PluginId":
        if "@" in value:
            name, marketplace = value.split("@", 1)
            validate_plugin_segment(name)
            validate_plugin_segment(marketplace)
        else:
            validate_plugin_segment(value)
        return cls(value)

    def as_key(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class AppConnectorId:
    value: str


@dataclass(frozen=True)
class PluginCapabilitySummary:
    config_name: str = ""
    display_name: str = ""
    description: str | None = None
    has_skills: bool = False
    mcp_server_names: tuple[str, ...] = ()
    app_connector_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "config_name", str(self.config_name))
        object.__setattr__(self, "display_name", str(self.display_name))
        if self.description is not None:
            object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "mcp_server_names", tuple(str(item) for item in self.mcp_server_names))
        object.__setattr__(self, "app_connector_ids", tuple(str(item) for item in self.app_connector_ids))

    @classmethod
    def from_value(cls, value: "PluginCapabilitySummary | Mapping[str, Any] | Any") -> "PluginCapabilitySummary":
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            display_name = value.get("display_name", value.get("displayName", value.get("config_name", "")))
            return cls(
                config_name=value.get("config_name", value.get("configName", display_name)),
                display_name=display_name,
                description=value.get("description"),
                has_skills=bool(value.get("has_skills", value.get("hasSkills", False))),
                mcp_server_names=tuple(value.get("mcp_server_names", value.get("mcpServerNames", ()))),
                app_connector_ids=tuple(value.get("app_connector_ids", value.get("appConnectorIds", ()))),
            )
        display_name = getattr(value, "display_name", getattr(value, "config_name", ""))
        return cls(
            config_name=getattr(value, "config_name", display_name),
            display_name=display_name,
            description=getattr(value, "description", None),
            has_skills=bool(getattr(value, "has_skills", False)),
            mcp_server_names=tuple(getattr(value, "mcp_server_names", ())),
            app_connector_ids=tuple(getattr(value, "app_connector_ids", ())),
        )

    def telemetry_metadata(self) -> "PluginTelemetryMetadata | None":
        try:
            plugin_id = PluginId.parse(self.config_name)
        except PluginIdError:
            return None
        return PluginTelemetryMetadata(plugin_id, None, self)


@dataclass
class PluginHookSource:
    plugin_id: PluginId
    plugin_root: Path
    plugin_data_root: Path
    source_path: Path
    source_relative_path: str
    hooks: Any


@dataclass
class PluginTelemetryMetadata:
    plugin_id: PluginId
    remote_plugin_id: str | None = None
    capability_summary: PluginCapabilitySummary | None = None

    @classmethod
    def from_plugin_id(cls, plugin_id: PluginId) -> "PluginTelemetryMetadata":
        return cls(plugin_id)


@dataclass
class EffectiveSkillRoots:
    roots: list[Path] = field(default_factory=list)


@dataclass
class LoadedPlugin:
    plugin_id: PluginId
    root: Path | None = None


@dataclass
class PluginLoadOutcome:
    loaded_plugins: list[LoadedPlugin] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def prompt_safe_plugin_description(description: str | None) -> str | None:
    return description.strip() if isinstance(description, str) and description.strip() else None


def mention_syntax(plugin_id: str) -> str:
    return f"@{plugin_id}"


def plugin_namespace_for_skill_path(path: str | Path) -> str:
    return Path(path).stem.replace("-", "_")


__all__ = [name for name in globals() if not name.startswith("_")]
