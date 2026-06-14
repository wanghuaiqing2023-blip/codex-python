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
        return "ctrl + u upgrade · ctrl + r remove · space toggle · ←/→ tabs · enter details · esc close"
    if can_remove_marketplace:
        return "ctrl + r remove · space toggle · ←/→ tabs · enter details · esc close"
    if can_upgrade_marketplace:
        return "ctrl + u upgrade · space toggle · ←/→ tabs · enter details · esc close"
    return "space enable/disable · ←/→ select marketplace · enter view details · esc close"


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
    return f"{MARKETPLACE_TAB_ID_PREFIX}{Path(path)}"


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
    "DelayedLoadingHeader",
    "INSTALLED_PLUGINS_TAB_ID",
    "LOADING_ANIMATION_DELAY_SECONDS",
    "LOADING_ANIMATION_INTERVAL_SECONDS",
    "MARKETPLACE_TAB_ID_PREFIX",
    "OPENAI_CURATED_TAB_ID",
    "PLUGINS_SELECTION_VIEW_ID",
    "PLUGIN_ROW_PREFIX_WIDTH",
    "PluginDetail",
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
    "disambiguate_duplicate_tab_labels",
    "marketplace_display_name",
    "marketplace_is_user_configured",
    "marketplace_is_user_configured_git",
    "marketplace_tab_id",
    "marketplace_tab_id_from_path",
    "marketplace_tab_id_matching_saved_id",
    "plugin_app_summary",
    "plugin_brief_description",
    "plugin_brief_description_without_marketplace",
    "plugin_description",
    "plugin_detail_description",
    "plugin_detail_hint_line",
    "plugin_display_name",
    "plugin_entries_for_marketplaces",
    "plugin_hook_summary",
    "plugin_mcp_summary",
    "plugin_skill_summary",
    "plugin_status_label",
    "plugins_header",
    "plugins_popup_hint_line",
    "sort_plugin_entries",
]
