from __future__ import annotations

import asyncio

from pycodex.tui.app.plugin_mentions import (
    PluginAvailability,
    PluginCapabilitySummary,
    PluginInterface,
    PluginListResponse,
    PluginMarketplaceEntry,
    PluginSummary,
    fetch_plugin_mentions,
    plugin_mention_description,
    plugin_mention_display_name,
    plugin_mentions_from_list_response,
)


def plugin_summary(name: str) -> PluginSummary:
    return PluginSummary(
        id=f"{name}@server-marketplace",
        name=name,
        installed=True,
        enabled=True,
        availability=PluginAvailability.Available,
        interface=None,
    )


def test_plugin_mentions_use_plugin_list_summaries_and_gui_eligibility() -> None:
    active = plugin_summary("active")
    disabled_by_admin = plugin_summary("disabled-by-admin")
    disabled_by_admin.availability = PluginAvailability.DisabledByAdmin
    disabled = plugin_summary("disabled")
    disabled.enabled = False
    uninstalled = plugin_summary("uninstalled")
    uninstalled.installed = False
    response = PluginListResponse(
        marketplaces=[
            PluginMarketplaceEntry(
                name="server-marketplace",
                plugins=[active, disabled_by_admin, disabled, uninstalled],
            )
        ]
    )

    assert plugin_mentions_from_list_response(response) == [
        PluginCapabilitySummary(
            config_name="active@server-marketplace",
            display_name="active",
            description="server-marketplace",
            has_skills=False,
            mcp_server_names=[],
            app_connector_ids=[],
        )
    ]


def test_plugin_mention_display_name_and_description_trim_interface_values() -> None:
    plugin = PluginSummary(
        id="sample@market",
        name="fallback-name",
        interface=PluginInterface(display_name="  Pretty Plugin  ", short_description="  Does things  "),
    )

    assert plugin_mention_display_name(plugin) == "Pretty Plugin"
    assert plugin_mention_description(" marketplace ", plugin) == "Does things"


def test_plugin_mention_description_falls_back_to_non_empty_marketplace() -> None:
    plugin = PluginSummary(
        id="sample@market",
        name="sample",
        interface=PluginInterface(display_name="", short_description="   "),
    )

    assert plugin_mention_display_name(plugin) == "sample"
    assert plugin_mention_description("  marketplace  ", plugin) == "marketplace"
    assert plugin_mention_description("   ", plugin) is None


def test_fetch_plugin_mentions_uses_request_handle_response() -> None:
    response = PluginListResponse(
        marketplaces=[
            PluginMarketplaceEntry(
                name="server-marketplace",
                plugins=[plugin_summary("active")],
            )
        ]
    )

    async def request_plugin_list(cwd):
        assert cwd == "repo"
        return response

    mentions = asyncio.run(fetch_plugin_mentions(request_plugin_list, "repo"))

    assert mentions == [
        PluginCapabilitySummary(
            config_name="active@server-marketplace",
            display_name="active",
            description="server-marketplace",
            has_skills=False,
            mcp_server_names=[],
            app_connector_ids=[],
        )
    ]


def test_fetch_plugin_mentions_accepts_request_handle_method() -> None:
    response = PluginListResponse(
        marketplaces=[
            PluginMarketplaceEntry(
                name=" server-marketplace ",
                plugins=[plugin_summary("active")],
            )
        ]
    )

    class Handle:
        def __init__(self) -> None:
            self.cwd = None

        def request_plugin_list(self, cwd):
            self.cwd = cwd
            return response

    handle = Handle()

    mentions = asyncio.run(fetch_plugin_mentions(handle, "repo"))

    assert handle.cwd == "repo"
    assert mentions == [
        PluginCapabilitySummary(
            config_name="active@server-marketplace",
            display_name="active",
            description="server-marketplace",
            has_skills=False,
            mcp_server_names=[],
            app_connector_ids=[],
        )
    ]
