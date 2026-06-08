"""Source-verified public interface slice for ``codex-plugin``.

Rust source:
- ``codex/codex-rs/plugin/src/lib.rs``
"""

from __future__ import annotations

import re
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


@dataclass
class PluginCapabilitySummary:
    config_name: str = ""
    display_name: str = ""
    description: str | None = None
    has_skills: bool = False
    mcp_server_names: list[str] = field(default_factory=list)
    app_connector_ids: list[AppConnectorId] = field(default_factory=list)

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
