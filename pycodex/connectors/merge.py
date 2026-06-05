"""Connector merge helpers aligned with ``codex-rs/connectors/src/merge.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pycodex.tools.tool_discovery import AppInfo

from .metadata import (
    coerce_app_info,
    connector_install_url,
    replace_app_info,
    sort_connectors_by_accessibility_and_name,
)

JsonValue = Any


def plugin_connector_to_app_info(connector_id: str) -> AppInfo:
    name = str(connector_id)
    return AppInfo(
        id=name,
        name=name,
        description=None,
        install_url=connector_install_url(name, name),
        is_accessible=False,
        is_enabled=True,
    )


def merge_connectors(
    connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    accessible_connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
) -> list[AppInfo]:
    merged: dict[str, AppInfo] = {
        connector.id: replace_app_info(connector, is_accessible=False)
        for connector in (coerce_app_info(connector) for connector in connectors)
    }
    for raw_connector in accessible_connectors:
        connector = replace_app_info(coerce_app_info(raw_connector), is_accessible=True)
        existing = merged.get(connector.id)
        if existing is None:
            merged[connector.id] = connector
            continue
        updates: dict[str, JsonValue] = {"is_accessible": True}
        if existing.name == existing.id and connector.name != connector.id:
            updates["name"] = connector.name
        if existing.description is None and connector.description is not None:
            updates["description"] = connector.description
        if existing.logo_url is None and connector.logo_url is not None:
            updates["logo_url"] = connector.logo_url
        if existing.logo_url_dark is None and connector.logo_url_dark is not None:
            updates["logo_url_dark"] = connector.logo_url_dark
        if existing.distribution_channel is None and connector.distribution_channel is not None:
            updates["distribution_channel"] = connector.distribution_channel
        plugin_names = tuple(
            sorted(set(existing.plugin_display_names).union(connector.plugin_display_names))
        )
        updates["plugin_display_names"] = plugin_names
        merged[connector.id] = replace_app_info(existing, **updates)

    result = []
    for connector in merged.values():
        install_url = connector.install_url or connector_install_url(connector.name, connector.id)
        result.append(
            replace_app_info(
                connector,
                install_url=install_url,
                plugin_display_names=tuple(sorted(set(connector.plugin_display_names))),
            )
        )
    sort_connectors_by_accessibility_and_name(result)
    return result


def merge_plugin_connectors(
    connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
    plugin_app_ids: Iterable[str],
) -> list[AppInfo]:
    merged = [coerce_app_info(connector) for connector in connectors]
    connector_ids = {connector.id for connector in merged}
    for connector_id in plugin_app_ids:
        connector_id = str(connector_id)
        if connector_id not in connector_ids:
            connector_ids.add(connector_id)
            merged.append(plugin_connector_to_app_info(connector_id))
    sort_connectors_by_accessibility_and_name(merged)
    return merged


def merge_plugin_connectors_with_accessible(
    plugin_app_ids: Iterable[str],
    accessible_connectors: Iterable[AppInfo | Mapping[str, JsonValue]],
) -> list[AppInfo]:
    accessible = [coerce_app_info(connector) for connector in accessible_connectors]
    accessible_ids = {connector.id for connector in accessible}
    plugin_connectors = [
        plugin_connector_to_app_info(str(connector_id))
        for connector_id in plugin_app_ids
        if str(connector_id) in accessible_ids
    ]
    return merge_connectors(plugin_connectors, accessible)


__all__ = [
    "merge_connectors",
    "merge_plugin_connectors",
    "merge_plugin_connectors_with_accessible",
    "plugin_connector_to_app_info",
]
