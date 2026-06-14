from pathlib import Path

from pycodex.tui.chatwidget.plugins import (
    ADD_MARKETPLACE_TAB_ID,
    ALL_PLUGINS_TAB_ID,
    PLUGINS_SELECTION_VIEW_ID,
    DelayedLoadingHeader,
    PluginDetail,
    PluginInstallPolicy,
    PluginInterface,
    PluginMarketplaceEntry,
    PluginSummary,
    disambiguate_duplicate_tab_labels,
    marketplace_display_name,
    marketplace_is_user_configured,
    marketplace_is_user_configured_git,
    marketplace_tab_id,
    marketplace_tab_id_from_path,
    marketplace_tab_id_matching_saved_id,
    plugin_app_summary,
    plugin_brief_description,
    plugin_brief_description_without_marketplace,
    plugin_description,
    plugin_detail_description,
    plugin_display_name,
    plugin_entries_for_marketplaces,
    plugin_hook_summary,
    plugin_mcp_summary,
    plugin_skill_summary,
    plugin_status_label,
    plugins_header,
    plugins_popup_hint_line,
    sort_plugin_entries,
)


def plugin(name, *, installed=False, enabled=False, policy=PluginInstallPolicy.AVAILABLE, interface=None):
    return PluginSummary(
        id=f"id-{name}",
        name=name,
        installed=installed,
        enabled=enabled,
        install_policy=policy,
        interface=interface,
    )


def test_constants_and_loading_header_semantics():
    assert PLUGINS_SELECTION_VIEW_ID == "plugins-selection"
    assert ALL_PLUGINS_TAB_ID == "all-plugins"
    assert ADD_MARKETPLACE_TAB_ID == "add-marketplace"

    header = DelayedLoadingHeader.new(loading_text="Loading plugins", note="Please wait")
    assert header.desired_height(80) == 3
    assert header.render_lines() == ["Plugins", "Loading plugins", "Please wait"]


def test_tab_id_matching_and_duplicate_tab_label_disambiguation():
    local = PluginMarketplaceEntry(name="local", path=Path("/tmp/market"), plugins=())
    remote = PluginMarketplaceEntry(name="remote", path=None, plugins=())

    assert marketplace_tab_id(local) == marketplace_tab_id_from_path("/tmp/market")
    assert marketplace_tab_id(remote) == "marketplace:remote"
    assert marketplace_tab_id_matching_saved_id("marketplace:/tmp", [local, remote]) == "marketplace:/tmp/market"
    assert marketplace_tab_id_matching_saved_id("marketplace:", [local]) is None
    assert disambiguate_duplicate_tab_labels(["A", "B", "A", "A"]) == ["A (1/3)", "B", "A (2/3)", "A (3/3)"]


def test_display_names_and_descriptions_trim_or_fallback_like_rust():
    summary = plugin(
        "internal-name",
        interface=PluginInterface(
            display_name="  Friendly  ",
            short_description="  Short  ",
            long_description="  Long  ",
        ),
    )
    marketplace = PluginMarketplaceEntry(
        name="market",
        interface=PluginInterface(display_name="  Market  "),
        plugins=(summary,),
    )

    assert plugin_display_name(summary) == "Friendly"
    assert marketplace_display_name(marketplace) == "Market"
    assert plugin_description(summary) == "Short"
    assert plugin_display_name(plugin("fallback")) == "fallback"


def test_status_labels_and_brief_descriptions():
    installed = plugin("installed", installed=True, enabled=True)
    disabled = plugin("disabled", installed=True, enabled=False)
    unavailable = plugin("nope", policy=PluginInstallPolicy.NOT_AVAILABLE)
    described = plugin("described", interface=PluginInterface(short_description="Useful"))

    assert plugin_status_label(installed) == "Installed"
    assert plugin_status_label(disabled) == "Disabled"
    assert plugin_status_label(unavailable) == "Not installable"
    assert plugin_status_label(plugin("available")) == "Available"
    assert plugin_brief_description(described, "Market", 9) == "Available · Market · Useful"
    assert plugin_brief_description_without_marketplace(described, 9) == "Available · Useful"


def test_entries_sort_installed_first_then_case_insensitive_name_and_tiebreakers():
    market = PluginMarketplaceEntry(
        name="m",
        plugins=(
            plugin("zeta"),
            plugin("Alpha", installed=True, enabled=True),
            plugin("alpha", installed=True, enabled=True),
        ),
    )
    entries = plugin_entries_for_marketplaces([market])

    sort_plugin_entries(entries)

    assert [entry.display_name for entry in entries] == ["Alpha", "alpha", "zeta"]


def test_detail_summaries_and_config_helpers():
    detail = PluginDetail(
        summary=plugin(
            "p",
            interface=PluginInterface(short_description="Short", long_description="Long"),
        ),
        skills=({"name": "skill-a"}, {"name": "skill-b"}),
        apps=({"name": "app-a"},),
        hooks=({"event_name": "BeforeCommand"}, {"event_name": "BeforeCommand"}, {"event_name": "AfterCommand"}),
        mcp_servers=("server-a", "server-b"),
    )

    assert plugin_detail_description(detail) == "Long"
    assert plugin_skill_summary(detail) == "skill-a, skill-b"
    assert plugin_app_summary(detail) == "app-a"
    assert plugin_hook_summary(detail) == "BeforeCommand (2), AfterCommand (1)"
    assert plugin_mcp_summary(detail) == "server-a, server-b"
    assert plugin_skill_summary(PluginDetail(summary=plugin("empty"))) == "No plugin skills."
    assert plugin_app_summary(PluginDetail(summary=plugin("empty"))) == "No plugin apps."
    assert plugin_hook_summary(PluginDetail(summary=plugin("empty"))) == "No plugin hooks."
    assert plugin_mcp_summary(PluginDetail(summary=plugin("empty"))) == "No plugin MCP servers."

    config = {"marketplaces": {"local": {"source_type": "git"}, "other": {}}}
    assert marketplace_is_user_configured(config, "local") is True
    assert marketplace_is_user_configured_git(config, "local") is True
    assert marketplace_is_user_configured_git(config, "other") is False


def test_hint_lines_and_header_text():
    assert plugins_header("subtitle", "3 plugins") == ("Plugins", "subtitle", "3 plugins")
    assert "ctrl + u upgrade" in plugins_popup_hint_line(True, True)
    assert "ctrl + r remove" in plugins_popup_hint_line(True, False)
    assert "space enable/disable" in plugins_popup_hint_line(False, False)
