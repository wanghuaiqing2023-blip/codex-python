"""Remote plugin catalog behavior.

Rust owner: ``codex-core-plugins::remote``.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pycodex.app_server_protocol import (
    PluginAuthPolicy,
    PluginAvailability,
    PluginInstallPolicy,
)
from pycodex.model_provider.auth import auth_provider_from_auth
from pycodex.plugin import PluginId, PluginIdError

from .share import (
    RemotePluginShareAccessPolicy,
    RemotePluginShareCheckoutResult,
    RemotePluginShareDiscoverability,
    RemotePluginSharePrincipal,
    RemotePluginSharePrincipalRole,
    RemotePluginSharePrincipalType,
    RemotePluginShareSaveResult,
    RemotePluginShareTarget,
    RemotePluginShareTargetRole,
    RemotePluginShareUpdateDiscoverability,
    RemotePluginShareUpdateTargetsResult,
    delete_remote_plugin_share,
    checkout_remote_plugin_share,
    list_remote_plugin_shares,
    load_plugin_share_remote_ids_by_local_path,
    save_remote_plugin_share,
    update_remote_plugin_share_targets,
)

REMOTE_GLOBAL_MARKETPLACE_NAME = "openai-curated-remote"
REMOTE_WORKSPACE_MARKETPLACE_NAME = "workspace-directory"
REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME = "workspace-shared-with-me"
REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME = (
    "workspace-shared-with-me-private"
)
REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_NAME = (
    "workspace-shared-with-me-unlisted"
)
REMOTE_GLOBAL_MARKETPLACE_DISPLAY_NAME = "OpenAI Curated Remote"
REMOTE_WORKSPACE_MARKETPLACE_DISPLAY_NAME = "Workspace Directory"
REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_DISPLAY_NAME = "Shared with me"
REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_DISPLAY_NAME = (
    "Shared with me (unlisted)"
)

_MARKETPLACE_DISPLAY_ORDER = (
    (REMOTE_GLOBAL_MARKETPLACE_NAME, REMOTE_GLOBAL_MARKETPLACE_DISPLAY_NAME),
    (REMOTE_WORKSPACE_MARKETPLACE_NAME, REMOTE_WORKSPACE_MARKETPLACE_DISPLAY_NAME),
    (
        REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_DISPLAY_NAME,
    ),
    (
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_DISPLAY_NAME,
    ),
    (
        REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_DISPLAY_NAME,
    ),
)


@dataclass(frozen=True)
class RemotePluginServiceConfig:
    chatgpt_base_url: str


@dataclass
class RemoteMarketplace:
    name: str
    display_name: str
    plugins: list["RemotePluginSummary"] = field(default_factory=list)


class RemoteMarketplaceSource(str, Enum):
    GLOBAL = "global"
    WORKSPACE_DIRECTORY = "workspace-directory"
    SHARED_WITH_ME = "shared-with-me"


class RemotePluginScope(str, Enum):
    GLOBAL = "GLOBAL"
    WORKSPACE = "WORKSPACE"

    def marketplace_name(self) -> str:
        if self is RemotePluginScope.GLOBAL:
            return REMOTE_GLOBAL_MARKETPLACE_NAME
        return REMOTE_WORKSPACE_MARKETPLACE_NAME

    def marketplace_display_name(self) -> str:
        if self is RemotePluginScope.GLOBAL:
            return REMOTE_GLOBAL_MARKETPLACE_DISPLAY_NAME
        return REMOTE_WORKSPACE_MARKETPLACE_DISPLAY_NAME

    @classmethod
    def from_marketplace_name(cls, name: str) -> "RemotePluginScope | None":
        if name == REMOTE_GLOBAL_MARKETPLACE_NAME:
            return cls.GLOBAL
        if name in {
            REMOTE_WORKSPACE_MARKETPLACE_NAME,
            REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
            REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
            REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_NAME,
        }:
            return cls.WORKSPACE
        return None


@dataclass
class RemoteInstalledPlugin:
    marketplace_name: str
    id: str
    name: str
    enabled: bool
    install_policy: PluginInstallPolicy
    auth_policy: PluginAuthPolicy
    availability: PluginAvailability
    interface: Any | None = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class RemotePluginSummary:
    id: str
    remote_plugin_id: str
    name: str
    share_context: "RemotePluginShareContext | None"
    installed: bool
    enabled: bool
    install_policy: PluginInstallPolicy
    auth_policy: PluginAuthPolicy
    availability: PluginAvailability
    interface: Any | None = None
    keywords: list[str] = field(default_factory=list)


@dataclass
class RemotePluginShareContext:
    remote_plugin_id: str
    remote_version: str | None
    discoverability: RemotePluginShareDiscoverability
    share_url: str | None = None
    creator_account_user_id: str | None = None
    creator_name: str | None = None
    share_principals: list[RemotePluginSharePrincipal] | None = None


@dataclass
class RemotePluginShareSummary:
    summary: RemotePluginSummary
    local_plugin_path: Path | None = None


@dataclass
class RemotePluginSkill:
    name: str
    description: str
    short_description: str | None = None
    interface: Any | None = None
    enabled: bool = True


@dataclass
class RemotePluginSkillDetail:
    contents: str | None


@dataclass
class RemotePluginDetail:
    marketplace_name: str
    marketplace_display_name: str
    summary: RemotePluginSummary
    description: str | None = None
    release_version: str | None = None
    bundle_download_url: str | None = None
    app_manifest: Any | None = None
    skills: list[RemotePluginSkill] = field(default_factory=list)
    app_ids: list[str] = field(default_factory=list)


class RemotePluginCatalogError(RuntimeError):
    pass


class InvalidRemotePluginIdError(RemotePluginCatalogError):
    pass


def is_valid_remote_plugin_id(plugin_id: str) -> bool:
    return bool(plugin_id) and all(
        character.isascii()
        and (character.isalnum() or character in {"-", "_", "~"})
        for character in plugin_id
    )


def validate_remote_plugin_id(plugin_id: str) -> None:
    if not is_valid_remote_plugin_id(plugin_id):
        raise InvalidRemotePluginIdError(
            "invalid remote plugin id: only ASCII letters, digits, `_`, `-`, "
            "and `~` are allowed"
        )


def group_remote_installed_plugins_by_marketplaces(
    plugins: Iterable[RemoteInstalledPlugin],
    visible_scopes: Iterable[RemotePluginScope],
) -> list[RemoteMarketplace]:
    visible = set(visible_scopes)
    grouped: dict[str, list[RemotePluginSummary]] = {}

    for plugin in plugins:
        scope = RemotePluginScope.from_marketplace_name(plugin.marketplace_name)
        if scope not in visible:
            continue
        try:
            plugin_id = PluginId.parse(
                f"{plugin.name}@{plugin.marketplace_name}"
            ).as_key()
        except PluginIdError:
            continue
        grouped.setdefault(plugin.marketplace_name, []).append(
            RemotePluginSummary(
                id=plugin_id,
                remote_plugin_id=plugin.id,
                name=plugin.name,
                share_context=None,
                installed=True,
                enabled=plugin.enabled,
                install_policy=plugin.install_policy,
                auth_policy=plugin.auth_policy,
                availability=plugin.availability,
                interface=plugin.interface,
                keywords=list(plugin.keywords),
            )
        )

    marketplaces: list[RemoteMarketplace] = []
    for marketplace_name, display_name in _MARKETPLACE_DISPLAY_ORDER:
        marketplace_plugins = grouped.get(marketplace_name)
        if not marketplace_plugins:
            continue
        marketplace_plugins.sort(
            key=lambda plugin: _remote_plugin_display_name(plugin).casefold()
        )
        marketplaces.append(
            RemoteMarketplace(
                name=marketplace_name,
                display_name=display_name,
                plugins=marketplace_plugins,
            )
        )
    return marketplaces


def _remote_plugin_display_name(plugin: RemotePluginSummary) -> str:
    interface = plugin.interface
    if interface is not None:
        if isinstance(interface, dict):
            display_name = interface.get("display_name") or interface.get("displayName")
        else:
            display_name = getattr(interface, "display_name", None)
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    return plugin.name


async def fetch_installed_plugins_for_scope(
    config: RemotePluginServiceConfig,
    auth: Any | None,
    scope: RemotePluginScope,
    include_download_urls: bool = False,
) -> list[Mapping[str, Any]]:
    if not isinstance(scope, RemotePluginScope):
        scope = RemotePluginScope(str(getattr(scope, "value", scope)).upper())
    plugins: list[Mapping[str, Any]] = []
    page_token: str | None = None
    while True:
        query: dict[str, object] = {"scope": scope.value}
        if include_download_urls:
            query["includeDownloadUrls"] = "true"
        if page_token is not None:
            query["pageToken"] = page_token
        payload = await _request_json(
            config,
            auth,
            "/ps/plugins/installed",
            query,
        )
        raw_plugins = payload.get("plugins", [])
        if not isinstance(raw_plugins, list):
            raise RemotePluginCatalogError(
                "remote installed-plugin response has invalid `plugins`"
            )
        plugins.extend(
            plugin for plugin in raw_plugins if isinstance(plugin, Mapping)
        )
        pagination = payload.get("pagination", {})
        if not isinstance(pagination, Mapping):
            break
        next_value = pagination.get("next_page_token", pagination.get("nextPageToken"))
        page_token = (
            next_value.strip()
            if isinstance(next_value, str) and next_value.strip()
            else None
        )
        if page_token is None:
            break
    return plugins


async def fetch_remote_installed_plugins(
    config: RemotePluginServiceConfig,
    auth: Any | None,
) -> list[RemoteInstalledPlugin]:
    global_plugins, workspace_plugins = await asyncio.gather(
        fetch_installed_plugins_for_scope(
            config,
            auth,
            RemotePluginScope.GLOBAL,
        ),
        fetch_installed_plugins_for_scope(
            config,
            auth,
            RemotePluginScope.WORKSPACE,
        ),
    )
    result = [
        _remote_installed_plugin_from_mapping(plugin)
        for plugin in [*global_plugins, *workspace_plugins]
    ]
    result.sort(key=lambda plugin: (plugin.marketplace_name, plugin.id))
    return result


def _remote_installed_plugin_from_mapping(
    installed: Mapping[str, Any],
) -> RemoteInstalledPlugin:
    plugin = installed.get("plugin", installed)
    if not isinstance(plugin, Mapping):
        raise RemotePluginCatalogError("remote installed-plugin item is invalid")
    scope = RemotePluginScope(
        str(getattr(plugin.get("scope"), "value", plugin.get("scope", ""))).upper()
    )
    marketplace_name = scope.marketplace_name()
    if scope is RemotePluginScope.WORKSPACE:
        discoverability = str(
            getattr(
                plugin.get("discoverability"),
                "value",
                plugin.get("discoverability", ""),
            )
        ).upper()
        if discoverability not in {"LISTED", "PRIVATE", "UNLISTED"}:
            raise RemotePluginCatalogError(
                f"workspace plugin `{plugin.get('id', '')}` did not include discoverability"
            )
        if discoverability != "LISTED":
            marketplace_name = REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME
    release = plugin.get("release", {})
    if not isinstance(release, Mapping):
        release = {}
    interface = release.get("interface")
    if isinstance(interface, Mapping):
        interface = dict(interface)
        display_name = release.get("display_name", release.get("displayName"))
        if isinstance(display_name, str) and display_name.strip():
            interface.setdefault("display_name", display_name.strip())
    return RemoteInstalledPlugin(
        marketplace_name=marketplace_name,
        id=str(plugin.get("id", "")),
        name=str(plugin.get("name", "")),
        enabled=bool(installed.get("enabled", False)),
        install_policy=PluginInstallPolicy.parse(
            plugin.get("installation_policy", plugin.get("installationPolicy"))
        ),
        auth_policy=PluginAuthPolicy.parse(
            plugin.get("authentication_policy", plugin.get("authenticationPolicy"))
        ),
        availability=PluginAvailability.parse(
            plugin.get("status", "AVAILABLE")
        ),
        interface=interface,
        keywords=[
            str(keyword)
            for keyword in release.get("keywords", [])
            if isinstance(keyword, str)
        ],
    )


async def _request_json(
    config: RemotePluginServiceConfig,
    auth: Any | None,
    path: str,
    query: Mapping[str, object],
) -> Mapping[str, Any]:
    headers = _remote_auth_headers(auth)
    base_url = config.chatgpt_base_url.rstrip("/")
    url = f"{base_url}{path}"
    encoded = urlencode(query)
    if encoded:
        url = f"{url}?{encoded}"

    def send() -> Mapping[str, Any]:
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30) as response:
                status = int(getattr(response, "status", 200))
                body = response.read().decode("utf-8")
        except Exception as exc:
            raise RemotePluginCatalogError(
                f"failed to send remote plugin catalog request to {url}: {exc}"
            ) from exc
        if status < 200 or status >= 300:
            raise RemotePluginCatalogError(
                f"remote plugin catalog request to {url} failed with status {status}: {body}"
            )
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RemotePluginCatalogError(
                f"failed to parse remote plugin catalog response from {url}: {exc}"
            ) from exc
        if not isinstance(payload, Mapping):
            raise RemotePluginCatalogError(
                f"remote plugin catalog response from {url} is not an object"
            )
        return payload

    return await asyncio.to_thread(send)


def _remote_auth_headers(auth: Any | None) -> dict[str, str]:
    if auth is None:
        raise RemotePluginCatalogError(
            "chatgpt authentication required for remote plugin catalog"
        )
    uses_backend = getattr(auth, "uses_codex_backend", None)
    uses_backend = uses_backend() if callable(uses_backend) else uses_backend
    if isinstance(auth, Mapping):
        uses_backend = auth.get("uses_codex_backend", uses_backend)
    if uses_backend is False:
        raise RemotePluginCatalogError(
            "chatgpt authentication required for remote plugin catalog; "
            "api key auth is not supported"
        )
    return {
        str(key): str(value)
        for key, value in auth_provider_from_auth(auth).to_auth_headers().items()
    }


async def _transport_call(method: str, *args: Any, **kwargs: Any) -> Any:
    transport = kwargs.pop("transport", None)
    if transport is None:
        raise RemotePluginCatalogError("remote plugin catalog transport is required")
    operation = getattr(transport, method)
    return await operation(*args, **kwargs)


async def fetch_remote_marketplaces(*args: Any, **kwargs: Any) -> Any:
    return await _transport_call("fetch_remote_marketplaces", *args, **kwargs)


async def fetch_openai_curated_remote_collection_marketplace(
    *args: Any,
    **kwargs: Any,
) -> Any:
    return await _transport_call(
        "fetch_openai_curated_remote_collection_marketplace",
        *args,
        **kwargs,
    )


async def fetch_remote_plugin_detail(*args: Any, **kwargs: Any) -> Any:
    return await _transport_call("fetch_remote_plugin_detail", *args, **kwargs)


async def fetch_remote_plugin_share_context(*args: Any, **kwargs: Any) -> Any:
    return await _transport_call("fetch_remote_plugin_share_context", *args, **kwargs)


async def fetch_remote_plugin_skill_detail(*args: Any, **kwargs: Any) -> Any:
    return await _transport_call("fetch_remote_plugin_skill_detail", *args, **kwargs)


async def install_remote_plugin(*args: Any, **kwargs: Any) -> Any:
    return await _transport_call("install_remote_plugin", *args, **kwargs)


async def uninstall_remote_plugin(*args: Any, **kwargs: Any) -> Any:
    return await _transport_call("uninstall_remote_plugin", *args, **kwargs)


from .remote_installed_plugin_sync import (  # noqa: E402
    RemoteInstalledPluginBundleSyncError,
    RemoteInstalledPluginBundleSyncOutcome,
    RemotePluginCacheMutationGuard,
    mark_remote_plugin_cache_mutation_in_flight,
    maybe_start_remote_installed_plugin_bundle_sync,
    sync_remote_installed_plugin_bundles_once,
)


__all__ = [
    name
    for name in globals()
    if name.startswith("REMOTE_")
    or name.startswith("Remote")
    or name
    in {
        "delete_remote_plugin_share",
        "checkout_remote_plugin_share",
        "fetch_openai_curated_remote_collection_marketplace",
        "fetch_installed_plugins_for_scope",
        "fetch_remote_marketplaces",
        "fetch_remote_installed_plugins",
        "fetch_remote_plugin_detail",
        "fetch_remote_plugin_share_context",
        "fetch_remote_plugin_skill_detail",
        "group_remote_installed_plugins_by_marketplaces",
        "install_remote_plugin",
        "is_valid_remote_plugin_id",
        "list_remote_plugin_shares",
        "load_plugin_share_remote_ids_by_local_path",
        "save_remote_plugin_share",
        "uninstall_remote_plugin",
        "update_remote_plugin_share_targets",
        "validate_remote_plugin_id",
    }
]
