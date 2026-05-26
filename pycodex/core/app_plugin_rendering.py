"""App and plugin instruction render helpers ported from Codex core.

This mirrors the dependency-free wrappers in ``core/src/apps/render.rs`` and
``core/src/plugins/render.rs``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.core.context import (
    AppsInstructions,
    AvailablePluginsInstructions,
    PluginCapabilitySummary,
)

JsonValue = Any


def render_apps_section(connectors: Iterable[Any]) -> str | None:
    instructions = AppsInstructions.from_connectors(connectors)
    return None if instructions is None else instructions.render()


def render_plugins_section(
    plugins: Iterable[PluginCapabilitySummary | Mapping[str, JsonValue] | Any],
) -> str | None:
    instructions = AvailablePluginsInstructions.from_plugins(plugins)
    return None if instructions is None else instructions.render()


def render_explicit_plugin_instructions(
    plugin: PluginCapabilitySummary | Mapping[str, JsonValue] | Any,
    available_mcp_servers: Iterable[str],
    available_apps: Iterable[str],
) -> str | None:
    plugin_summary = PluginCapabilitySummary.from_value(plugin)
    lines = [f"Capabilities from the `{plugin_summary.display_name}` plugin:"]

    if plugin_summary.has_skills:
        lines.append(f"- Skills from this plugin are prefixed with `{plugin_summary.display_name}:`.")

    mcp_servers = tuple(str(server) for server in available_mcp_servers)
    if mcp_servers:
        rendered_servers = ", ".join(f"`{server}`" for server in mcp_servers)
        lines.append(f"- MCP servers from this plugin available in this session: {rendered_servers}.")

    apps = tuple(str(app) for app in available_apps)
    if apps:
        rendered_apps = ", ".join(f"`{app}`" for app in apps)
        lines.append(f"- Apps from this plugin available in this session: {rendered_apps}.")

    if len(lines) == 1:
        return None

    lines.append("Use these plugin-associated capabilities to help solve the task.")
    return "\n".join(lines)


__all__ = [
    "render_apps_section",
    "render_explicit_plugin_instructions",
    "render_plugins_section",
]
