"""Discoverable plugin suggestions.

Rust source: ``codex/codex-rs/core/src/plugins/discoverable.rs``.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.core.config.edit import ToolSuggestDiscoverableType
from pycodex.core.context import PluginCapabilitySummary
from pycodex.core_plugins import (
    OPENAI_BUNDLED_MARKETPLACE_NAME,
    OPENAI_CURATED_MARKETPLACE_NAME,
    TOOL_SUGGEST_DISCOVERABLE_PLUGIN_ALLOWLIST,
    PluginDetail,
    PluginsManager,
)
from pycodex.features import Feature
from pycodex.tools import DiscoverablePluginInfo


LOGGER = logging.getLogger(__name__)

TOOL_SUGGEST_DISCOVERABLE_MARKETPLACE_ALLOWLIST = (
    OPENAI_BUNDLED_MARKETPLACE_NAME,
    OPENAI_CURATED_MARKETPLACE_NAME,
)


async def list_tool_suggest_discoverable_plugins(
    config: Any,
    plugins_manager: Any | None = None,
) -> list[DiscoverablePluginInfo]:
    """Return installable plugin suggestions for the tool-suggest flow."""

    if not _feature_enabled(config, Feature.PLUGINS):
        return []

    manager = plugins_manager
    if manager is None:
        manager = PluginsManager.new(getattr(config, "codex_home"))

    plugins_input = _plugins_config_input(config)
    configured_plugin_ids = set(
        _tool_suggest_plugin_ids(_tool_suggest_items(config, "discoverables"))
    )
    disabled_plugin_ids = set(
        _tool_suggest_plugin_ids(_tool_suggest_items(config, "disabled_tools"))
    )
    outcome = await _maybe_await(
        manager.list_marketplaces_for_config(plugins_input, [])
    )
    marketplaces = tuple(getattr(outcome, "marketplaces", ()))
    discoverable_plugins: list[DiscoverablePluginInfo] = []

    for marketplace in marketplaces:
        marketplace_name = str(getattr(marketplace, "name", ""))
        if marketplace_name not in TOOL_SUGGEST_DISCOVERABLE_MARKETPLACE_ALLOWLIST:
            continue
        for plugin in getattr(marketplace, "plugins", ()):
            plugin_id = _marketplace_plugin_id(plugin, marketplace_name)
            if (
                bool(getattr(plugin, "installed", False))
                or plugin_id in disabled_plugin_ids
                or (
                    plugin_id not in TOOL_SUGGEST_DISCOVERABLE_PLUGIN_ALLOWLIST
                    and plugin_id not in configured_plugin_ids
                )
            ):
                continue
            try:
                detail = await _maybe_await(
                    manager.read_plugin_detail_for_marketplace_plugin(
                        plugins_input,
                        marketplace_name,
                        plugin,
                    )
                )
            except Exception as exc:
                LOGGER.warning("failed to load discoverable plugin suggestion %s: %s", plugin_id, exc)
                continue
            discoverable_plugins.append(
                _discoverable_plugin_info_from_detail(detail, fallback_plugin_id=plugin_id)
            )

    discoverable_plugins.sort(key=lambda plugin: (plugin.name, plugin.id))
    return discoverable_plugins


def _discoverable_plugin_info_from_detail(
    detail: Any,
    *,
    fallback_plugin_id: str,
) -> DiscoverablePluginInfo:
    plugin = getattr(detail, "plugin", detail)
    if isinstance(plugin, PluginCapabilitySummary):
        summary = plugin
    else:
        summary = _plugin_capability_summary_from_detail(plugin, fallback_plugin_id)
    return DiscoverablePluginInfo(
        id=summary.config_name,
        name=summary.display_name,
        description=summary.description,
        has_skills=summary.has_skills,
        mcp_server_names=summary.mcp_server_names,
        app_connector_ids=summary.app_connector_ids,
    )


def _plugin_capability_summary_from_detail(
    plugin: Any,
    fallback_plugin_id: str,
) -> PluginCapabilitySummary:
    if isinstance(plugin, Mapping):
        plugin_id = str(plugin.get("id", fallback_plugin_id))
        name = str(plugin.get("name", plugin_id.rsplit("@", 1)[0]))
        description = _normalize_description(plugin.get("description"))
        skills = plugin.get("skills", ())
        mcp_server_names = plugin.get("mcp_server_names", plugin.get("mcpServerNames", ()))
        apps = plugin.get("apps", ())
        app_connector_ids = plugin.get("app_connector_ids", plugin.get("appConnectorIds", ()))
    elif isinstance(plugin, PluginDetail):
        plugin_id = plugin.id or fallback_plugin_id
        name = plugin.name or plugin_id.rsplit("@", 1)[0]
        description = _normalize_description(plugin.description)
        skills = plugin.skills
        mcp_server_names = plugin.mcp_server_names
        apps = plugin.apps
        app_connector_ids = ()
    else:
        plugin_id = str(getattr(plugin, "id", fallback_plugin_id))
        name = str(getattr(plugin, "name", plugin_id.rsplit("@", 1)[0]))
        description = _normalize_description(getattr(plugin, "description", None))
        skills = getattr(plugin, "skills", ())
        mcp_server_names = getattr(plugin, "mcp_server_names", ())
        apps = getattr(plugin, "apps", ())
        app_connector_ids = getattr(plugin, "app_connector_ids", ())

    return PluginCapabilitySummary(
        config_name=plugin_id,
        display_name=name,
        description=description,
        has_skills=bool(tuple(skills)),
        mcp_server_names=tuple(str(item) for item in mcp_server_names),
        app_connector_ids=tuple(str(item) for item in tuple(app_connector_ids) + _connector_ids_from_apps(apps)),
    )


def _feature_enabled(config: Any, feature: Feature) -> bool:
    features = getattr(config, "features", None)
    enabled = getattr(features, "enabled", None)
    return bool(callable(enabled) and enabled(feature))


def _plugins_config_input(config: Any) -> Any:
    plugins_config_input = getattr(config, "plugins_config_input", None)
    return plugins_config_input() if callable(plugins_config_input) else None


def _tool_suggest_items(config: Any, attr: str) -> Iterable[Any]:
    tool_suggest = getattr(config, "tool_suggest", None)
    if tool_suggest is None and isinstance(config, Mapping):
        tool_suggest = config.get("tool_suggest")
    if tool_suggest is None:
        return ()
    if isinstance(tool_suggest, Mapping):
        return tool_suggest.get(attr, ()) or ()
    return getattr(tool_suggest, attr, ()) or ()


def _tool_suggest_plugin_ids(items: Iterable[Any]) -> Iterable[str]:
    for item in items:
        kind = _field(item, "kind", _field(item, "type", None))
        if _tool_suggest_kind(kind) == ToolSuggestDiscoverableType.PLUGIN:
            raw_id = _field(item, "id", None)
            if raw_id is not None:
                yield str(raw_id)


def _tool_suggest_kind(value: Any) -> ToolSuggestDiscoverableType | None:
    if isinstance(value, ToolSuggestDiscoverableType):
        return value
    if value is None:
        return None
    try:
        return ToolSuggestDiscoverableType(str(value))
    except ValueError:
        return None


def _marketplace_plugin_id(plugin: Any, marketplace_name: str) -> str:
    raw_id = getattr(plugin, "id", None)
    if raw_id is not None:
        value = str(raw_id)
        return value if "@" in value else f"{value}@{marketplace_name}"
    name = str(getattr(plugin, "name", ""))
    return f"{name}@{marketplace_name}"


def _connector_ids_from_apps(apps: Iterable[Any]) -> tuple[str, ...]:
    ids = []
    for app in apps:
        connector_id = _field(app, "connector_id", _field(app, "connectorId", _field(app, "id", None)))
        if connector_id is None:
            continue
        value = getattr(connector_id, "0", connector_id)
        ids.append(str(value))
    return tuple(ids)


def _normalize_description(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "TOOL_SUGGEST_DISCOVERABLE_MARKETPLACE_ALLOWLIST",
    "list_tool_suggest_discoverable_plugins",
]
