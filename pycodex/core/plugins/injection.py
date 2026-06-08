"""Plugin prompt injection helpers ported from ``codex-core::plugins::injection``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.connectors.metadata import connector_display_label
from pycodex.core.context import PluginCapabilitySummary, PluginInstructions
from pycodex.core.plugins.render import render_explicit_plugin_instructions
from pycodex.mcp import CODEX_APPS_MCP_SERVER_NAME
from pycodex.protocol import ResponseItem


def build_plugin_injections(
    mentioned_plugins: Iterable[PluginCapabilitySummary | Mapping[str, Any] | Any],
    mcp_tools: Iterable[Any],
    available_connectors: Iterable[Any],
) -> tuple[ResponseItem, ...]:
    plugins = tuple(PluginCapabilitySummary.from_value(plugin) for plugin in mentioned_plugins)
    if not plugins:
        return ()
    tools = tuple(mcp_tools)
    connectors = tuple(available_connectors)
    items: list[ResponseItem] = []
    for plugin in plugins:
        available_mcp_servers = sorted(
            {
                server_name
                for tool in tools
                if (server_name := _string_field(tool, "server_name"))
                and server_name != CODEX_APPS_MCP_SERVER_NAME
                and plugin.display_name in _string_tuple(_field_value(tool, "plugin_display_names", ()))
            }
        )
        available_apps = sorted(
            {
                connector_display_label(connector)
                for connector in connectors
                if bool(_field_value(connector, "is_enabled", False))
                and plugin.display_name in _string_tuple(_field_value(connector, "plugin_display_names", ()))
            }
        )
        instructions = render_explicit_plugin_instructions(
            plugin,
            available_mcp_servers,
            available_apps,
        )
        if instructions is not None:
            items.append(PluginInstructions.new(instructions).into_response_item())
    return tuple(items)


def _field_value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _string_field(value: Any, name: str) -> str:
    raw = _field_value(value, name, "")
    return raw if isinstance(raw, str) else str(raw) if raw is not None else ""


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(str(item) for item in value)
    except TypeError:
        return (str(value),)


__all__ = ["build_plugin_injections"]
