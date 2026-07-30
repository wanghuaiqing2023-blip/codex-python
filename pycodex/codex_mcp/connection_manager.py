"""MCP client lifecycle from ``codex-mcp/src/connection_manager.rs``."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from pycodex.config.mcp_types import McpServerConfig
from .elicitation import ElicitationRequestManager
from .mcp import McpSnapshotDetail
from .rmcp_client import ManagedClient, start_managed_client
from .runtime import McpRuntimeContext
from .server import EffectiveMcpServer
from .tools import ToolFilter, ToolInfo, filter_tools, normalize_tools_for_model_with_prefix


class McpConnectionManager:
    def __init__(
        self,
        servers: Mapping[str, McpServerConfig | Any] | None = None,
        *,
        tools: Mapping[str, Any] | tuple[Any, ...] | list[Any] | None = None,
        resources: Mapping[str, Any] | None = None,
        resource_templates: Mapping[str, Any] | None = None,
        resource_contents: Mapping[tuple[str, str], Any] | None = None,
        runtime_context: McpRuntimeContext | None = None,
        prefix_mcp_tool_names: bool = True,
        elicitation_manager: ElicitationRequestManager | None = None,
    ) -> None:
        self._servers = {
            name: _server_config(value)
            for name, value in dict(servers or {}).items()
        }
        self._tools = dict(tools) if isinstance(tools, Mapping) else tuple(tools or ())
        self._resources = dict(resources or {})
        self._resource_templates = dict(resource_templates or {})
        self._resource_contents = dict(resource_contents or {})
        self._runtime_context = runtime_context or _default_runtime_context()
        self._prefix_mcp_tool_names = prefix_mcp_tool_names
        self._elicitation_manager = elicitation_manager
        self._clients: dict[str, ManagedClient] = {}
        self._startup_errors: dict[str, Exception] = {}
        self._started = False
        self._closed = False
        self._start_lock = asyncio.Lock()

    @classmethod
    async def from_effective_servers(
        cls,
        servers: Mapping[str, EffectiveMcpServer],
        *,
        runtime_context: McpRuntimeContext,
        prefix_mcp_tool_names: bool = True,
        elicitation_manager: ElicitationRequestManager | None = None,
    ) -> "McpConnectionManager":
        manager = cls(
            {
                name: server.configured_config()
                for name, server in servers.items()
            },
            runtime_context=runtime_context,
            prefix_mcp_tool_names=prefix_mcp_tool_names,
            elicitation_manager=elicitation_manager,
        )
        await manager.ensure_started()
        return manager

    def replace_servers(self, servers: Mapping[str, Any] | None) -> None:
        if self._clients:
            raise RuntimeError("cannot replace MCP servers after clients have started")
        self._servers = {
            name: _server_config(value)
            for name, value in dict(servers or {}).items()
        }
        self._started = False
        self._startup_errors.clear()

    async def replace_from_config(self, config: Any, reviewer: Any = None) -> None:
        del reviewer
        servers = getattr(config, "mcp_servers", config)
        await self.close()
        self._closed = False
        self._clients.clear()
        self._servers = {
            name: _server_config(value)
            for name, value in dict(servers or {}).items()
        }
        self._started = False
        self._startup_errors.clear()
        await self.ensure_started()

    async def refresh(self, config: Any, reviewer: Any = None) -> None:
        await self.replace_from_config(config, reviewer)

    def configured_servers(self) -> dict[str, McpServerConfig]:
        return dict(self._servers)

    def has_servers(self) -> bool:
        return bool(self._servers)

    async def ensure_started(self) -> None:
        if self._started:
            return
        if self._closed:
            raise RuntimeError("MCP connection manager is shut down")
        async with self._start_lock:
            if self._started:
                return
            tasks = [
                self._start_one(name, config)
                for name, config in self._servers.items()
                if config.enabled
            ]
            if tasks:
                await asyncio.gather(*tasks)
            self._started = True

    async def _start_one(self, name: str, config: McpServerConfig) -> None:
        sender = (
            self._elicitation_manager.make_sender(name)
            if self._elicitation_manager is not None
            else None
        )
        try:
            self._clients[name] = await start_managed_client(
                name,
                config,
                self._runtime_context,
                send_elicitation=sender,
            )
        except Exception as exc:
            self._startup_errors[name] = exc
            if config.required:
                raise

    async def list_all_tools(self) -> tuple[ToolInfo, ...]:
        await self.ensure_started()
        tools: list[ToolInfo] = list(_injected_tools(self._tools))
        for name, client in self._clients.items():
            listed = await client.list_tools()
            tools.extend(filter_tools(listed, ToolFilter.from_config(self._servers[name])))
        return normalize_tools_for_model_with_prefix(
            tools,
            self._prefix_mcp_tool_names,
        )

    async def list_resources(self, server: str, cursor: str | None = None) -> Any:
        _require_server(self._servers, server)
        if server in self._resources:
            return _page("resources", self._resources[server], cursor)
        await self.ensure_started()
        return await self._client_by_name(server).list_resources(cursor)

    async def list_all_resources(self) -> dict[str, tuple[Any, ...]]:
        await self.ensure_started()
        result = {
            server: tuple(values)
            for server, values in self._resources.items()
            if server in self._servers
        }
        for server, client in self._clients.items():
            response = await client.list_resources()
            result[server] = tuple(_field(response, "resources", default=()) or ())
        return result

    async def list_resource_templates(
        self,
        server: str,
        cursor: str | None = None,
    ) -> Any:
        _require_server(self._servers, server)
        if server in self._resource_templates:
            return _page("resourceTemplates", self._resource_templates[server], cursor)
        await self.ensure_started()
        return await self._client_by_name(server).list_resource_templates(cursor)

    async def list_all_resource_templates(self) -> dict[str, tuple[Any, ...]]:
        await self.ensure_started()
        result = {
            server: tuple(values)
            for server, values in self._resource_templates.items()
            if server in self._servers
        }
        for server, client in self._clients.items():
            response = await client.list_resource_templates()
            result[server] = tuple(
                _field(
                    response,
                    "resourceTemplates",
                    "resource_templates",
                    default=(),
                )
                or ()
            )
        return result

    async def read_resource(self, server: str, uri: str) -> Any:
        _require_server(self._servers, server)
        if (server, uri) in self._resource_contents:
            return self._resource_contents[(server, uri)]
        await self.ensure_started()
        return await self._client_by_name(server).read_resource(uri)

    async def call_tool(
        self,
        server: str,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> Any:
        _require_server(self._servers, server)
        await self.ensure_started()
        return await self._client_by_name(server).call_tool(
            tool_name,
            arguments,
            meta,
        )

    async def resolve_elicitation(
        self,
        server_name: str,
        request_id: Any,
        response: Any,
    ) -> None:
        if self._elicitation_manager is None:
            raise ValueError("elicitation request not found")
        await self._elicitation_manager.resolve(server_name, request_id, response)

    def elicitations_auto_deny(self) -> bool:
        return (
            self._elicitation_manager.auto_deny()
            if self._elicitation_manager is not None
            else False
        )

    def set_elicitations_auto_deny(self, value: bool) -> None:
        if self._elicitation_manager is not None:
            self._elicitation_manager.set_auto_deny(value)

    def startup_errors(self) -> dict[str, Exception]:
        return dict(self._startup_errors)

    async def begin_shutdown(self) -> Any:
        return self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        clients = tuple(self._clients.values())
        self._clients.clear()
        if clients:
            await asyncio.gather(
                *(client.close() for client in clients),
                return_exceptions=True,
            )

    def _client_by_name(self, name: str) -> ManagedClient:
        try:
            return self._clients[name]
        except KeyError as exc:
            if name in self._startup_errors:
                raise RuntimeError(str(self._startup_errors[name])) from exc
            raise ValueError(f"MCP server `{name}` is not connected") from exc


def _server_config(value: Any) -> McpServerConfig:
    if isinstance(value, EffectiveMcpServer):
        return value.configured_config()
    if isinstance(value, McpServerConfig):
        return value
    if isinstance(value, Mapping):
        return McpServerConfig.from_mapping(value)
    raise TypeError("MCP server config must be McpServerConfig or mapping")


def _default_runtime_context() -> McpRuntimeContext:
    from pathlib import Path

    from pycodex.exec_server.environment import EnvironmentManager

    return McpRuntimeContext(EnvironmentManager.default_for_tests(), Path.cwd())


def _require_server(servers: Mapping[str, Any], server: str) -> None:
    if not isinstance(server, str) or not server.strip():
        raise ValueError("server must be a non-empty string")
    if server not in servers:
        raise ValueError(f"unknown MCP server: {server}")


def _injected_tools(value: Any) -> tuple[ToolInfo, ...]:
    raw = tuple(value.values()) if isinstance(value, Mapping) else tuple(value or ())
    return tuple(item for item in raw if isinstance(item, ToolInfo))


def _page(field: str, values: Any, cursor: str | None) -> dict[str, Any]:
    return {field: list(values or ()), "nextCursor": cursor}


def _field(value: Any, *names: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        for name in names:
            if name in value:
                return value[name]
        return default
    for name in names:
        if hasattr(value, name):
            return getattr(value, name)
    return default


__all__ = ["McpConnectionManager", "McpSnapshotDetail"]
