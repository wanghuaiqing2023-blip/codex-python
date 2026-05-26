import unittest

from pycodex.core import (
    CODEX_APPS_MCP_SERVER_NAME,
    DIRECT_MCP_TOOL_EXPOSURE_THRESHOLD,
    AppInfo,
    AppsConfig,
    AppsDefaultConfig,
    McpToolExposure,
    ToolInfo,
    build_mcp_tool_exposure,
    sanitize_name,
)
from pycodex.protocol import Tool, ToolName


def make_connector(connector_id: str, name: str) -> AppInfo:
    return AppInfo(
        id=connector_id,
        name=name,
        is_accessible=True,
        is_enabled=True,
    )


def make_mcp_tool(
    server_name: str,
    tool_name: str,
    callable_namespace: str,
    callable_name: str,
    connector_id: str | None = None,
    connector_name: str | None = None,
) -> ToolInfo:
    return ToolInfo(
        server_name=server_name,
        callable_namespace=callable_namespace,
        callable_name=callable_name,
        tool=Tool(
            name=tool_name,
            description=f"Test tool: {tool_name}",
            input_schema={},
        ),
        connector_id=connector_id,
        connector_name=connector_name,
    )


def codex_app_tool(connector_id: str = "calendar") -> ToolInfo:
    connector_name = "Calendar"
    return make_mcp_tool(
        CODEX_APPS_MCP_SERVER_NAME,
        "calendar_create_event",
        f"mcp__{CODEX_APPS_MCP_SERVER_NAME}__{sanitize_name(connector_name)}",
        "_create_event",
        connector_id,
        connector_name,
    )


def numbered_mcp_tools(count: int) -> tuple[ToolInfo, ...]:
    return tuple(
        make_mcp_tool(
            "rmcp",
            f"tool_{index}",
            "mcp__rmcp__",
            f"tool_{index}",
        )
        for index in range(count)
    )


def tool_names(tools: tuple[ToolInfo, ...]) -> set[ToolName]:
    return {tool.canonical_tool_name() for tool in tools}


class McpToolExposureTests(unittest.TestCase):
    def test_exposure_dataclass_accepts_mappings(self) -> None:
        info = make_mcp_tool("rmcp", "echo", "mcp__rmcp__", "echo")
        mapping = {
            "server_name": info.server_name,
            "callable_namespace": info.callable_namespace,
            "callable_name": info.callable_name,
            "tool": info.tool.to_mapping(),
        }

        exposure = McpToolExposure(direct_tools=(mapping,), deferred_tools=None)

        self.assertEqual(exposure.direct_tools, (info,))

    def test_directly_exposes_small_effective_tool_sets(self) -> None:
        mcp_tools = numbered_mcp_tools(DIRECT_MCP_TOOL_EXPOSURE_THRESHOLD - 1)

        exposure = build_mcp_tool_exposure(
            mcp_tools,
            search_tool_enabled=True,
        )

        self.assertEqual(tool_names(exposure.direct_tools), tool_names(mcp_tools))
        self.assertIsNone(exposure.deferred_tools)

    def test_searches_large_effective_tool_sets(self) -> None:
        mcp_tools = numbered_mcp_tools(DIRECT_MCP_TOOL_EXPOSURE_THRESHOLD)

        exposure = build_mcp_tool_exposure(
            mcp_tools,
            search_tool_enabled=True,
        )

        self.assertEqual(exposure.direct_tools, ())
        self.assertIsNotNone(exposure.deferred_tools)
        self.assertEqual(tool_names(exposure.deferred_tools or ()), tool_names(mcp_tools))

    def test_search_tool_disabled_keeps_large_tool_sets_direct(self) -> None:
        mcp_tools = numbered_mcp_tools(DIRECT_MCP_TOOL_EXPOSURE_THRESHOLD)

        exposure = build_mcp_tool_exposure(
            mcp_tools,
            search_tool_enabled=False,
        )

        self.assertEqual(tool_names(exposure.direct_tools), tool_names(mcp_tools))
        self.assertIsNone(exposure.deferred_tools)

    def test_always_defer_feature_defers_apps_too(self) -> None:
        regular = make_mcp_tool("rmcp", "tool", "mcp__rmcp__", "tool")
        app = codex_app_tool()

        exposure = build_mcp_tool_exposure(
            (regular, app),
            connectors=(make_connector("calendar", "Calendar"),),
            search_tool_enabled=True,
            always_defer_mcp_tools=True,
        )

        self.assertEqual(exposure.direct_tools, ())
        deferred_tool_names = tool_names(exposure.deferred_tools or ())
        self.assertIn(ToolName.namespaced("mcp__rmcp__", "tool"), deferred_tool_names)
        self.assertIn(
            ToolName.namespaced("mcp__codex-apps__calendar", "_create_event"),
            deferred_tool_names,
        )

    def test_codex_app_tools_require_accessible_enabled_connectors(self) -> None:
        app = codex_app_tool()
        disabled_config = AppsConfig(default=AppsDefaultConfig(enabled=False))

        no_connector = build_mcp_tool_exposure(
            (app,),
            search_tool_enabled=True,
            always_defer_mcp_tools=True,
        )
        disabled = build_mcp_tool_exposure(
            (app,),
            connectors=(make_connector("calendar", "Calendar"),),
            apps_config=disabled_config,
            search_tool_enabled=True,
            always_defer_mcp_tools=True,
        )

        self.assertIsNone(no_connector.deferred_tools)
        self.assertIsNone(disabled.deferred_tools)


if __name__ == "__main__":
    unittest.main()
