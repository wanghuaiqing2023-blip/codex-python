import json
import unittest

from pycodex.core import (
    LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
    REQUEST_PLUGIN_INSTALL_TOOL_NAME,
    TUI_CLIENT_NAME,
    AppInfo,
    DiscoverablePluginInfo,
    DiscoverableTool,
    DiscoverableToolAction,
    DiscoverableToolType,
    ListAvailablePluginsToInstallResult,
    RequestPluginInstallEntry,
    collect_request_plugin_install_entries,
    filter_request_plugin_install_discoverable_tools_for_client,
)


def calendar_connector() -> DiscoverableTool:
    return DiscoverableTool.connector(
        AppInfo(
            id="connector_google_calendar",
            name="Google Calendar",
            description="Plan events and schedules.",
            install_url="https://example.test/google-calendar",
            is_accessible=False,
            is_enabled=True,
        )
    )


def slack_plugin() -> DiscoverableTool:
    return DiscoverableTool.plugin(
        DiscoverablePluginInfo(
            id="slack@openai-curated",
            name="Slack",
            description="Search Slack messages",
            has_skills=True,
            mcp_server_names=("slack",),
            app_connector_ids=("connector_slack",),
        )
    )


class ToolDiscoveryTests(unittest.TestCase):
    def test_discoverable_tool_enums_use_expected_wire_names(self) -> None:
        encoded = json.loads(
            json.dumps(
                {
                    "tool_type": DiscoverableToolType.CONNECTOR,
                    "action_type": DiscoverableToolAction.INSTALL,
                }
            )
        )

        self.assertEqual(
            encoded,
            {
                "tool_type": "connector",
                "action_type": "install",
            },
        )

    def test_tool_name_constants_match_upstream_contract(self) -> None:
        self.assertEqual(
            LIST_AVAILABLE_PLUGINS_TO_INSTALL_TOOL_NAME,
            "list_available_plugins_to_install",
        )
        self.assertEqual(REQUEST_PLUGIN_INSTALL_TOOL_NAME, "request_plugin_install")

    def test_discoverable_tool_accessors_delegate_to_inner_metadata(self) -> None:
        connector = calendar_connector()
        plugin = slack_plugin()

        self.assertEqual(connector.tool_type(), DiscoverableToolType.CONNECTOR)
        self.assertEqual(connector.id(), "connector_google_calendar")
        self.assertEqual(connector.name(), "Google Calendar")
        self.assertEqual(
            connector.install_url(),
            "https://example.test/google-calendar",
        )
        self.assertEqual(plugin.tool_type(), DiscoverableToolType.PLUGIN)
        self.assertEqual(plugin.id(), "slack@openai-curated")
        self.assertEqual(plugin.name(), "Slack")
        self.assertIsNone(plugin.install_url())

    def test_filter_for_codex_tui_omits_plugins(self) -> None:
        connector = calendar_connector()
        plugin = slack_plugin()

        self.assertEqual(
            filter_request_plugin_install_discoverable_tools_for_client(
                [connector, plugin],
                TUI_CLIENT_NAME,
            ),
            [connector],
        )

    def test_filter_for_other_clients_preserves_all_tools(self) -> None:
        tools = [calendar_connector(), slack_plugin()]

        self.assertEqual(
            filter_request_plugin_install_discoverable_tools_for_client(
                tools,
                "codex-desktop",
            ),
            tools,
        )
        self.assertEqual(
            filter_request_plugin_install_discoverable_tools_for_client(tools, None),
            tools,
        )

    def test_collect_request_plugin_install_entries(self) -> None:
        entries = collect_request_plugin_install_entries(
            [calendar_connector(), slack_plugin()]
        )

        self.assertEqual(
            entries,
            [
                RequestPluginInstallEntry(
                    id="connector_google_calendar",
                    name="Google Calendar",
                    description="Plan events and schedules.",
                    tool_type=DiscoverableToolType.CONNECTOR,
                    has_skills=False,
                    mcp_server_names=(),
                    app_connector_ids=(),
                ),
                RequestPluginInstallEntry(
                    id="slack@openai-curated",
                    name="Slack",
                    description="Search Slack messages",
                    tool_type=DiscoverableToolType.PLUGIN,
                    has_skills=True,
                    mcp_server_names=("slack",),
                    app_connector_ids=("connector_slack",),
                ),
            ],
        )

    def test_list_available_result_serializes_to_wire_shape(self) -> None:
        result = ListAvailablePluginsToInstallResult(
            collect_request_plugin_install_entries(
                [calendar_connector(), slack_plugin()]
            )
        )

        self.assertEqual(
            result.to_mapping(),
            {
                "tools": [
                    {
                        "id": "connector_google_calendar",
                        "name": "Google Calendar",
                        "description": "Plan events and schedules.",
                        "tool_type": "connector",
                        "has_skills": False,
                        "mcp_server_names": [],
                        "app_connector_ids": [],
                    },
                    {
                        "id": "slack@openai-curated",
                        "name": "Slack",
                        "description": "Search Slack messages",
                        "tool_type": "plugin",
                        "has_skills": True,
                        "mcp_server_names": ["slack"],
                        "app_connector_ids": ["connector_slack"],
                    },
                ]
            },
        )

    def test_mapping_round_trips_for_discoverable_tools(self) -> None:
        connector = calendar_connector()
        plugin = slack_plugin()

        self.assertEqual(DiscoverableTool.from_mapping(connector.to_mapping()), connector)
        self.assertEqual(DiscoverableTool.from_mapping(plugin.to_mapping()), plugin)


if __name__ == "__main__":
    unittest.main()
