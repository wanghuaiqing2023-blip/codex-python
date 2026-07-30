"""ChatGPT connector orchestration owned by ``connectors.rs``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pycodex.app_server_protocol.apps import AppInfo
from pycodex.connectors import (
    ConnectorDirectoryCacheContext,
    ConnectorDirectoryCacheKey,
    DirectoryListResponse,
    cached_directory_connectors,
    filter_disallowed_connectors,
    list_all_connectors_with_options as list_directory_connectors_with_options,
    merge_connectors,
    merge_plugin_connectors,
)
from pycodex.core.connectors import (
    accessible_connectors_from_mcp_tools,
    with_app_enabled_state as core_with_app_enabled_state,
)
from pycodex.core_plugins import PluginsManager
from pycodex.login.auth.default_client import originator
from pycodex.plugin import AppConnectorId

from .chatgpt_client import (
    _auth_manager_from_config,
    chatgpt_get_request_with_timeout,
)

DIRECTORY_CONNECTORS_TIMEOUT = 60.0


@dataclass(frozen=True)
class AccessibleConnectorsStatus:
    connectors: tuple[AppInfo, ...]
    codex_apps_ready: bool = True


async def list_connectors(config: Any) -> list[AppInfo]:
    if not await _apps_enabled(config):
        return []
    all_connectors, accessible_status = await _gather_connector_lists(config)
    return _with_app_enabled_state(
        merge_connectors_with_accessible(
            all_connectors,
            list(accessible_status.connectors),
            all_connectors_loaded=True,
        ),
        config,
    )


async def list_all_connectors(config: Any) -> list[AppInfo]:
    return await list_all_connectors_with_options(config, False)


async def list_cached_all_connectors(config: Any) -> list[AppInfo] | None:
    if not await _apps_enabled(config):
        return []
    try:
        auth = await _connector_auth(config)
    except Exception:
        return None
    connectors = cached_directory_connectors(
        _connector_directory_cache_context(config, auth)
    )
    if connectors is None:
        return None
    connectors = merge_plugin_connectors(
        connectors,
        await _plugin_apps_for_config(config),
    )
    return filter_disallowed_connectors(connectors, originator().value)


async def list_all_connectors_with_options(
    config: Any,
    force_refetch: bool,
) -> list[AppInfo]:
    if not await _apps_enabled(config):
        return []
    auth = await _connector_auth(config)
    connectors = await list_directory_connectors_with_options(
        _connector_directory_cache_context(config, auth),
        bool(auth.is_workspace_account()),
        bool(force_refetch),
        lambda path: _directory_page(config, path),
    )
    connectors = merge_plugin_connectors(
        connectors,
        await _plugin_apps_for_config(config),
    )
    return filter_disallowed_connectors(connectors, originator().value)


async def list_cached_accessible_connectors_from_mcp_tools(
    config: Any,
) -> list[AppInfo] | None:
    loader = getattr(config, "list_cached_accessible_connectors_from_mcp_tools", None)
    if callable(loader):
        return await _maybe_await(loader())
    cached = getattr(config, "cached_accessible_connectors", None)
    return None if cached is None else list(cached)


async def list_accessible_connectors_from_mcp_tools(
    config: Any,
) -> AccessibleConnectorsStatus:
    return await list_accessible_connectors_from_mcp_tools_with_environment_manager(
        config,
        False,
        None,
    )


async def list_accessible_connectors_from_mcp_tools_with_environment_manager(
    config: Any,
    force_refetch: bool,
    environment_manager: Any,
) -> AccessibleConnectorsStatus:
    loader = getattr(
        config,
        "list_accessible_connectors_from_mcp_tools_with_environment_manager",
        None,
    )
    if callable(loader):
        result = await _maybe_await(
            loader(bool(force_refetch), environment_manager)
        )
        if isinstance(result, AccessibleConnectorsStatus):
            return result
        connectors = getattr(result, "connectors", result)
        ready = getattr(result, "codex_apps_ready", True)
        return AccessibleConnectorsStatus(tuple(connectors or ()), bool(ready))

    tools = getattr(config, "mcp_tools", ())
    return AccessibleConnectorsStatus(
        tuple(accessible_connectors_from_mcp_tools(tools)),
        True,
    )


def connectors_for_plugin_apps(
    connectors: Iterable[AppInfo],
    plugin_apps: Iterable[AppConnectorId | str],
) -> list[AppInfo]:
    plugin_ids = [_connector_id(value) for value in plugin_apps]
    requested = set(plugin_ids)
    merged = merge_plugin_connectors(connectors, plugin_ids)
    return [
        connector
        for connector in filter_disallowed_connectors(merged, originator().value)
        if connector.id in requested
    ]


def merge_connectors_with_accessible(
    connectors: Iterable[AppInfo],
    accessible_connectors: Iterable[AppInfo],
    all_connectors_loaded: bool,
) -> list[AppInfo]:
    all_items = list(connectors)
    accessible_items = list(accessible_connectors)
    if all_connectors_loaded:
        connector_ids = {connector.id for connector in all_items}
        accessible_items = [
            connector
            for connector in accessible_items
            if connector.id in connector_ids
        ]
    return filter_disallowed_connectors(
        merge_connectors(all_items, accessible_items),
        originator().value,
    )


class ChatgptAppsConnectorLoader:
    async def cached_accessible(self, config: Any) -> tuple[AppInfo, ...] | None:
        value = await list_cached_accessible_connectors_from_mcp_tools(config)
        return None if value is None else tuple(value)

    async def cached_all(self, config: Any) -> tuple[AppInfo, ...] | None:
        value = await list_cached_all_connectors(config)
        return None if value is None else tuple(value)

    async def load_accessible(
        self,
        config: Any,
        force_refetch: bool,
        environment_manager: Any,
    ) -> AccessibleConnectorsStatus:
        return await list_accessible_connectors_from_mcp_tools_with_environment_manager(
            config,
            force_refetch,
            environment_manager,
        )

    async def load_all(
        self,
        config: Any,
        force_refetch: bool,
    ) -> tuple[AppInfo, ...]:
        return tuple(await list_all_connectors_with_options(config, force_refetch))


async def _apps_enabled(config: Any) -> bool:
    manager = await _auth_manager_from_config(config)
    auth = await manager.auth()
    features = getattr(config, "features", None)
    enabled = getattr(features, "apps_enabled_for_auth", None)
    if callable(enabled):
        return bool(
            enabled(auth is not None and bool(auth.uses_codex_backend()))
        )
    return False


async def _connector_auth(config: Any) -> Any:
    manager = await _auth_manager_from_config(config)
    auth = await manager.auth()
    if auth is None:
        raise RuntimeError("ChatGPT auth not available")
    if not auth.uses_codex_backend():
        raise RuntimeError("ChatGPT connectors require Codex backend auth")
    return auth


def _connector_directory_cache_context(
    config: Any,
    auth: Any,
) -> ConnectorDirectoryCacheContext:
    return ConnectorDirectoryCacheContext(
        getattr(config, "codex_home"),
        ConnectorDirectoryCacheKey(
            str(getattr(config, "chatgpt_base_url")),
            auth.get_account_id(),
            auth.get_chatgpt_user_id(),
            bool(auth.is_workspace_account()),
        ),
    )


async def _plugin_apps_for_config(config: Any) -> tuple[str, ...]:
    builder = getattr(config, "plugins_config_input", None)
    if not callable(builder):
        return ()
    outcome = await PluginsManager(getattr(config, "codex_home")).plugins_for_config(
        builder()
    )
    return tuple(_connector_id(value) for value in outcome.effective_apps())


async def _directory_page(config: Any, path: str) -> DirectoryListResponse:
    payload = await chatgpt_get_request_with_timeout(
        config,
        path,
        DIRECTORY_CONNECTORS_TIMEOUT,
    )
    return (
        payload
        if isinstance(payload, DirectoryListResponse)
        else DirectoryListResponse.from_mapping(payload)
    )


async def _gather_connector_lists(
    config: Any,
) -> tuple[list[AppInfo], AccessibleConnectorsStatus]:
    import asyncio

    all_result, accessible_result = await asyncio.gather(
        list_all_connectors(config),
        list_accessible_connectors_from_mcp_tools(config),
    )
    return all_result, accessible_result


def _with_app_enabled_state(
    connectors: Iterable[AppInfo],
    config: Any,
) -> list[AppInfo]:
    return core_with_app_enabled_state(
        connectors,
        getattr(config, "apps", getattr(config, "apps_config", {})),
        getattr(
            config,
            "requirements_apps_config",
            getattr(config, "apps_requirements", None),
        ),
    )


def _connector_id(value: AppConnectorId | str) -> str:
    if isinstance(value, str):
        return value
    return str(getattr(value, "value", getattr(value, "id", value)))


async def _maybe_await(value: Any) -> Any:
    import inspect

    return await value if inspect.isawaitable(value) else value


__all__ = [
    "AccessibleConnectorsStatus",
    "ChatgptAppsConnectorLoader",
    "connectors_for_plugin_apps",
    "list_accessible_connectors_from_mcp_tools",
    "list_accessible_connectors_from_mcp_tools_with_environment_manager",
    "list_all_connectors",
    "list_all_connectors_with_options",
    "list_cached_accessible_connectors_from_mcp_tools",
    "list_cached_all_connectors",
    "list_connectors",
    "merge_connectors_with_accessible",
]
