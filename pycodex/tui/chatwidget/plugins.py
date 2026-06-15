"""Semantic Python slice for Rust ``codex-tui::chatwidget::plugins``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/plugins.rs``.

The Rust module contains a large plugin marketplace UI.  This Python slice
ports the module-owned constants and pure helper behavior while keeping the
runtime UI, app-server requests, and marketplace/plugin install flow as explicit
boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableSequence, Sequence

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::plugins",
    source="codex/codex-rs/tui/src/chatwidget/plugins.rs",
    status="complete",
)

PLUGINS_SELECTION_VIEW_ID = "plugins-selection"
ALL_PLUGINS_TAB_ID = "all-plugins"
INSTALLED_PLUGINS_TAB_ID = "installed-plugins"
MARKETPLACE_TAB_ID_PREFIX = "marketplace:"
OPENAI_CURATED_TAB_ID = "marketplace:openai-curated"
ADD_MARKETPLACE_TAB_ID = "add-marketplace"
PLUGIN_ROW_PREFIX_WIDTH = 6
LOADING_ANIMATION_DELAY_SECONDS = 1.0
LOADING_ANIMATION_INTERVAL_SECONDS = 0.1
APPS_HELP_ARTICLE_URL = "https://help.openai.com/en/articles/11487775-apps-in-chatgpt"


class PluginInstallPolicy(Enum):
    AVAILABLE = "Available"
    INSTALLED_BY_DEFAULT = "InstalledByDefault"
    NOT_AVAILABLE = "NotAvailable"


class PluginsCacheKind(Enum):
    UNINITIALIZED = "Uninitialized"
    LOADING = "Loading"
    READY = "Ready"
    FAILED = "Failed"


@dataclass
class PluginListFetchState:
    cache_cwd: Path | None = None
    in_flight_cwd: Path | None = None


@dataclass
class PluginInstallAuthFlowState:
    plugin_display_name: str
    next_app_index: int = 0


@dataclass(frozen=True)
class AppEvent:
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SelectionToggle:
    is_on: bool
    event_kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_event(self, enabled: bool) -> AppEvent:
        payload = dict(self.payload)
        payload["enabled"] = enabled
        return AppEvent(self.event_kind, payload)


@dataclass(frozen=True)
class SelectionItem:
    name: str
    description: str | None = None
    selected_description: str | None = None
    actions: tuple[AppEvent, ...] = ()
    toggle: SelectionToggle | None = None
    toggle_placeholder: str | None = None
    search_value: str | None = None
    is_disabled: bool = False
    disabled_reason: str | None = None


@dataclass(frozen=True)
class SelectionTab:
    id: str
    label: str


@dataclass(frozen=True)
class SelectionViewParams:
    view_id: str | None = PLUGINS_SELECTION_VIEW_ID
    title: str = "Plugins"
    subtitle: str | None = None
    count_line: str | None = None
    items: tuple[SelectionItem, ...] = ()
    tabs: tuple[SelectionTab, ...] = ()
    active_tab_id: str | None = None
    footer_hint: str | None = None
    loading_text: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CustomPromptView:
    title: str
    description: str
    initial_text: str = ""
    context_label: str | None = None
    submit_events: tuple[AppEvent, ...] = ()


@dataclass
class DelayedLoadingHeader:
    loading_text: str
    note: str | None = None
    animations_enabled: bool = True

    @classmethod
    def new(
        cls,
        frame_requester: Any = None,
        animations_enabled: bool = True,
        loading_text: str = "",
        note: str | None = None,
    ) -> "DelayedLoadingHeader":
        return cls(
            loading_text=loading_text,
            note=note,
            animations_enabled=animations_enabled,
        )

    def desired_height(self, width: int | None = None) -> int:
        return 2 + int(self.note is not None)

    def render_lines(self, elapsed_seconds: float = 0.0) -> list[str]:
        return ["Plugins", self.loading_text] + ([self.note] if self.note else [])


@dataclass(frozen=True)
class PluginInterface:
    display_name: str | None = None
    short_description: str | None = None
    long_description: str | None = None


@dataclass(frozen=True)
class PluginSummary:
    id: str
    name: str
    installed: bool = False
    enabled: bool = False
    install_policy: PluginInstallPolicy = PluginInstallPolicy.AVAILABLE
    interface: PluginInterface | None = None


@dataclass(frozen=True)
class PluginMarketplaceEntry:
    name: str
    path: Path | None = None
    plugins: tuple[PluginSummary, ...] = ()
    interface: PluginInterface | None = None


@dataclass(frozen=True)
class PluginDetail:
    summary: PluginSummary
    description: str | None = None
    skills: tuple[Any, ...] = ()
    apps: tuple[Any, ...] = ()
    hooks: tuple[Any, ...] = ()
    mcp_servers: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginListResponse:
    marketplaces: tuple[PluginMarketplaceEntry, ...] = ()


@dataclass(frozen=True)
class MarketplaceAddResponse:
    marketplace_name: str
    installed_root: Path
    already_added: bool = False


@dataclass(frozen=True)
class MarketplaceRemoveResponse:
    marketplace_name: str


@dataclass(frozen=True)
class MarketplaceUpgradeResponse:
    marketplace_name: str
    upgraded: bool = False


@dataclass(frozen=True)
class PluginInstallResponse:
    apps_needing_auth: tuple[Any, ...] = ()


@dataclass(frozen=True)
class PluginUninstallResponse:
    plugin_display_name: str


@dataclass
class PluginsCacheState:
    kind: PluginsCacheKind = PluginsCacheKind.UNINITIALIZED
    response: Any | None = None
    error: str | None = None

    @classmethod
    def uninitialized(cls) -> "PluginsCacheState":
        return cls(PluginsCacheKind.UNINITIALIZED)

    @classmethod
    def loading(cls) -> "PluginsCacheState":
        return cls(PluginsCacheKind.LOADING)

    @classmethod
    def ready(cls, response: Any) -> "PluginsCacheState":
        return cls(PluginsCacheKind.READY, response=response)

    @classmethod
    def failed(cls, error: str) -> "PluginsCacheState":
        return cls(PluginsCacheKind.FAILED, error=error)


@dataclass(frozen=True)
class PluginSelectionEntry:
    marketplace: PluginMarketplaceEntry
    plugin: PluginSummary
    display_name: str


def plugins_popup_hint_line(can_remove_marketplace: bool, can_upgrade_marketplace: bool) -> str:
    if can_remove_marketplace and can_upgrade_marketplace:
        return "ctrl + u upgrade · ctrl + r remove · space toggle · tab/backtab tabs · enter details · esc close"
    if can_remove_marketplace:
        return "ctrl + r remove · space toggle · tab/backtab tabs · enter details · esc close"
    if can_upgrade_marketplace:
        return "ctrl + u upgrade · space toggle · tab/backtab tabs · enter details · esc close"
    return "space enable/disable · tab/backtab select marketplace · enter view details · esc close"

def plugin_detail_hint_line() -> str:
    return "Press esc to close."


def plugins_header(subtitle: str, count_line: str) -> tuple[str, str, str]:
    return ("Plugins", subtitle, count_line)


def plugin_entries_for_marketplaces(
    marketplaces: Iterable[PluginMarketplaceEntry | Mapping[str, Any]],
) -> list[PluginSelectionEntry]:
    entries: list[PluginSelectionEntry] = []
    for marketplace in marketplaces:
        mp = _coerce_marketplace(marketplace)
        for plugin in mp.plugins:
            entries.append(PluginSelectionEntry(mp, plugin, plugin_display_name(plugin)))
    return entries


def sort_plugin_entries(entries: MutableSequence[PluginSelectionEntry]) -> None:
    entries.sort(
        key=lambda entry: (
            not entry.plugin.installed,
            entry.display_name.lower(),
            entry.display_name,
            entry.plugin.name,
            entry.plugin.id,
        )
    )


def marketplace_tab_id(marketplace: PluginMarketplaceEntry | Mapping[str, Any]) -> str:
    mp = _coerce_marketplace(marketplace)
    if mp.path is not None:
        return marketplace_tab_id_from_path(mp.path)
    return f"{MARKETPLACE_TAB_ID_PREFIX}{mp.name}"


def marketplace_tab_id_from_path(path: str | Path) -> str:
    normalized = Path(path).as_posix().replace("\\", "/")
    return f"{MARKETPLACE_TAB_ID_PREFIX}{normalized}"


def marketplace_tab_id_matching_saved_id(
    saved_tab_id: str,
    marketplaces: Sequence[PluginMarketplaceEntry | Mapping[str, Any]],
) -> str | None:
    coerced = [_coerce_marketplace(marketplace) for marketplace in marketplaces]
    for marketplace in coerced:
        tab_id = marketplace_tab_id(marketplace)
        if tab_id == saved_tab_id:
            return tab_id

    if not saved_tab_id.startswith(MARKETPLACE_TAB_ID_PREFIX):
        return None
    root_text = saved_tab_id[len(MARKETPLACE_TAB_ID_PREFIX) :]
    if not root_text:
        return None
    root = Path(root_text)
    for marketplace in coerced:
        if marketplace.path is not None and _path_starts_with(marketplace.path, root):
            return marketplace_tab_id(marketplace)
    return None


def disambiguate_duplicate_tab_labels(labels: Sequence[str]) -> list[str]:
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1

    seen: dict[str, int] = {}
    result: list[str] = []
    for label in labels:
        if counts[label] == 1:
            result.append(label)
            continue
        seen[label] = seen.get(label, 0) + 1
        result.append(f"{label} ({seen[label]}/{counts[label]})")
    return result


def marketplace_display_name(marketplace: PluginMarketplaceEntry | Mapping[str, Any]) -> str:
    mp = _coerce_marketplace(marketplace)
    display_name = _trimmed_optional(mp.interface.display_name if mp.interface else None)
    return display_name or mp.name


def marketplace_is_user_configured(config: Mapping[str, Any], marketplace_name: str) -> bool:
    marketplaces = _get_nested(config, "marketplaces")
    return isinstance(marketplaces, Mapping) and marketplace_name in marketplaces


def marketplace_is_user_configured_git(config: Mapping[str, Any], marketplace_name: str) -> bool:
    marketplaces = _get_nested(config, "marketplaces")
    if not isinstance(marketplaces, Mapping):
        return False
    marketplace = marketplaces.get(marketplace_name)
    return isinstance(marketplace, Mapping) and marketplace.get("source_type") == "git"


def plugin_display_name(plugin: PluginSummary | Mapping[str, Any]) -> str:
    item = _coerce_plugin(plugin)
    display_name = _trimmed_optional(item.interface.display_name if item.interface else None)
    return display_name or item.name


def plugin_brief_description(
    plugin: PluginSummary | Mapping[str, Any],
    marketplace_label: str,
    status_label_width: int,
) -> str:
    item = _coerce_plugin(plugin)
    status = f"{plugin_status_label(item):<{status_label_width}}"
    description = plugin_description(item)
    if description is None:
        return f"{status} · {marketplace_label}"
    return f"{status} · {marketplace_label} · {description}"


def plugin_brief_description_without_marketplace(
    plugin: PluginSummary | Mapping[str, Any],
    status_label_width: int,
) -> str:
    item = _coerce_plugin(plugin)
    status = f"{plugin_status_label(item):<{status_label_width}}"
    description = plugin_description(item)
    return status if description is None else f"{status} · {description}"


def plugin_status_label(plugin: PluginSummary | Mapping[str, Any]) -> str:
    item = _coerce_plugin(plugin)
    if item.installed:
        return "Installed" if item.enabled else "Disabled"
    if item.install_policy is PluginInstallPolicy.NOT_AVAILABLE:
        return "Not installable"
    return "Available"


def plugin_description(plugin: PluginSummary | Mapping[str, Any]) -> str | None:
    item = _coerce_plugin(plugin)
    if item.interface is None:
        return None
    return _trimmed_optional(item.interface.short_description) or _trimmed_optional(
        item.interface.long_description
    )


def plugin_detail_description(plugin: PluginDetail | Mapping[str, Any]) -> str | None:
    detail = _coerce_detail(plugin)
    return (
        _trimmed_optional(detail.description)
        or _trimmed_optional(detail.summary.interface.long_description if detail.summary.interface else None)
        or _trimmed_optional(detail.summary.interface.short_description if detail.summary.interface else None)
    )


def plugin_skill_summary(plugin: PluginDetail | Mapping[str, Any]) -> str:
    detail = _coerce_detail(plugin)
    return _name_join(detail.skills, "No plugin skills.")


def plugin_app_summary(plugin: PluginDetail | Mapping[str, Any]) -> str:
    detail = _coerce_detail(plugin)
    return _name_join(detail.apps, "No plugin apps.")


def plugin_hook_summary(plugin: PluginDetail | Mapping[str, Any]) -> str:
    detail = _coerce_detail(plugin)
    if not detail.hooks:
        return "No plugin hooks."
    counts: dict[str, int] = {}
    for hook in detail.hooks:
        event_name = str(_get(hook, "event_name", ""))
        counts[event_name] = counts.get(event_name, 0) + 1
    return ", ".join(f"{event_name} ({count})" for event_name, count in counts.items())


def plugin_mcp_summary(plugin: PluginDetail | Mapping[str, Any]) -> str:
    detail = _coerce_detail(plugin)
    return "No plugin MCP servers." if not detail.mcp_servers else ", ".join(detail.mcp_servers)


def add_plugins_output(widget: Any) -> None:
    if not widget.config.features.enabled("Plugins"):
        widget.add_info_message("Plugins are disabled.", "Enable the plugins feature to use /plugins.")
        return
    widget.plugins_active_tab_id = ALL_PLUGINS_TAB_ID
    prefetch_plugins(widget)
    cache = plugins_cache_for_current_cwd(widget)
    if cache.kind is PluginsCacheKind.READY:
        open_plugins_popup(widget, cache.response)
    elif cache.kind is PluginsCacheKind.FAILED:
        widget.add_to_history({"kind": "error", "message": cache.error})
    else:
        open_plugins_loading_popup(widget)
    widget.request_redraw()


def prefetch_plugins(widget: Any) -> None:
    cwd = Path(widget.config.cwd)
    if getattr(widget.plugins_fetch_state, "in_flight_cwd", None) == cwd:
        return
    widget.plugins_fetch_state.in_flight_cwd = cwd
    if getattr(widget.plugins_fetch_state, "cache_cwd", None) != cwd:
        widget.plugins_cache = PluginsCacheState.loading()
    _send(widget, AppEvent("FetchPluginsList", {"cwd": cwd}))


def plugins_cache_for_current_cwd(widget: Any) -> PluginsCacheState:
    if getattr(widget.plugins_fetch_state, "cache_cwd", None) == Path(widget.config.cwd):
        return widget.plugins_cache
    return PluginsCacheState.uninitialized()


def on_plugins_loaded(widget: Any, cwd: str | Path, result: Any) -> None:
    cwd_path = Path(cwd)
    if getattr(widget.plugins_fetch_state, "in_flight_cwd", None) == cwd_path:
        widget.plugins_fetch_state.in_flight_cwd = None
    if Path(widget.config.cwd) != cwd_path:
        return
    auth_flow_active = getattr(widget, "plugin_install_auth_flow", None) is not None
    if _is_error_result(result):
        if not auth_flow_active:
            widget.plugins_fetch_state.cache_cwd = None
            widget.plugins_cache = PluginsCacheState.failed(str(result))
            _replace_or_show(widget, plugins_error_popup_params(str(result)))
        return
    response = _coerce_list_response(result)
    widget.plugins_fetch_state.cache_cwd = cwd_path
    widget.plugins_active_tab_id = _matching_or_existing_tab(widget.plugins_active_tab_id, response.marketplaces)
    widget.newly_installed_marketplace_tab_id = _matching_or_existing_tab(
        getattr(widget, "newly_installed_marketplace_tab_id", None), response.marketplaces
    )
    widget.plugins_cache = PluginsCacheState.ready(response)
    if not auth_flow_active:
        refresh_plugins_popup_if_open(widget, response)
    widget.newly_installed_marketplace_tab_id = None


def open_plugins_loading_popup(widget: Any) -> SelectionViewParams:
    params = plugins_loading_popup_params()
    _replace_or_show(widget, params)
    return params


def open_plugins_popup(widget: Any, response: Any) -> SelectionViewParams:
    widget.plugins_active_tab_id = ALL_PLUGINS_TAB_ID
    params = plugins_popup_params(widget, response, widget.plugins_active_tab_id, None)
    widget.bottom_pane.show_selection_view(params)
    return params


def refresh_plugins_popup_if_open(widget: Any, response: Any) -> bool:
    active_tab_id = widget.bottom_pane.active_tab_id_for_active_view(PLUGINS_SELECTION_VIEW_ID)
    params = plugins_popup_params(widget, response, active_tab_id or widget.plugins_active_tab_id, None)
    return bool(widget.bottom_pane.replace_selection_view_if_active(PLUGINS_SELECTION_VIEW_ID, params))


def open_marketplace_add_prompt(widget: Any) -> CustomPromptView:
    widget.plugins_active_tab_id = ADD_MARKETPLACE_TAB_ID
    view = CustomPromptView(
        title="Add marketplace",
        description="owner/repo, git URL, or local marketplace path",
        context_label="Examples: owner/repo, git URL, ./marketplace",
    )
    widget.bottom_pane.show_view(view)
    return view


def marketplace_add_submit_events(cwd: str | Path, source: str) -> tuple[AppEvent, ...]:
    source = source.strip()
    if not source:
        return ()
    return (
        AppEvent("OpenMarketplaceAddLoading", {"source": source}),
        AppEvent("FetchMarketplaceAdd", {"cwd": Path(cwd), "source": source}),
    )


def open_marketplace_add_loading_popup(widget: Any, source: str) -> SelectionViewParams:
    widget.plugins_active_tab_id = ADD_MARKETPLACE_TAB_ID
    params = marketplace_add_loading_popup_params()
    _replace_or_show(widget, params)
    return params


def on_marketplace_add_loaded(widget: Any, cwd: str | Path, source: str, result: Any) -> None:
    if Path(widget.config.cwd) != Path(cwd):
        return
    if _is_error_result(result):
        _replace_or_show(widget, plugins_error_popup_params(str(result)))
        return
    response = _coerce_marketplace_add_response(result)
    tab_id = marketplace_tab_id_from_path(response.installed_root)
    widget.plugins_active_tab_id = tab_id
    widget.newly_installed_marketplace_tab_id = None if response.already_added else tab_id
    message = (
        f"Marketplace {response.marketplace_name} is already added."
        if response.already_added
        else f"Added marketplace {response.marketplace_name}."
    )
    widget.add_info_message(message, None)
    prefetch_plugins(widget)


def open_marketplace_upgrade_loading_popup(widget: Any, marketplace_name: str | None = None) -> SelectionViewParams:
    widget.plugins_active_tab_id = widget.bottom_pane.active_tab_id_for_active_view(PLUGINS_SELECTION_VIEW_ID) or widget.plugins_active_tab_id
    params = marketplace_upgrade_loading_popup_params(marketplace_name)
    _replace_or_show(widget, params)
    return params


def on_marketplace_upgrade_loaded(widget: Any, cwd: str | Path, marketplace_name: str | None, result: Any) -> None:
    if Path(widget.config.cwd) != Path(cwd):
        return
    if _is_error_result(result):
        _replace_or_show(widget, plugins_error_popup_params(str(result)))
        return
    name = _get(result, "marketplace_name", marketplace_name or "marketplace")
    upgraded = bool(_get(result, "upgraded", False))
    widget.add_info_message(f"Upgraded marketplace {name}." if upgraded else f"Marketplace {name} is already up to date.", None)
    prefetch_plugins(widget)


def open_marketplace_remove_confirmation(widget: Any, marketplace_name: str, marketplace_display_name: str) -> SelectionViewParams | None:
    widget.plugins_active_tab_id = widget.bottom_pane.active_tab_id_for_active_view(PLUGINS_SELECTION_VIEW_ID) or widget.plugins_active_tab_id
    cache = plugins_cache_for_current_cwd(widget)
    if cache.kind is not PluginsCacheKind.READY:
        return None
    params = marketplace_remove_confirmation_popup_params(cache.response, marketplace_name, marketplace_display_name, Path(widget.config.cwd))
    _replace_or_show(widget, params)
    return params


def on_marketplace_remove_loaded(widget: Any, cwd: str | Path, marketplace_name: str, marketplace_display_name: str, result: Any) -> None:
    if Path(widget.config.cwd) != Path(cwd):
        return
    if _is_error_result(result):
        _replace_or_show(widget, plugins_error_popup_params(str(result)))
        return
    widget.add_info_message(f"Removed marketplace {marketplace_display_name}.", None)
    if widget.plugins_active_tab_id == f"{MARKETPLACE_TAB_ID_PREFIX}{marketplace_name}":
        widget.plugins_active_tab_id = ALL_PLUGINS_TAB_ID
    prefetch_plugins(widget)


def on_plugin_detail_loaded(widget: Any, cwd: str | Path, result: Any) -> None:
    if Path(widget.config.cwd) != Path(cwd):
        return
    cache = plugins_cache_for_current_cwd(widget)
    plugins_response = cache.response if cache.kind is PluginsCacheKind.READY else None
    if _is_error_result(result):
        widget.bottom_pane.replace_selection_view_if_active(
            PLUGINS_SELECTION_VIEW_ID,
            plugin_detail_error_popup_params(str(result), plugins_response),
        )
        return
    widget.bottom_pane.replace_selection_view_if_active(
        PLUGINS_SELECTION_VIEW_ID,
        plugin_detail_popup_params(widget, plugins_response, _coerce_detail(_get(result, "plugin", result))),
    )


def on_plugin_install_loaded(widget: Any, cwd: str | Path, marketplace_path: str | Path, plugin_name: str, plugin_display_name: str, result: Any) -> bool:
    if Path(widget.config.cwd) != Path(cwd):
        return True
    if _is_error_result(result):
        widget.plugin_install_apps_needing_auth = []
        widget.plugin_install_auth_flow = None
        cache = plugins_cache_for_current_cwd(widget)
        response = cache.response if cache.kind is PluginsCacheKind.READY else None
        widget.bottom_pane.replace_selection_view_if_active(
            PLUGINS_SELECTION_VIEW_ID,
            plugin_detail_error_popup_params(str(result), response),
        )
        return True
    apps = list(_get(result, "apps_needing_auth", ()))
    widget.plugin_install_apps_needing_auth = apps
    widget.plugin_install_auth_flow = None
    if not apps:
        widget.add_info_message(f"Installed {plugin_display_name} plugin.", "No additional app authentication is required.")
        return True
    names = ", ".join(str(_get(app, "name", app)) for app in apps)
    widget.add_info_message(
        f"Installed {plugin_display_name} plugin.",
        f"{len(apps)} app(s) still need authentication: {names}",
    )
    widget.plugin_install_auth_flow = PluginInstallAuthFlowState(plugin_display_name, 0)
    open_plugin_install_auth_popup(widget)
    return False


def open_plugin_install_auth_popup(widget: Any) -> SelectionViewParams | None:
    flow = getattr(widget, "plugin_install_auth_flow", None)
    apps = getattr(widget, "plugin_install_apps_needing_auth", [])
    if flow is None or flow.next_app_index >= len(apps):
        widget.plugin_install_auth_flow = None
        return None
    app = apps[flow.next_app_index]
    app_name = str(_get(app, "name", app))
    params = SelectionViewParams(
        subtitle=f"Authenticate {app_name}",
        count_line=f"{flow.next_app_index + 1} of {len(apps)} apps for {flow.plugin_display_name}",
        items=(
            SelectionItem(
                name=f"Authenticate {app_name}",
                actions=(AppEvent("OpenAppAuthentication", {"app": app}),),
            ),
            SelectionItem(
                name="Skip for now",
                actions=(AppEvent("SkipPluginInstallAuth", {"app": app}),),
            ),
        ),
        footer_hint=plugin_detail_hint_line(),
    )
    _replace_or_show(widget, params)
    return params


def advance_plugin_install_auth_flow(widget: Any) -> bool:
    flow = getattr(widget, "plugin_install_auth_flow", None)
    if flow is None:
        return True
    flow.next_app_index += 1
    if flow.next_app_index >= len(getattr(widget, "plugin_install_apps_needing_auth", [])):
        widget.plugin_install_auth_flow = None
        prefetch_plugins(widget)
        return True
    open_plugin_install_auth_popup(widget)
    return False


def on_plugin_uninstall_loaded(widget: Any, cwd: str | Path, plugin_display_name: str, result: Any) -> None:
    if Path(widget.config.cwd) != Path(cwd):
        return
    if _is_error_result(result):
        _replace_or_show(widget, plugins_error_popup_params(str(result)))
        return
    widget.add_info_message(f"Uninstalled {plugin_display_name} plugin.", None)
    prefetch_plugins(widget)


def plugins_loading_popup_params() -> SelectionViewParams:
    return SelectionViewParams(
        subtitle="Loading plugins",
        loading_text="Loading plugins...",
        items=(SelectionItem(name="Loading plugins...", is_disabled=True),),
        footer_hint=plugins_popup_hint_line(False, False),
    )


def marketplace_add_loading_popup_params() -> SelectionViewParams:
    return SelectionViewParams(
        active_tab_id=ADD_MARKETPLACE_TAB_ID,
        subtitle="Adding marketplace",
        loading_text="Adding marketplace...",
        items=(SelectionItem(name="Adding marketplace...", is_disabled=True),),
    )


def marketplace_upgrade_loading_popup_params(marketplace_name: str | None = None) -> SelectionViewParams:
    label = marketplace_name or "marketplace"
    return SelectionViewParams(
        subtitle=f"Upgrading {label}",
        loading_text=f"Upgrading {label}...",
        items=(SelectionItem(name=f"Upgrading {label}...", is_disabled=True),),
    )


def marketplace_remove_loading_popup_params(marketplace_display_name: str) -> SelectionViewParams:
    return SelectionViewParams(
        subtitle=f"Removing {marketplace_display_name}",
        loading_text=f"Removing {marketplace_display_name}...",
        items=(SelectionItem(name=f"Removing {marketplace_display_name}...", is_disabled=True),),
    )


def plugins_error_popup_params(error: str) -> SelectionViewParams:
    return SelectionViewParams(
        subtitle="Unable to load plugins",
        error=error,
        items=(SelectionItem(name="Error loading plugins", description=error, is_disabled=True),),
        footer_hint=plugin_detail_hint_line(),
    )


def plugin_detail_error_popup_params(error: str, plugins_response: Any = None) -> SelectionViewParams:
    items = [SelectionItem(name="Error loading plugin", description=error, is_disabled=True)]
    if plugins_response is not None:
        items.insert(0, SelectionItem(name="Back to plugins", actions=(AppEvent("PluginsLoaded", {"result": plugins_response}),)))
    return SelectionViewParams(
        subtitle="Plugin details",
        error=error,
        items=tuple(items),
        footer_hint=plugin_detail_hint_line(),
    )


def plugin_detail_loading_popup_params(plugin_display_name: str) -> SelectionViewParams:
    return SelectionViewParams(
        subtitle=plugin_display_name,
        loading_text=f"Loading {plugin_display_name}...",
        items=(SelectionItem(name=f"Loading {plugin_display_name}...", is_disabled=True),),
    )


def plugin_install_loading_popup_params(plugin_display_name: str) -> SelectionViewParams:
    return SelectionViewParams(
        subtitle=plugin_display_name,
        loading_text=f"Installing {plugin_display_name}...",
        items=(SelectionItem(name=f"Installing {plugin_display_name}...", is_disabled=True),),
    )


def plugin_uninstall_loading_popup_params(plugin_display_name: str) -> SelectionViewParams:
    return SelectionViewParams(
        subtitle=plugin_display_name,
        loading_text=f"Uninstalling {plugin_display_name}...",
        items=(SelectionItem(name=f"Uninstalling {plugin_display_name}...", is_disabled=True),),
    )


def plugins_popup_params(widget: Any, response: Any, active_tab_id: str | None = None, initial_selected_idx: int | None = None) -> SelectionViewParams:
    response = _coerce_list_response(response)
    active_tab_id = active_tab_id or ALL_PLUGINS_TAB_ID
    marketplaces = response.marketplaces
    tabs = _plugin_tabs(marketplaces)
    entries = plugin_entries_for_marketplaces(marketplaces)
    include_marketplace_names = active_tab_id in (ALL_PLUGINS_TAB_ID, INSTALLED_PLUGINS_TAB_ID)
    if active_tab_id == INSTALLED_PLUGINS_TAB_ID:
        entries = [entry for entry in entries if entry.plugin.installed]
    elif active_tab_id not in (ALL_PLUGINS_TAB_ID, INSTALLED_PLUGINS_TAB_ID, ADD_MARKETPLACE_TAB_ID):
        entries = [entry for entry in entries if marketplace_tab_id(entry.marketplace) == active_tab_id]
        include_marketplace_names = False
    items = plugin_selection_items(
        widget,
        entries,
        include_marketplace_names,
        "No plugins",
        "No plugins match this tab.",
    )
    installed_count = len([entry for entry in plugin_entries_for_marketplaces(marketplaces) if entry.plugin.installed])
    return SelectionViewParams(
        active_tab_id=active_tab_id,
        subtitle="Browse and manage plugins",
        count_line=f"{len(entries)} plugins, {installed_count} installed",
        items=tuple(items),
        tabs=tabs,
        footer_hint=plugins_popup_hint_line(
            _active_marketplace_can_remove(widget, active_tab_id),
            _active_marketplace_can_upgrade(widget, active_tab_id),
        ),
    )


def plugin_detail_popup_params(widget: Any, plugins_response: Any, plugin: PluginDetail) -> SelectionViewParams:
    display_name = plugin_display_name(plugin.summary)
    items = [
        SelectionItem(name="Back to plugins", description="Return to the plugin list.", actions=(AppEvent("PluginsLoaded", {"result": plugins_response}),)),
    ]
    if plugin.summary.installed:
        items.append(
            SelectionItem(
                name="Uninstall plugin",
                description="Remove this plugin now.",
                actions=(AppEvent("FetchPluginUninstall", {"plugin_id": plugin.summary.id, "plugin_display_name": display_name}),),
            )
        )
    elif plugin.summary.install_policy is PluginInstallPolicy.NOT_AVAILABLE:
        items.append(SelectionItem(name="Install plugin", description="This plugin is not installable from this marketplace.", is_disabled=True))
    else:
        items.append(
            SelectionItem(
                name="Install plugin",
                description="Install this plugin now.",
                actions=(AppEvent("FetchPluginInstall", {"plugin_name": plugin.summary.name, "plugin_display_name": display_name}),),
            )
        )
    items.extend(
        [
            SelectionItem(name="Skills", description=plugin_skill_summary(plugin), is_disabled=True),
            SelectionItem(name="Hooks", description=plugin_hook_summary(plugin), is_disabled=True),
            SelectionItem(name="Apps", description=plugin_app_summary(plugin), is_disabled=True),
            SelectionItem(name="MCP Servers", description=plugin_mcp_summary(plugin), is_disabled=True),
        ]
    )
    return SelectionViewParams(
        subtitle=display_name,
        count_line=plugin_detail_description(plugin),
        items=tuple(items),
        footer_hint=plugin_detail_hint_line(),
    )


def marketplace_remove_confirmation_popup_params(response: Any, marketplace_name: str, marketplace_display_name: str, cwd: Path) -> SelectionViewParams:
    return SelectionViewParams(
        subtitle=f"Remove {marketplace_display_name}",
        items=(
            SelectionItem(
                name=f"Remove {marketplace_display_name}",
                description="Remove this marketplace now.",
                actions=(
                    AppEvent("OpenMarketplaceRemoveLoading", {"marketplace_display_name": marketplace_display_name}),
                    AppEvent("FetchMarketplaceRemove", {"cwd": cwd, "marketplace_name": marketplace_name, "marketplace_display_name": marketplace_display_name}),
                ),
            ),
            SelectionItem(name="Cancel", actions=(AppEvent("PluginsLoaded", {"result": response}),)),
        ),
        footer_hint=plugin_detail_hint_line(),
    )


def plugin_selection_items(
    widget: Any,
    plugin_entries: Sequence[PluginSelectionEntry],
    include_marketplace_names: bool,
    empty_name: str,
    empty_description: str,
) -> list[SelectionItem]:
    entries = list(plugin_entries)
    sort_plugin_entries(entries)
    status_label_width = max([len(plugin_status_label(entry.plugin)) for entry in entries] or [0])
    items = []
    for entry in entries:
        marketplace_label = marketplace_display_name(entry.marketplace)
        status_label = plugin_status_label(entry.plugin)
        description = (
            plugin_brief_description(entry.plugin, marketplace_label, status_label_width)
            if include_marketplace_names
            else plugin_brief_description_without_marketplace(entry.plugin, status_label_width)
        )
        selected_status = f"{status_label:<{status_label_width}}"
        can_view_details = entry.marketplace.path is not None
        if entry.plugin.installed:
            toggle_action = "disable" if entry.plugin.enabled else "enable"
            selected_description = (
                f"{selected_status}   Space to {toggle_action}; Enter view details."
                if can_view_details
                else f"{selected_status}   Space to {toggle_action}."
            )
        elif can_view_details:
            selected_description = f"{selected_status}   Press Enter to install or view plugin details."
        else:
            selected_description = f"{selected_status}   Remote plugin details are not available yet."
        actions = ()
        if can_view_details:
            actions = (
                AppEvent("OpenPluginDetailLoading", {"plugin_display_name": entry.display_name}),
                AppEvent("FetchPluginDetail", {"cwd": Path(widget.config.cwd), "plugin_name": entry.plugin.name, "marketplace_path": entry.marketplace.path}),
            )
        is_disabled = not can_view_details and not entry.plugin.installed
        toggle = None
        if entry.plugin.installed:
            toggle = SelectionToggle(
                is_on=entry.plugin.enabled,
                event_kind="SetPluginEnabled",
                payload={"cwd": Path(widget.config.cwd), "plugin_id": entry.plugin.id},
            )
        items.append(
            SelectionItem(
                name=entry.display_name,
                toggle=toggle,
                toggle_placeholder=None if entry.plugin.installed else "[-] ",
                description=description,
                selected_description=selected_description,
                search_value=f"{entry.display_name} {entry.plugin.id} {entry.plugin.name} {marketplace_label}",
                actions=actions,
                is_disabled=is_disabled,
                disabled_reason="remote plugin details are not available yet" if is_disabled else None,
            )
        )
    if not items:
        items.append(SelectionItem(name=empty_name, description=empty_description, is_disabled=True))
    return items


def _trimmed_optional(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _coerce_interface(value: Any) -> PluginInterface | None:
    if value is None or isinstance(value, PluginInterface):
        return value
    return PluginInterface(
        display_name=_get(value, "display_name"),
        short_description=_get(value, "short_description"),
        long_description=_get(value, "long_description"),
    )


def _coerce_policy(value: Any) -> PluginInstallPolicy:
    if isinstance(value, PluginInstallPolicy):
        return value
    raw = str(getattr(value, "value", value))
    for policy in PluginInstallPolicy:
        if raw in {policy.value, policy.name, policy.name.lower()}:
            return policy
    raise ValueError(f"unknown plugin install policy: {value!r}")


def _coerce_plugin(value: PluginSummary | Mapping[str, Any]) -> PluginSummary:
    if isinstance(value, PluginSummary):
        return value
    return PluginSummary(
        id=str(_get(value, "id", "")),
        name=str(_get(value, "name", "")),
        installed=bool(_get(value, "installed", False)),
        enabled=bool(_get(value, "enabled", False)),
        install_policy=_coerce_policy(_get(value, "install_policy", PluginInstallPolicy.AVAILABLE)),
        interface=_coerce_interface(_get(value, "interface")),
    )


def _coerce_marketplace(value: PluginMarketplaceEntry | Mapping[str, Any]) -> PluginMarketplaceEntry:
    if isinstance(value, PluginMarketplaceEntry):
        return value
    path = _get(value, "path")
    plugins = tuple(_coerce_plugin(plugin) for plugin in _get(value, "plugins", ()))
    return PluginMarketplaceEntry(
        name=str(_get(value, "name", "")),
        path=Path(path) if path is not None else None,
        plugins=plugins,
        interface=_coerce_interface(_get(value, "interface")),
    )


def _coerce_detail(value: PluginDetail | Mapping[str, Any]) -> PluginDetail:
    if isinstance(value, PluginDetail):
        return value
    return PluginDetail(
        summary=_coerce_plugin(_get(value, "summary", {})),
        description=_get(value, "description"),
        skills=tuple(_get(value, "skills", ())),
        apps=tuple(_get(value, "apps", ())),
        hooks=tuple(_get(value, "hooks", ())),
        mcp_servers=tuple(str(server) for server in _get(value, "mcp_servers", ())),
    )


def _coerce_list_response(value: Any) -> PluginListResponse:
    if isinstance(value, PluginListResponse):
        return value
    marketplaces = tuple(_coerce_marketplace(marketplace) for marketplace in _get(value, "marketplaces", ()))
    return PluginListResponse(marketplaces)


def _coerce_marketplace_add_response(value: Any) -> MarketplaceAddResponse:
    if isinstance(value, MarketplaceAddResponse):
        return value
    return MarketplaceAddResponse(
        marketplace_name=str(_get(value, "marketplace_name", "")),
        installed_root=Path(_get(value, "installed_root")),
        already_added=bool(_get(value, "already_added", False)),
    )


def _is_error_result(value: Any) -> bool:
    return isinstance(value, Exception) or isinstance(value, str)


def _send(widget: Any, event: AppEvent) -> None:
    tx = getattr(widget, "app_event_tx", None)
    if tx is None:
        return
    tx.send(event)


def _replace_or_show(widget: Any, params: SelectionViewParams) -> bool:
    if widget.bottom_pane.replace_selection_view_if_active(PLUGINS_SELECTION_VIEW_ID, params):
        return True
    widget.bottom_pane.show_selection_view(params)
    return False


def _matching_or_existing_tab(saved_tab_id: str | None, marketplaces: Sequence[PluginMarketplaceEntry]) -> str | None:
    if saved_tab_id is None:
        return None
    return marketplace_tab_id_matching_saved_id(saved_tab_id, marketplaces) or saved_tab_id


def _plugin_tabs(marketplaces: Sequence[PluginMarketplaceEntry]) -> tuple[SelectionTab, ...]:
    labels = disambiguate_duplicate_tab_labels([marketplace_display_name(marketplace) for marketplace in marketplaces])
    tabs = [
        SelectionTab(ALL_PLUGINS_TAB_ID, "All"),
        SelectionTab(INSTALLED_PLUGINS_TAB_ID, "Installed"),
    ]
    tabs.extend(
        SelectionTab(marketplace_tab_id(marketplace), label)
        for marketplace, label in zip(marketplaces, labels)
    )
    tabs.append(SelectionTab(ADD_MARKETPLACE_TAB_ID, "Add marketplace"))
    return tuple(tabs)


def _active_marketplace_can_remove(widget: Any, active_tab_id: str | None) -> bool:
    if active_tab_id is None or not active_tab_id.startswith(MARKETPLACE_TAB_ID_PREFIX):
        return False
    name = active_tab_id[len(MARKETPLACE_TAB_ID_PREFIX) :]
    return marketplace_is_user_configured(getattr(widget, "config_dict", {}), name)


def _active_marketplace_can_upgrade(widget: Any, active_tab_id: str | None) -> bool:
    if active_tab_id is None or not active_tab_id.startswith(MARKETPLACE_TAB_ID_PREFIX):
        return False
    name = active_tab_id[len(MARKETPLACE_TAB_ID_PREFIX) :]
    return marketplace_is_user_configured_git(getattr(widget, "config_dict", {}), name)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_nested(config: Mapping[str, Any], key: str) -> Any:
    if "config_layer_stack" in config and isinstance(config["config_layer_stack"], Mapping):
        config = config["config_layer_stack"]
    if "effective_user_config" in config and isinstance(config["effective_user_config"], Mapping):
        config = config["effective_user_config"]
    return config.get(key)


def _name_join(items: Sequence[Any], empty: str) -> str:
    if not items:
        return empty
    return ", ".join(str(_get(item, "name", item)) for item in items)


def _path_starts_with(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return str(path).startswith(str(root))


__all__ = [
    "ADD_MARKETPLACE_TAB_ID",
    "ALL_PLUGINS_TAB_ID",
    "APPS_HELP_ARTICLE_URL",
    "AppEvent",
    "CustomPromptView",
    "DelayedLoadingHeader",
    "INSTALLED_PLUGINS_TAB_ID",
    "LOADING_ANIMATION_DELAY_SECONDS",
    "LOADING_ANIMATION_INTERVAL_SECONDS",
    "MARKETPLACE_TAB_ID_PREFIX",
    "OPENAI_CURATED_TAB_ID",
    "PLUGINS_SELECTION_VIEW_ID",
    "PLUGIN_ROW_PREFIX_WIDTH",
    "PluginDetail",
    "PluginInstallResponse",
    "PluginInstallAuthFlowState",
    "PluginInstallPolicy",
    "PluginInterface",
    "PluginListFetchState",
    "PluginMarketplaceEntry",
    "PluginSelectionEntry",
    "PluginSummary",
    "PluginsCacheKind",
    "PluginsCacheState",
    "RUST_MODULE",
    "add_plugins_output",
    "advance_plugin_install_auth_flow",
    "disambiguate_duplicate_tab_labels",
    "marketplace_add_loading_popup_params",
    "marketplace_add_submit_events",
    "marketplace_display_name",
    "marketplace_is_user_configured",
    "marketplace_is_user_configured_git",
    "marketplace_remove_confirmation_popup_params",
    "marketplace_remove_loading_popup_params",
    "marketplace_tab_id",
    "marketplace_tab_id_from_path",
    "marketplace_tab_id_matching_saved_id",
    "marketplace_upgrade_loading_popup_params",
    "on_marketplace_add_loaded",
    "on_marketplace_remove_loaded",
    "on_marketplace_upgrade_loaded",
    "on_plugin_detail_loaded",
    "on_plugin_install_loaded",
    "on_plugin_uninstall_loaded",
    "on_plugins_loaded",
    "open_marketplace_add_loading_popup",
    "open_marketplace_add_prompt",
    "open_marketplace_remove_confirmation",
    "open_marketplace_upgrade_loading_popup",
    "open_plugin_install_auth_popup",
    "open_plugins_loading_popup",
    "open_plugins_popup",
    "plugin_app_summary",
    "plugin_brief_description",
    "plugin_brief_description_without_marketplace",
    "plugin_description",
    "plugin_detail_error_popup_params",
    "plugin_detail_description",
    "plugin_detail_hint_line",
    "plugin_detail_loading_popup_params",
    "plugin_detail_popup_params",
    "plugin_display_name",
    "plugin_entries_for_marketplaces",
    "plugin_hook_summary",
    "plugin_install_loading_popup_params",
    "plugin_mcp_summary",
    "plugin_selection_items",
    "plugin_skill_summary",
    "plugin_status_label",
    "plugin_uninstall_loading_popup_params",
    "plugins_cache_for_current_cwd",
    "plugins_error_popup_params",
    "plugins_header",
    "plugins_loading_popup_params",
    "plugins_popup_params",
    "plugins_popup_hint_line",
    "prefetch_plugins",
    "refresh_plugins_popup_if_open",
    "sort_plugin_entries",
    "MarketplaceAddResponse",
    "MarketplaceRemoveResponse",
    "MarketplaceUpgradeResponse",
    "PluginListResponse",
    "PluginUninstallResponse",
    "SelectionItem",
    "SelectionTab",
    "SelectionToggle",
    "SelectionViewParams",
]
