"""Plugin mention enrichment for Rust ``codex-tui::app::plugin_mentions``.

Upstream source: ``codex/codex-rs/tui/src/app/plugin_mentions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::plugin_mentions",
    source="codex/codex-rs/tui/src/app/plugin_mentions.rs",
    status="complete",
)


class PluginAvailability(str, Enum):
    Available = "available"
    DisabledByAdmin = "disabled_by_admin"


@dataclass(eq=True)
class PluginInterface:
    display_name: Optional[str] = None
    short_description: Optional[str] = None


@dataclass(eq=True)
class PluginSummary:
    id: str
    name: str
    installed: bool = True
    enabled: bool = True
    availability: Any = PluginAvailability.Available
    interface: Any = None


@dataclass(eq=True)
class PluginMarketplaceEntry:
    name: str
    plugins: List[Any] = field(default_factory=list)


@dataclass(eq=True)
class PluginListResponse:
    marketplaces: List[Any] = field(default_factory=list)
    marketplace_load_errors: List[Any] = field(default_factory=list)
    featured_plugin_ids: List[str] = field(default_factory=list)


@dataclass(eq=True)
class PluginCapabilitySummary:
    config_name: str
    display_name: str
    description: Optional[str]
    has_skills: bool = False
    mcp_server_names: List[str] = field(default_factory=list)
    app_connector_ids: List[str] = field(default_factory=list)


def _get_attr_or_key(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _availability_value(value: Any) -> str:
    if isinstance(value, PluginAvailability):
        return value.value
    if hasattr(value, "name") and str(value.name) == "DisabledByAdmin":
        return PluginAvailability.DisabledByAdmin.value
    text = str(value)
    if text == "DisabledByAdmin":
        return PluginAvailability.DisabledByAdmin.value
    return text


async def fetch_plugin_mentions(request_handle: Any, cwd: Any = None) -> List[PluginCapabilitySummary]:
    response = None
    if hasattr(request_handle, "request_plugin_list"):
        response = request_handle.request_plugin_list(cwd)
    elif hasattr(request_handle, "plugin_list"):
        response = request_handle.plugin_list(cwd)
    elif callable(request_handle):
        response = request_handle(cwd)
    else:
        response = request_handle
    if hasattr(response, "__await__"):
        response = await response
    return plugin_mentions_from_list_response(response)


def plugin_mentions_from_list_response(response: Any) -> List[PluginCapabilitySummary]:
    mentions = []
    for marketplace in _get_attr_or_key(response, "marketplaces", []) or []:
        marketplace_name = str(_get_attr_or_key(marketplace, "name", ""))
        for plugin in _get_attr_or_key(marketplace, "plugins", []) or []:
            mention = plugin_mention_from_summary(marketplace_name, plugin)
            if mention is not None:
                mentions.append(mention)
    return mentions


def plugin_is_eligible_for_mentions(plugin: Any) -> bool:
    return bool(_get_attr_or_key(plugin, "installed", False)) and bool(_get_attr_or_key(plugin, "enabled", False)) and _availability_value(
        _get_attr_or_key(plugin, "availability", PluginAvailability.Available)
    ) != PluginAvailability.DisabledByAdmin.value


def plugin_mention_from_summary(marketplace_name: str, plugin: Any) -> Optional[PluginCapabilitySummary]:
    if not plugin_is_eligible_for_mentions(plugin):
        return None
    return PluginCapabilitySummary(
        config_name=str(_get_attr_or_key(plugin, "id")),
        display_name=plugin_mention_display_name(plugin),
        description=plugin_mention_description(marketplace_name, plugin),
        has_skills=False,
        mcp_server_names=[],
        app_connector_ids=[],
    )


def plugin_mention_display_name(plugin: Any) -> str:
    interface = _get_attr_or_key(plugin, "interface")
    display_name = _get_attr_or_key(interface, "display_name") if interface is not None else None
    if display_name is not None:
        trimmed = str(display_name).strip()
        if trimmed:
            return trimmed
    return str(_get_attr_or_key(plugin, "name", ""))


def plugin_mention_description(marketplace_name: str, plugin: Any) -> Optional[str]:
    interface = _get_attr_or_key(plugin, "interface")
    description = _get_attr_or_key(interface, "short_description") if interface is not None else None
    if description is not None:
        trimmed = str(description).strip()
        if trimmed:
            return trimmed
    marketplace = marketplace_name.strip()
    return marketplace or None


__all__ = [
    "PluginAvailability",
    "PluginCapabilitySummary",
    "PluginInterface",
    "PluginListResponse",
    "PluginMarketplaceEntry",
    "PluginSummary",
    "RUST_MODULE",
    "fetch_plugin_mentions",
    "plugin_is_eligible_for_mentions",
    "plugin_mention_description",
    "plugin_mention_display_name",
    "plugin_mention_from_summary",
    "plugin_mentions_from_list_response",
]
