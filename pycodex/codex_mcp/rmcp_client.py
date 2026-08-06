"""Managed RMCP client startup from ``codex-mcp/src/rmcp_client.rs``."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Mapping

from pycodex.config.mcp_types import McpServerConfig
from pycodex.protocol import Tool
from .codex_apps import (
    filter_disallowed_codex_apps_tools,
    normalize_codex_apps_callable_name,
    normalize_codex_apps_callable_namespace,
    normalize_codex_apps_tool_title,
)
from .mcp import CODEX_APPS_MCP_SERVER_NAME
from .runtime import McpRuntimeContext
from .server import EffectiveMcpServer, McpServerMetadata
from .tools import ToolInfo


MCP_SANDBOX_STATE_META_CAPABILITY = "codex/sandbox-state-meta"
DEFAULT_STARTUP_TIMEOUT = 30.0
DEFAULT_TOOL_TIMEOUT = 120.0


class StartupOutcomeErrorKind(str, Enum):
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class StartupOutcomeError(RuntimeError):
    def __init__(self, kind: StartupOutcomeErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass
class ManagedClient:
    server_name: str
    client: Any
    metadata: McpServerMetadata
    tool_timeout: float
    listed_tools_snapshot: tuple[ToolInfo, ...] = ()

    async def list_tools(self) -> tuple[ToolInfo, ...]:
        result = await self.client.list_tools_with_connector_ids(
            timeout=self.tool_timeout
        )
        tools = []
        for item in result.tools:
            tool = item.tool if isinstance(item.tool, Tool) else Tool.from_mcp_value(item.tool)
            if self.server_name == CODEX_APPS_MCP_SERVER_NAME:
                connector_id = item.connector_id
                connector_name = item.connector_name
                connector_description = item.connector_description
            else:
                connector_id = None
                connector_name = None
                connector_description = None
            callable_name = normalize_codex_apps_callable_name(
                self.server_name,
                tool.name,
                connector_id,
                connector_name,
            )
            callable_namespace = normalize_codex_apps_callable_namespace(
                self.server_name,
                connector_name,
            )
            if tool.title is not None:
                normalized_title = normalize_codex_apps_tool_title(
                    self.server_name,
                    connector_name,
                    tool.title,
                )
                if normalized_title != tool.title:
                    tool = replace(tool, title=normalized_title)
            tools.append(
                ToolInfo(
                    server_name=self.server_name,
                    supports_parallel_tool_calls=self.metadata.supports_parallel_tool_calls,
                    server_origin=self.metadata.origin,
                    callable_name=callable_name,
                    callable_namespace=callable_namespace,
                    namespace_description=connector_description,
                    tool=tool,
                    connector_id=connector_id,
                    connector_name=connector_name,
                )
            )
        listed = tuple(tools)
        if self.server_name == CODEX_APPS_MCP_SERVER_NAME:
            listed = filter_disallowed_codex_apps_tools(listed)
        self.listed_tools_snapshot = listed
        return listed

    async def list_resources(self, cursor: str | None = None) -> Any:
        return await self.client.list_resources(
            {"cursor": cursor} if cursor is not None else {},
            timeout=self.tool_timeout,
        )

    async def list_resource_templates(self, cursor: str | None = None) -> Any:
        return await self.client.list_resource_templates(
            {"cursor": cursor} if cursor is not None else {},
            timeout=self.tool_timeout,
        )

    async def read_resource(self, uri: str) -> Any:
        return await self.client.read_resource(
            {"uri": uri},
            timeout=self.tool_timeout,
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
        meta: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self.client.call_tool(
            tool_name,
            arguments,
            meta,
            timeout=self.tool_timeout,
        )

    async def close(self) -> None:
        await self.client.shutdown()


async def start_managed_client(
    server_name: str,
    config: McpServerConfig,
    runtime_context: McpRuntimeContext,
    *,
    send_elicitation: Any = None,
    auth_provider: Any = None,
    initialization: Mapping[str, Any] | None = None,
) -> ManagedClient:
    from pycodex.exec_server.client.http_client.reqwest_http_client import (
        ReqwestHttpClient,
    )
    from pycodex.rmcp_client import (
        ExecutorStdioServerLauncher,
        LocalStdioServerLauncher,
        RmcpClient,
    )

    if not server_name:
        raise ValueError("MCP server name must be non-empty")
    environment = runtime_context.resolve_server_environment(server_name, config)
    transport = config.transport
    client = None
    try:
        if transport.kind == "stdio":
            if environment is None:
                raise ValueError(
                    f"stdio MCP server `{server_name}` requires an environment"
                )
            if getattr(environment, "is_remote", lambda: False)():
                launcher = ExecutorStdioServerLauncher(environment.get_exec_backend())
                cwd = transport.cwd
            else:
                launcher = LocalStdioServerLauncher(
                    runtime_context.local_stdio_fallback_cwd
                )
                cwd = transport.cwd
            client = await RmcpClient.new_stdio_client(
                transport.command or "",
                transport.args,
                transport.env,
                transport.env_vars,
                cwd,
                launcher,
            )
        elif transport.kind == "streamable_http":
            http_client = (
                environment.get_http_client()
                if environment is not None
                else ReqwestHttpClient()
            )
            bearer_token = _resolve_bearer_token(transport.bearer_token_env_var)
            client = await RmcpClient.new_streamable_http_client(
                server_name,
                transport.url or "",
                bearer_token,
                transport.http_headers,
                transport.env_http_headers,
                None,
                http_client,
                auth_provider,
            )
        else:
            raise ValueError(f"unsupported MCP transport: {transport.kind}")

        await client.initialize(
            dict(initialization or _default_initialization()),
            timeout=config.startup_timeout_sec or DEFAULT_STARTUP_TIMEOUT,
            send_elicitation=send_elicitation,
        )
    except TimeoutError as exc:
        if client is not None:
            await client.shutdown()
        raise StartupOutcomeError(
            StartupOutcomeErrorKind.TIMED_OUT,
            f"MCP server `{server_name}` startup timed out",
        ) from exc
    except Exception as exc:
        if client is not None:
            await client.shutdown()
        raise StartupOutcomeError(
            StartupOutcomeErrorKind.FAILED,
            f"MCP server `{server_name}` failed to start: {exc}",
        ) from exc

    return ManagedClient(
        server_name,
        client,
        McpServerMetadata.from_server(EffectiveMcpServer.configured(config)),
        config.tool_timeout_sec or DEFAULT_TOOL_TIMEOUT,
    )


def sanitize_tool_connector_metadata(tool: Any, server_name: str) -> Any:
    if server_name == "codex_apps":
        return tool
    if not isinstance(tool, Mapping):
        return tool
    result = dict(tool)
    meta = result.get("_meta")
    if isinstance(meta, Mapping):
        result["_meta"] = {
            key: value
            for key, value in meta.items()
            if not str(key).startswith("connector")
            and not str(key).startswith("openai/")
        }
    return result


def _resolve_bearer_token(env_var: str | None) -> str | None:
    if env_var is None:
        return None
    value = os.environ.get(env_var)
    if value is None:
        raise ValueError(f"environment variable `{env_var}` is not set")
    return value


def _default_initialization() -> dict[str, Any]:
    return {
        "protocolVersion": "2025-06-18",
        "capabilities": {"elicitation": {"form": {}, "url": {}}},
        "clientInfo": {"name": "codex", "version": "0.1.0"},
    }


def _tool_name(tool: Any) -> str:
    if isinstance(tool, Mapping):
        return str(tool.get("name", ""))
    return str(getattr(tool, "name", ""))


__all__ = [
    "DEFAULT_STARTUP_TIMEOUT",
    "DEFAULT_TOOL_TIMEOUT",
    "MCP_SANDBOX_STATE_META_CAPABILITY",
    "ManagedClient",
    "StartupOutcomeError",
    "StartupOutcomeErrorKind",
    "sanitize_tool_connector_metadata",
    "start_managed_client",
]
