"""Connector metadata helpers aligned with ``codex-rs/connectors/src/metadata.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.tools.tool_discovery import AppInfo

JsonValue = Any


def connector_name_slug(name: str) -> str:
    normalized = "".join(
        character.lower() if character.isascii() and character.isalnum() else "-"
        for character in str(name)
    ).strip("-")
    return normalized or "app"


def connector_display_label(connector: AppInfo | Mapping[str, JsonValue] | Any) -> str:
    return coerce_app_info(connector).name


def connector_mention_slug(connector: AppInfo | Mapping[str, JsonValue] | Any) -> str:
    return connector_name_slug(connector_display_label(connector))


def connector_install_url(name: str, connector_id: str) -> str:
    return f"https://chatgpt.com/apps/{connector_name_slug(name)}/{connector_id}"


def sanitize_name(name: str) -> str:
    return connector_name_slug(name).replace("-", "_")


def normalize_connector_value(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = str(value).strip()
    return trimmed or None


def coerce_app_info(value: AppInfo | Mapping[str, JsonValue]) -> AppInfo:
    if isinstance(value, AppInfo):
        return value
    if isinstance(value, Mapping):
        return AppInfo.from_mapping(value)
    if hasattr(value, "to_mapping"):
        try:
            mapped = value.to_mapping()
            if isinstance(mapped, Mapping):
                return AppInfo.from_mapping(mapped)
        except Exception:
            pass
    fields: dict[str, JsonValue] = {}
    if hasattr(value, "__dict__"):
        fields.update(value.__dict__)
    for key in (
        "id",
        "name",
        "description",
        "labels",
        "is_accessible",
        "is_enabled",
        "plugin_display_names",
        "install_url",
        "logo_url",
        "logo_url_dark",
        "distribution_channel",
        "branding",
        "app_metadata",
    ):
        if key not in fields and hasattr(value, key):
            fields[key] = getattr(value, key)
    if "id" not in fields:
        connector_id = None
        for fallback in ("connector_id", "slug", "path"):
            if hasattr(value, fallback):
                connector_id = getattr(value, fallback)
                break
        if connector_id is None:
            connector_id = getattr(value, "__name__", None)
        if connector_id is not None:
            fields["id"] = connector_id
    if "name" not in fields:
        if "id" in fields:
            fields["name"] = fields["id"]
        elif hasattr(value, "__class__"):
            fields["name"] = value.__class__.__name__
    if "id" not in fields:
        raise TypeError("AppInfo mapping must be a mapping")
    if "name" not in fields:
        fields["name"] = fields["id"]
    return AppInfo.from_mapping(fields)


def replace_app_info(connector: AppInfo, **updates: JsonValue) -> AppInfo:
    data = connector.to_mapping()
    data.update(updates)
    return AppInfo.from_mapping(data)


def sort_connectors_by_accessibility_and_name(connectors: list[AppInfo]) -> None:
    connectors.sort(key=lambda connector: (not connector.is_accessible, connector.name, connector.id))


__all__ = [
    "coerce_app_info",
    "connector_display_label",
    "connector_install_url",
    "connector_mention_slug",
    "connector_name_slug",
    "normalize_connector_value",
    "replace_app_info",
    "sanitize_name",
    "sort_connectors_by_accessibility_and_name",
]
