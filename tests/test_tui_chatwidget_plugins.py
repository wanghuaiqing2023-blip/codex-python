from pathlib import Path
from types import SimpleNamespace

from pycodex.tui.chatwidget.plugins import (
    AppEvent,
    ADD_MARKETPLACE_TAB_ID,
    ALL_PLUGINS_TAB_ID,
    PLUGINS_SELECTION_VIEW_ID,
    DelayedLoadingHeader,
    MarketplaceAddResponse,
    PluginInstallAuthFlowState,
    PluginInstallResponse,
    PluginListFetchState,
    PluginListResponse,
    PluginDetail,
    PluginInstallPolicy,
    PluginInterface,
    PluginMarketplaceEntry,
    PluginSummary,
    PluginsCacheState,
    add_plugins_output,
    advance_plugin_install_auth_flow,
    disambiguate_duplicate_tab_labels,
    marketplace_add_submit_events,
    on_marketplace_add_loaded,
    on_marketplace_upgrade_loaded,
    on_plugin_install_loaded,
    on_plugin_uninstall_loaded,
    on_plugins_loaded,
    open_marketplace_add_prompt,
    open_marketplace_remove_confirmation,
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
    plugin_detail_popup_params,
    plugin_display_name,
    plugin_entries_for_marketplaces,
    plugin_hook_summary,
    plugin_mcp_summary,
    plugin_skill_summary,
    plugin_status_label,
    plugins_cache_for_current_cwd,
    plugins_loading_popup_params,
    plugins_popup_params,
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


class Tx:
    def __init__(self):
        self.events = []

    def send(self, event):
        self.events.append(event)


class Pane:
    def __init__(self):
        self.selection = None
        self.view = None
        self.replaced = []
        self.active_tab = None
        self.replace_active = False

    def show_selection_view(self, params):
        self.selection = params

    def show_view(self, view):
        self.view = view

    def replace_selection_view_if_active(self, view_id, params):
        self.replaced.append((view_id, params))
        if self.replace_active:
            self.selection = params
            return True
        return False

    def active_tab_id_for_active_view(self, view_id):
        return self.active_tab


class Features:
    def __init__(self, enabled=True):
        self.value = enabled

    def enabled(self, feature):
        return self.value and feature == "Plugins"


class Widget:
    def __init__(self):
        self.config = SimpleNamespace(cwd=Path("/repo"), features=Features())
        self.config_dict = {"marketplaces": {"m": {"source_type": "git"}}}
        self.bottom_pane = Pane()
        self.app_event_tx = Tx()
        self.plugins_fetch_state = PluginListFetchState()
        self.plugins_cache = PluginsCacheState.uninitialized()
        self.plugins_active_tab_id = None
        self.newly_installed_marketplace_tab_id = None
        self.plugin_install_apps_needing_auth = []
        self.plugin_install_auth_flow = None
        self.info_messages = []
        self.history = []
        self.redraws = 0

    def add_info_message(self, message, hint=None):
        self.info_messages.append((message, hint))

    def add_to_history(self, item):
        self.history.append(item)

    def request_redraw(self):
        self.redraws += 1


def response_with_plugins():
    marketplace = PluginMarketplaceEntry(
        name="m",
        path=Path("/marketplaces/m"),
        plugins=(plugin("tool", installed=True, enabled=True), plugin("new-tool"),),
        interface=PluginInterface(display_name="Market"),
    )
    return PluginListResponse((marketplace,))


def test_add_plugins_output_prefetches_then_opens_loading_ready_or_error_states():
    widget = Widget()

    add_plugins_output(widget)

    assert widget.plugins_active_tab_id == ALL_PLUGINS_TAB_ID
    assert widget.plugins_cache.kind.name == "LOADING"
    assert widget.app_event_tx.events == [AppEvent("FetchPluginsList", {"cwd": Path("/repo")})]
    assert widget.bottom_pane.selection.loading_text == "Loading plugins..."
    assert widget.redraws == 1

    widget = Widget()
    response = response_with_plugins()
    widget.plugins_fetch_state.cache_cwd = Path("/repo")
    widget.plugins_cache = PluginsCacheState.ready(response)
    add_plugins_output(widget)
    assert widget.bottom_pane.selection.active_tab_id == ALL_PLUGINS_TAB_ID
    assert widget.bottom_pane.selection.items[0].name == "tool"

    widget = Widget()
    widget.config.features = Features(enabled=False)
    add_plugins_output(widget)
    assert widget.info_messages == [("Plugins are disabled.", "Enable the plugins feature to use /plugins.")]


def test_plugins_loaded_updates_cache_tab_matching_and_replaces_popup_or_error():
    widget = Widget()
    widget.plugins_fetch_state.in_flight_cwd = Path("/repo")
    widget.plugins_active_tab_id = "marketplace:/marketplaces"
    widget.bottom_pane.replace_active = True
    response = response_with_plugins()

    on_plugins_loaded(widget, Path("/repo"), response)

    assert widget.plugins_fetch_state.in_flight_cwd is None
    assert widget.plugins_fetch_state.cache_cwd == Path("/repo")
    assert widget.plugins_cache.response == response
    assert widget.plugins_active_tab_id == "marketplace:/marketplaces/m"
    assert widget.bottom_pane.selection.view_id == PLUGINS_SELECTION_VIEW_ID

    widget = Widget()
    widget.bottom_pane.replace_active = True
    on_plugins_loaded(widget, Path("/repo"), "network failed")
    assert widget.plugins_cache.error == "network failed"
    assert widget.bottom_pane.selection.error == "network failed"


def test_plugins_popup_params_detail_params_and_toggle_events_are_semantic_rust_actions():
    widget = Widget()
    response = response_with_plugins()

    params = plugins_popup_params(widget, response, ALL_PLUGINS_TAB_ID, None)

    assert [tab.id for tab in params.tabs][:2] == [ALL_PLUGINS_TAB_ID, "installed-plugins"]
    installed_item = params.items[0]
    assert installed_item.toggle.to_event(False) == AppEvent(
        "SetPluginEnabled", {"cwd": Path("/repo"), "plugin_id": "id-tool", "enabled": False}
    )
    assert installed_item.actions[0].kind == "OpenPluginDetailLoading"
    assert installed_item.actions[1].kind == "FetchPluginDetail"

    detail = PluginDetail(summary=plugin("tool", installed=True), skills=({"name": "s"},))
    detail_params = plugin_detail_popup_params(widget, response, detail)
    assert detail_params.items[0].name == "Back to plugins"
    assert detail_params.items[1].name == "Uninstall plugin"
    assert detail_params.items[2].description == "s"


def test_marketplace_add_upgrade_remove_and_prompt_flows_emit_events_and_refresh():
    widget = Widget()
    view = open_marketplace_add_prompt(widget)
    assert view.title == "Add marketplace"
    assert widget.plugins_active_tab_id == ADD_MARKETPLACE_TAB_ID
    assert marketplace_add_submit_events("/repo", " source ")[1] == AppEvent(
        "FetchMarketplaceAdd", {"cwd": Path("/repo"), "source": "source"}
    )

    on_marketplace_add_loaded(
        widget,
        "/repo",
        "source",
        MarketplaceAddResponse("m", Path("/marketplaces/m"), already_added=False),
    )
    assert widget.plugins_active_tab_id == "marketplace:/marketplaces/m"
    assert widget.newly_installed_marketplace_tab_id == "marketplace:/marketplaces/m"
    assert widget.info_messages[-1] == ("Added marketplace m.", None)

    on_marketplace_upgrade_loaded(widget, "/repo", "m", {"marketplace_name": "m", "upgraded": False})
    assert widget.info_messages[-1] == ("Marketplace m is already up to date.", None)

    widget.plugins_fetch_state.cache_cwd = Path("/repo")
    widget.plugins_cache = PluginsCacheState.ready(response_with_plugins())
    params = open_marketplace_remove_confirmation(widget, "m", "Market")
    assert params.items[0].actions[1].kind == "FetchMarketplaceRemove"


def test_plugin_install_auth_flow_and_uninstall_loaded_follow_rust_state_machine():
    widget = Widget()
    apps = [SimpleNamespace(name="Drive"), SimpleNamespace(name="Slack")]

    done = on_plugin_install_loaded(
        widget,
        "/repo",
        "/market",
        "tool",
        "Tool",
        PluginInstallResponse(tuple(apps)),
    )

    assert done is False
    assert widget.plugin_install_auth_flow == PluginInstallAuthFlowState("Tool", 0)
    assert widget.bottom_pane.selection.items[0].name == "Authenticate Drive"

    assert advance_plugin_install_auth_flow(widget) is False
    assert widget.plugin_install_auth_flow.next_app_index == 1
    assert widget.bottom_pane.selection.items[0].name == "Authenticate Slack"

    assert advance_plugin_install_auth_flow(widget) is True
    assert widget.plugin_install_auth_flow is None
    assert widget.app_event_tx.events[-1].kind == "FetchPluginsList"

    on_plugin_uninstall_loaded(widget, "/repo", "Tool", {"ok": True})
    assert widget.info_messages[-1] == ("Uninstalled Tool plugin.", None)
