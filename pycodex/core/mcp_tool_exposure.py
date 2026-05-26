"""MCP tool exposure planning ported from Codex core.

This mirrors the dependency-free behavior in
``codex-rs/core/src/mcp_tool_exposure.rs``: compute the effective MCP tool set,
filter Codex Apps tools by accessible connectors and app policy, then either
expose tools directly or defer them behind ``tool_search``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.core.connectors import AppsConfig, codex_app_tool_is_enabled
from pycodex.core.mcp_tool_handler import ToolInfo
from pycodex.core.request_plugin_install import CODEX_APPS_MCP_SERVER_NAME
from pycodex.core.tool_discovery import AppInfo

JsonValue = Any

DIRECT_MCP_TOOL_EXPOSURE_THRESHOLD = 100


@dataclass(frozen=True)
class McpToolExposure:
    direct_tools: tuple[ToolInfo, ...]
    deferred_tools: tuple[ToolInfo, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "direct_tools", tuple(_coerce_tool(tool) for tool in self.direct_tools))
        if self.deferred_tools is not None:
            object.__setattr__(
                self,
                "deferred_tools",
                tuple(_coerce_tool(tool) for tool in self.deferred_tools),
            )


def build_mcp_tool_exposure(
    all_mcp_tools: Iterable[ToolInfo | Mapping[str, JsonValue]],
    connectors: Iterable[AppInfo | Mapping[str, JsonValue]] | None = None,
    apps_config: AppsConfig | Mapping[str, JsonValue] | None = None,
    *,
    search_tool_enabled: bool,
    always_defer_mcp_tools: bool = False,
) -> McpToolExposure:
    tools = tuple(_coerce_tool(tool) for tool in all_mcp_tools)
    effective_tools = list(_filter_non_codex_apps_mcp_tools_only(tools))

    if connectors is not None:
        effective_tools.extend(_filter_codex_apps_mcp_tools(tools, connectors, apps_config))

    should_defer = search_tool_enabled and (
        always_defer_mcp_tools
        or len(effective_tools) >= DIRECT_MCP_TOOL_EXPOSURE_THRESHOLD
    )

    if not should_defer:
        return McpToolExposure(direct_tools=tuple(effective_tools), deferred_tools=None)

    return McpToolExposure(
        direct_tools=(),
        deferred_tools=tuple(effective_tools) if effective_tools else None,
    )


def _filter_non_codex_apps_mcp_tools_only(tools: tuple[ToolInfo, ...]) -> tuple[ToolInfo, ...]:
    return tuple(tool for tool in tools if tool.server_name != CODEX_APPS_MCP_SERVER_NAME)


def _filter_codex_apps_mcp_tools(
    tools: tuple[ToolInfo, ...],
    connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    apps_config: AppsConfig | Mapping[str, JsonValue] | None,
) -> tuple[ToolInfo, ...]:
    allowed = {_coerce_app_info(connector).id for connector in connectors}
    return tuple(
        tool
        for tool in tools
        if tool.server_name == CODEX_APPS_MCP_SERVER_NAME
        and tool.connector_id is not None
        and tool.connector_id in allowed
        and codex_app_tool_is_enabled(tool, apps_config)
    )


def _coerce_tool(value: ToolInfo | Mapping[str, JsonValue]) -> ToolInfo:
    return value if isinstance(value, ToolInfo) else ToolInfo.from_mapping(value)


def _coerce_app_info(value: AppInfo | Mapping[str, JsonValue]) -> AppInfo:
    return value if isinstance(value, AppInfo) else AppInfo.from_mapping(value)


__all__ = [
    "DIRECT_MCP_TOOL_EXPOSURE_THRESHOLD",
    "McpToolExposure",
    "build_mcp_tool_exposure",
]
