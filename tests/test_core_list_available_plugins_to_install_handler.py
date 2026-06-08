from pycodex.core.tools.handlers import list_available_plugins_to_install as facade
from pycodex.core.tools.handlers.request_plugin_install import (
    MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS,
    ListAvailablePluginsToInstallHandler,
    create_list_available_plugins_to_install_tool,
)
from pycodex.tools import DiscoverableToolType, RequestPluginInstallEntry


def test_facade_exports_rust_coordinate_handler_surface():
    # Rust source: codex-rs/core/src/tools/handlers/list_available_plugins_to_install.rs.
    assert facade.MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS == (
        MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS
    )
    assert facade.ListAvailablePluginsToInstallHandler is ListAvailablePluginsToInstallHandler
    assert facade.create_list_available_plugins_to_install_tool is create_list_available_plugins_to_install_tool


def test_facade_handler_preserves_sorting_and_description_truncation():
    # Rust tests: list_tool_does_not_support_parallel_calls; result_truncates_candidate_descriptions.
    handler = facade.ListAvailablePluginsToInstallHandler.new(
        [
            RequestPluginInstallEntry(
                id="sample@openai-curated",
                name="Sample Plugin",
                description="x" * (MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS + 1),
                tool_type=DiscoverableToolType.PLUGIN,
                has_skills=True,
                mcp_server_names=("sample-mcp",),
                app_connector_ids=("connector-sample",),
            ),
            RequestPluginInstallEntry(
                id="calendar@openai-curated",
                name="Calendar",
                description="calendar",
                tool_type=DiscoverableToolType.PLUGIN,
                has_skills=False,
            ),
        ]
    )

    result = handler.result()

    assert handler.supports_parallel_tool_calls() is False
    assert [tool.id for tool in result.tools] == [
        "calendar@openai-curated",
        "sample@openai-curated",
    ]
    assert len(result.tools[1].description) == MAX_LIST_AVAILABLE_PLUGINS_TO_INSTALL_DESCRIPTION_CHARS
