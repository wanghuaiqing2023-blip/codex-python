"""Effective MCP server ownership from ``codex-mcp/src/server.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from pycodex.config.mcp_types import McpServerConfig


@dataclass(frozen=True)
class EffectiveMcpServer:
    _configured: McpServerConfig

    @classmethod
    def configured(cls, config: McpServerConfig) -> "EffectiveMcpServer":
        return cls(config)

    def configured_config(self) -> McpServerConfig:
        return self._configured

    def enabled(self) -> bool:
        return self._configured.enabled

    def required(self) -> bool:
        return self._configured.required


@dataclass(frozen=True)
class McpServerMetadata:
    pollutes_memory: bool
    origin: str | None
    supports_parallel_tool_calls: bool

    @classmethod
    def from_server(cls, server: EffectiveMcpServer) -> "McpServerMetadata":
        config = server.configured_config()
        transport = config.transport
        if transport.kind == "stdio":
            origin = "stdio"
        elif transport.url:
            parsed = urlsplit(transport.url)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None
        else:
            origin = None
        return cls(True, origin, config.supports_parallel_tool_calls)


__all__ = ["EffectiveMcpServer", "McpServerMetadata"]
