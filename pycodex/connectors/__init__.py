"""Connector helpers aligned with Rust ``codex-rs/connectors``."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from .accessible import AccessibleConnectorTool, collect_accessible_connectors
from .directory_cache import (
    ConnectorDirectoryCacheContext,
    ConnectorDirectoryCacheKey,
    load_cached_directory_connectors_from_disk,
    write_cached_directory_connectors_to_disk,
)
from .filter import filter_disallowed_connectors, filter_tool_suggest_discoverable_connectors
from .merge import (
    merge_connectors,
    merge_plugin_connectors,
    merge_plugin_connectors_with_accessible,
    plugin_connector_to_app_info,
)
from .metadata import (
    coerce_app_info,
    connector_install_url,
    connector_name_slug,
    normalize_connector_value,
    replace_app_info,
    sanitize_name,
    sort_connectors_by_accessibility_and_name,
)
from pycodex.app_server_protocol.apps import AppBranding, AppInfo, AppMetadata

JsonValue = Any

CONNECTORS_CACHE_TTL = 3600.0


@dataclass(frozen=True)
class DirectoryListResponse:
    apps: tuple["DirectoryApp", ...]
    next_token: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "DirectoryListResponse":
        return cls(
            tuple(DirectoryApp.from_mapping(app) for app in value.get("apps", ())),
            normalize_connector_value(value.get("next_token", value.get("nextToken"))),
        )


@dataclass(frozen=True)
class DirectoryApp:
    id: str
    name: str
    description: str | None = None
    app_metadata: AppMetadata | Mapping[str, JsonValue] | None = None
    branding: AppBranding | Mapping[str, JsonValue] | None = None
    labels: Mapping[str, str] | None = None
    logo_url: str | None = None
    logo_url_dark: str | None = None
    distribution_channel: str | None = None
    visibility: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", str(self.id))
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "description", None if self.description is None else str(self.description))
        if self.app_metadata is not None and not isinstance(self.app_metadata, AppMetadata):
            object.__setattr__(self, "app_metadata", AppMetadata.from_mapping(self.app_metadata))
        if self.branding is not None and not isinstance(self.branding, AppBranding):
            object.__setattr__(self, "branding", AppBranding.from_mapping(self.branding))
        if self.labels is not None:
            object.__setattr__(self, "labels", {str(key): str(value) for key, value in self.labels.items()})
        object.__setattr__(self, "logo_url", None if self.logo_url is None else str(self.logo_url))
        object.__setattr__(self, "logo_url_dark", None if self.logo_url_dark is None else str(self.logo_url_dark))
        object.__setattr__(
            self,
            "distribution_channel",
            None if self.distribution_channel is None else str(self.distribution_channel),
        )
        object.__setattr__(self, "visibility", None if self.visibility is None else str(self.visibility))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "DirectoryApp":
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            description=value.get("description"),
            app_metadata=value.get("app_metadata", value.get("appMetadata")),
            branding=value.get("branding"),
            labels=value.get("labels"),
            logo_url=value.get("logo_url", value.get("logoUrl")),
            logo_url_dark=value.get("logo_url_dark", value.get("logoUrlDark")),
            distribution_channel=value.get("distribution_channel", value.get("distributionChannel")),
            visibility=value.get("visibility"),
        )


@dataclass(frozen=True)
class _CachedConnectorDirectory:
    key: ConnectorDirectoryCacheKey
    expires_at: float
    connectors: tuple[AppInfo, ...]


_CONNECTOR_DIRECTORY_CACHE: _CachedConnectorDirectory | None = None


def cached_directory_connectors(cache_context: ConnectorDirectoryCacheContext) -> list[AppInfo] | None:
    cached_connectors = _cached_directory_connectors_in_memory(cache_context.cache_key)
    if cached_connectors is not None:
        return cached_connectors
    connectors = load_cached_directory_connectors_from_disk(cache_context)
    if connectors is None:
        return None
    _write_cached_directory_connectors_in_memory(cache_context.cache_key, connectors, 0.0)
    return connectors


async def list_all_connectors_with_options(
    cache_context: ConnectorDirectoryCacheContext,
    is_workspace_account: bool,
    force_refetch: bool,
    fetch_page: Callable[[str], Awaitable[DirectoryListResponse | Mapping[str, JsonValue]]],
) -> list[AppInfo]:
    if not force_refetch:
        cached_connectors = _unexpired_directory_connectors_in_memory(cache_context.cache_key)
        if cached_connectors is not None:
            return cached_connectors

    apps = await list_directory_connectors(fetch_page)
    if is_workspace_account:
        apps.extend(await list_workspace_connectors(fetch_page))

    connectors = [_directory_app_to_app_info(app) for app in _merge_directory_apps(apps)]
    normalized_connectors: list[AppInfo] = []
    for connector in connectors:
        install_url = connector.install_url or connector_install_url(connector.name, connector.id)
        normalized_connectors.append(
            replace_app_info(
                connector,
                name=_normalize_connector_name(connector.name, connector.id),
                description=normalize_connector_value(connector.description),
                install_url=install_url,
                is_accessible=False,
            )
        )
    normalized_connectors.sort(key=lambda connector: (connector.name, connector.id))
    _write_cached_directory_connectors(cache_context, normalized_connectors)
    return normalized_connectors


async def list_directory_connectors(
    fetch_page: Callable[[str], Awaitable[DirectoryListResponse | Mapping[str, JsonValue]]],
) -> list[DirectoryApp]:
    apps: list[DirectoryApp] = []
    next_token: str | None = None
    while True:
        if next_token is None:
            path = "/connectors/directory/list?external_logos=true"
        else:
            path = f"/connectors/directory/list?token={quote(next_token)}&external_logos=true"
        response = _coerce_directory_list_response(await fetch_page(path))
        apps.extend(app for app in response.apps if not _is_hidden_directory_app(app))
        next_token = normalize_connector_value(response.next_token)
        if next_token is None:
            return apps


async def list_workspace_connectors(
    fetch_page: Callable[[str], Awaitable[DirectoryListResponse | Mapping[str, JsonValue]]],
) -> list[DirectoryApp]:
    try:
        response = _coerce_directory_list_response(
            await fetch_page("/connectors/directory/list_workspace?external_logos=true")
        )
    except Exception:
        return []
    return [app for app in response.apps if not _is_hidden_directory_app(app)]


def _cached_directory_connectors_in_memory(cache_key: ConnectorDirectoryCacheKey) -> list[AppInfo] | None:
    if _CONNECTOR_DIRECTORY_CACHE is None or _CONNECTOR_DIRECTORY_CACHE.key != cache_key:
        return None
    return list(_CONNECTOR_DIRECTORY_CACHE.connectors)


def _unexpired_directory_connectors_in_memory(cache_key: ConnectorDirectoryCacheKey) -> list[AppInfo] | None:
    if _CONNECTOR_DIRECTORY_CACHE is None or _CONNECTOR_DIRECTORY_CACHE.key != cache_key:
        return None
    if time.monotonic() < _CONNECTOR_DIRECTORY_CACHE.expires_at:
        return list(_CONNECTOR_DIRECTORY_CACHE.connectors)
    return None


def _write_cached_directory_connectors(
    cache_context: ConnectorDirectoryCacheContext,
    connectors: list[AppInfo],
) -> None:
    _write_cached_directory_connectors_in_memory(cache_context.cache_key, connectors, CONNECTORS_CACHE_TTL)
    write_cached_directory_connectors_to_disk(cache_context, connectors)


def _write_cached_directory_connectors_in_memory(
    cache_key: ConnectorDirectoryCacheKey,
    connectors: Iterable[AppInfo],
    ttl: float,
) -> None:
    global _CONNECTOR_DIRECTORY_CACHE
    _CONNECTOR_DIRECTORY_CACHE = _CachedConnectorDirectory(
        key=cache_key,
        expires_at=time.monotonic() + ttl,
        connectors=tuple(connectors),
    )


def _clear_directory_memory_cache_for_tests() -> None:
    global _CONNECTOR_DIRECTORY_CACHE
    _CONNECTOR_DIRECTORY_CACHE = None


def _merge_directory_apps(apps: Iterable[DirectoryApp]) -> list[DirectoryApp]:
    merged: dict[str, DirectoryApp] = {}
    for app in apps:
        existing = merged.get(app.id)
        merged[app.id] = app if existing is None else _merge_directory_app(existing, app)
    return list(merged.values())


def _merge_directory_app(existing: DirectoryApp, incoming: DirectoryApp) -> DirectoryApp:
    branding = _merge_branding(existing.branding, incoming.branding)
    app_metadata = _merge_app_metadata(existing.app_metadata, incoming.app_metadata)
    return DirectoryApp(
        id=existing.id,
        name=incoming.name if existing.name.strip() == "" and incoming.name.strip() != "" else existing.name,
        description=(
            incoming.description
            if incoming.description is not None and incoming.description.strip() != ""
            else existing.description
        ),
        app_metadata=app_metadata,
        branding=branding,
        labels=existing.labels if existing.labels is not None else incoming.labels,
        logo_url=existing.logo_url if existing.logo_url is not None else incoming.logo_url,
        logo_url_dark=existing.logo_url_dark if existing.logo_url_dark is not None else incoming.logo_url_dark,
        distribution_channel=(
            existing.distribution_channel
            if existing.distribution_channel is not None
            else incoming.distribution_channel
        ),
        visibility=existing.visibility,
    )


def _merge_branding(
    existing: AppBranding | None,
    incoming: AppBranding | None,
) -> AppBranding | None:
    if incoming is None:
        return existing
    if existing is None:
        return incoming
    return AppBranding(
        category=existing.category if existing.category is not None else incoming.category,
        developer=existing.developer if existing.developer is not None else incoming.developer,
        website=existing.website if existing.website is not None else incoming.website,
        privacy_policy=(
            existing.privacy_policy if existing.privacy_policy is not None else incoming.privacy_policy
        ),
        terms_of_service=(
            existing.terms_of_service
            if existing.terms_of_service is not None
            else incoming.terms_of_service
        ),
        is_discoverable_app=existing.is_discoverable_app or incoming.is_discoverable_app,
    )


def _merge_app_metadata(
    existing: AppMetadata | None,
    incoming: AppMetadata | None,
) -> AppMetadata | None:
    if incoming is None:
        return existing
    if existing is None:
        return incoming
    data = existing.to_mapping()
    incoming_data = incoming.to_mapping()
    for key, value in incoming_data.items():
        if data.get(key) is None and value is not None:
            data[key] = value
    return AppMetadata.from_mapping(data)


def _is_hidden_directory_app(app: DirectoryApp) -> bool:
    return app.visibility == "HIDDEN"


def _directory_app_to_app_info(app: DirectoryApp) -> AppInfo:
    return AppInfo(
        id=app.id,
        name=app.name,
        description=app.description,
        logo_url=app.logo_url,
        logo_url_dark=app.logo_url_dark,
        distribution_channel=app.distribution_channel,
        branding=app.branding,
        app_metadata=app.app_metadata,
        labels=app.labels,
        install_url=None,
        is_accessible=False,
        is_enabled=True,
        plugin_display_names=(),
    )


def _normalize_connector_name(name: str, connector_id: str) -> str:
    trimmed = name.strip()
    return connector_id if trimmed == "" else trimmed


def _coerce_directory_list_response(
    value: DirectoryListResponse | Mapping[str, JsonValue],
) -> DirectoryListResponse:
    if isinstance(value, DirectoryListResponse):
        return value
    return DirectoryListResponse.from_mapping(value)

__all__ = [
    "AccessibleConnectorTool",
    "CONNECTORS_CACHE_TTL",
    "ConnectorDirectoryCacheContext",
    "ConnectorDirectoryCacheKey",
    "DirectoryApp",
    "DirectoryListResponse",
    "coerce_app_info",
    "collect_accessible_connectors",
    "connector_install_url",
    "connector_name_slug",
    "cached_directory_connectors",
    "filter_disallowed_connectors",
    "filter_tool_suggest_discoverable_connectors",
    "list_all_connectors_with_options",
    "list_directory_connectors",
    "list_workspace_connectors",
    "merge_connectors",
    "merge_plugin_connectors",
    "merge_plugin_connectors_with_accessible",
    "normalize_connector_value",
    "plugin_connector_to_app_info",
    "replace_app_info",
    "sanitize_name",
    "sort_connectors_by_accessibility_and_name",
]
