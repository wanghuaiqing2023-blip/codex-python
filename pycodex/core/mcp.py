"""MCP manager boundary helpers.

Ported from ``codex/codex-rs/core/src/mcp.rs``. The Rust module is a thin
manager that turns a core Config into an MCP config and delegates to the MCP
crate. This Python port preserves that method shape with injectable delegate
functions instead of pretending to implement the full MCP runtime here.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


McpServerConfig = dict[str, Any]
EffectiveMcpServer = dict[str, Any]
ToolPluginProvenance = dict[str, Any]

ConfiguredServersFn = Callable[[Mapping[str, Any]], Mapping[str, McpServerConfig]]
EffectiveServersFn = Callable[[Mapping[str, Any], Any | None], Mapping[str, EffectiveMcpServer]]
ToolPluginProvenanceFn = Callable[[Mapping[str, Any]], ToolPluginProvenance]


@dataclass(frozen=True)
class McpDelegates:
    configured_mcp_servers: ConfiguredServersFn | None = None
    effective_mcp_servers: EffectiveServersFn | None = None
    tool_plugin_provenance: ToolPluginProvenanceFn | None = None


@dataclass
class McpManager:
    plugins_manager: Any
    delegates: McpDelegates = field(default_factory=McpDelegates)

    async def configured_servers(self, config: Any) -> dict[str, McpServerConfig]:
        mcp_config = await self._to_mcp_config(config)
        delegate = self.delegates.configured_mcp_servers or configured_mcp_servers
        return _server_map(delegate(mcp_config), "configured_mcp_servers")

    async def effective_servers(self, config: Any, auth: Any | None = None) -> dict[str, EffectiveMcpServer]:
        mcp_config = await self._to_mcp_config(config)
        delegate = self.delegates.effective_mcp_servers or effective_mcp_servers
        return _server_map(delegate(mcp_config, auth), "effective_mcp_servers")

    async def tool_plugin_provenance(self, config: Any) -> ToolPluginProvenance:
        mcp_config = await self._to_mcp_config(config)
        delegate = self.delegates.tool_plugin_provenance or collect_tool_plugin_provenance
        provenance = delegate(mcp_config)
        if not isinstance(provenance, Mapping):
            raise TypeError("tool_plugin_provenance must return a mapping")
        return dict(provenance)

    async def _to_mcp_config(self, config: Any) -> Mapping[str, Any]:
        to_mcp_config = getattr(config, "to_mcp_config", None)
        if callable(to_mcp_config):
            value = to_mcp_config(self.plugins_manager)
            if isinstance(value, Awaitable) or inspect.isawaitable(value):
                value = await value
            if not isinstance(value, Mapping):
                raise TypeError("config.to_mcp_config() must return a mapping")
            return value
        if isinstance(config, Mapping):
            value = config.get("mcp_config", config)
            if not isinstance(value, Mapping):
                raise TypeError("config['mcp_config'] must be a mapping")
            return value
        raise TypeError("config must expose to_mcp_config() or be a mapping")


def configured_mcp_servers(mcp_config: Mapping[str, Any]) -> dict[str, McpServerConfig]:
    if not isinstance(mcp_config, Mapping):
        raise TypeError("mcp_config must be a mapping")
    servers = mcp_config.get("configured_servers", mcp_config.get("servers", {}))
    return _server_map(servers, "configured_servers")


def effective_mcp_servers(mcp_config: Mapping[str, Any], auth: Any | None = None) -> dict[str, EffectiveMcpServer]:
    if not isinstance(mcp_config, Mapping):
        raise TypeError("mcp_config must be a mapping")
    servers = mcp_config.get("effective_servers")
    if servers is None:
        servers = configured_mcp_servers(mcp_config)
    _ = auth
    return _server_map(servers, "effective_servers")


def collect_tool_plugin_provenance(mcp_config: Mapping[str, Any]) -> ToolPluginProvenance:
    if not isinstance(mcp_config, Mapping):
        raise TypeError("mcp_config must be a mapping")
    value = mcp_config.get("tool_plugin_provenance", {})
    if not isinstance(value, Mapping):
        raise TypeError("tool_plugin_provenance must be a mapping")
    return dict(value)


def _server_map(value: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    output: dict[str, dict[str, Any]] = {}
    for key, server in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{label} keys must be strings")
        if not isinstance(server, Mapping):
            raise TypeError(f"{label} values must be mappings")
        output[key] = dict(server)
    return output


__all__ = [
    "EffectiveMcpServer",
    "McpDelegates",
    "McpManager",
    "McpServerConfig",
    "ToolPluginProvenance",
    "collect_tool_plugin_provenance",
    "configured_mcp_servers",
    "effective_mcp_servers",
]
