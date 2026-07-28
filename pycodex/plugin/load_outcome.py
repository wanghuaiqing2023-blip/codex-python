"""Plugin load results owned by ``codex-plugin::load_outcome``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pycodex.utils.plugins import PluginSkillRoot

from . import AppConnectorId, PluginCapabilitySummary, PluginHookSource

MAX_CAPABILITY_SUMMARY_DESCRIPTION_LEN = 1024


@dataclass(frozen=True)
class LoadedPlugin:
    config_name: str
    root: Path
    manifest_name: str | None = None
    manifest_description: str | None = None
    enabled: bool = True
    skill_roots: tuple[Path, ...] = ()
    disabled_skill_paths: frozenset[Path] = frozenset()
    has_enabled_skills: bool = False
    mcp_servers: Mapping[str, Any] = field(default_factory=dict)
    apps: tuple[str | AppConnectorId, ...] = ()
    hook_sources: tuple[PluginHookSource, ...] = ()
    hook_load_warnings: tuple[str, ...] = ()
    error: str | None = None

    def is_active(self) -> bool:
        return self.enabled and self.error is None


def _connector_value(connector_id: str | AppConnectorId) -> str:
    if isinstance(connector_id, AppConnectorId):
        return connector_id.value
    return str(connector_id)


def _plugin_capability_summary_from_loaded(
    plugin: LoadedPlugin,
) -> PluginCapabilitySummary | None:
    if not plugin.is_active():
        return None
    summary = PluginCapabilitySummary(
        config_name=plugin.config_name,
        display_name=plugin.manifest_name or plugin.config_name,
        description=prompt_safe_plugin_description(plugin.manifest_description),
        has_skills=plugin.has_enabled_skills,
        mcp_server_names=tuple(sorted(str(name) for name in plugin.mcp_servers)),
        app_connector_ids=tuple(_connector_value(item) for item in plugin.apps),
    )
    if summary.has_skills or summary.mcp_server_names or summary.app_connector_ids:
        return summary
    return None


def prompt_safe_plugin_description(description: str | None) -> str | None:
    if description is None:
        return None
    normalized = " ".join(str(description).split())
    if not normalized:
        return None
    return normalized[:MAX_CAPABILITY_SUMMARY_DESCRIPTION_LEN]


@dataclass(frozen=True)
class PluginLoadOutcome:
    _plugins: tuple[LoadedPlugin, ...] = ()
    _capability_summaries: tuple[PluginCapabilitySummary, ...] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        summaries = tuple(
            summary
            for plugin in self._plugins
            if (summary := _plugin_capability_summary_from_loaded(plugin)) is not None
        )
        object.__setattr__(self, "_capability_summaries", summaries)

    @classmethod
    def from_plugins(
        cls,
        plugins: list[LoadedPlugin] | tuple[LoadedPlugin, ...],
    ) -> "PluginLoadOutcome":
        return cls(tuple(plugins))

    def effective_skill_roots(self) -> tuple[Path, ...]:
        return tuple(
            sorted(
                {
                    path
                    for plugin in self._plugins
                    if plugin.is_active()
                    for path in plugin.skill_roots
                },
                key=str,
            )
        )

    def effective_plugin_skill_roots(self) -> tuple[PluginSkillRoot, ...]:
        skill_roots: list[PluginSkillRoot] = []
        seen_paths: set[Path] = set()
        for plugin in self._plugins:
            if not plugin.is_active():
                continue
            for path in plugin.skill_roots:
                if path in seen_paths:
                    continue
                seen_paths.add(path)
                skill_roots.append(
                    PluginSkillRoot(
                        path=path,
                        plugin_id=plugin.config_name,
                        plugin_root=plugin.root,
                    )
                )
        skill_roots.sort(key=lambda root: str(root.path))
        return tuple(skill_roots)

    def effective_mcp_servers(self) -> dict[str, Any]:
        mcp_servers: dict[str, Any] = {}
        for plugin in self._plugins:
            if not plugin.is_active():
                continue
            for name, config in plugin.mcp_servers.items():
                mcp_servers.setdefault(str(name), config)
        return mcp_servers

    def effective_apps(self) -> tuple[str, ...]:
        apps: list[str] = []
        seen_connector_ids: set[str] = set()
        for plugin in self._plugins:
            if not plugin.is_active():
                continue
            for connector_id in plugin.apps:
                value = _connector_value(connector_id)
                if value in seen_connector_ids:
                    continue
                seen_connector_ids.add(value)
                apps.append(value)
        return tuple(apps)

    def effective_plugin_hook_sources(self) -> tuple[PluginHookSource, ...]:
        return tuple(
            source
            for plugin in self._plugins
            if plugin.is_active()
            for source in plugin.hook_sources
        )

    def effective_plugin_hook_warnings(self) -> tuple[str, ...]:
        return tuple(
            warning
            for plugin in self._plugins
            if plugin.is_active()
            for warning in plugin.hook_load_warnings
        )

    def capability_summaries(self) -> tuple[PluginCapabilitySummary, ...]:
        return self._capability_summaries

    def plugins(self) -> tuple[LoadedPlugin, ...]:
        return self._plugins


class EffectiveSkillRoots(Protocol):
    def effective_skill_roots(self) -> tuple[Path, ...]: ...

    def effective_plugin_skill_roots(self) -> tuple[PluginSkillRoot, ...]: ...


__all__ = [
    "EffectiveSkillRoots",
    "LoadedPlugin",
    "PluginLoadOutcome",
    "prompt_safe_plugin_description",
]
