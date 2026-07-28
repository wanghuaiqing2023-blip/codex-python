"""Plugin manager owned by ``codex-core-plugins::manager``."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.config import PluginConfigEdit, apply_user_plugin_config_edits, clear_user_plugin
from pycodex.plugin import PluginId, PluginIdError, PluginLoadOutcome

from .installed_marketplaces import installed_marketplace_roots_from_layer_stack
from .loader import load_plugins_from_layer_stack
from .loader import curated_plugin_cache_version
from .marketplace import (
    MarketplaceError,
    MarketplacePluginAuthPolicy,
    MarketplacePluginSource,
    find_installable_marketplace_plugin,
    find_marketplace_plugin,
    list_marketplaces,
    load_marketplace,
)
from .marketplace_add.install import clone_git_source
from .marketplace_upgrade import (
    configured_git_marketplace_names,
    upgrade_configured_git_marketplaces,
)
from .remote import (
    RemoteInstalledPlugin,
    RemoteMarketplace,
    RemotePluginScope,
    RemotePluginServiceConfig,
    group_remote_installed_plugins_by_marketplaces,
)
from .startup_sync import (
    curated_plugins_repo_path,
    read_curated_plugins_sha,
    sync_openai_plugins_repo,
)
from .store import PluginStore, PluginStoreError


@dataclass(frozen=True)
class PluginsConfigInput:
    config_layer_stack: Any
    plugins_enabled: bool
    remote_plugin_enabled: bool
    chatgpt_base_url: str

    @classmethod
    def new(
        cls,
        config_layer_stack: Any,
        plugins_enabled: bool,
        remote_plugin_enabled: bool,
        chatgpt_base_url: str,
    ) -> "PluginsConfigInput":
        return cls(
            config_layer_stack,
            plugins_enabled,
            remote_plugin_enabled,
            chatgpt_base_url,
        )


@dataclass(frozen=True)
class PluginInstallRequest:
    plugin_name: str
    marketplace_path: Any


@dataclass(frozen=True)
class PluginReadRequest:
    plugin_name: str
    marketplace_path: Any


@dataclass(frozen=True)
class PluginInstallOutcome:
    plugin_id: Any
    plugin_version: str
    installed_path: Any
    auth_policy: Any


@dataclass(frozen=True)
class PluginReadOutcome:
    marketplace_name: str
    marketplace_path: Any | None
    plugin: "PluginDetail"


@dataclass(frozen=True)
class PluginHookSummary:
    key: str
    event_name: Any


class PluginDetailsUnavailableReason(str, Enum):
    INSTALL_REQUIRED_FOR_REMOTE_SOURCE = "install_required_for_remote_source"


@dataclass(frozen=True)
class PluginDetail:
    id: str
    name: str
    local_version: str | None = None
    description: str | None = None
    source: Any | None = None
    policy: Any | None = None
    interface: Any | None = None
    keywords: list[str] = field(default_factory=list)
    installed: bool = False
    enabled: bool = False
    skills: list[Any] = field(default_factory=list)
    disabled_skill_paths: set[Any] = field(default_factory=set)
    hooks: list[PluginHookSummary] = field(default_factory=list)
    apps: list[Any] = field(default_factory=list)
    mcp_server_names: list[str] = field(default_factory=list)
    details_unavailable_reason: PluginDetailsUnavailableReason | None = None


@dataclass(frozen=True)
class ConfiguredMarketplacePlugin:
    id: str
    name: str
    local_version: str | None = None
    installed_version: str | None = None
    source: Any | None = None
    policy: Any | None = None
    interface: Any | None = None
    keywords: list[str] = field(default_factory=list)
    installed: bool = False
    enabled: bool = False


@dataclass(frozen=True)
class ConfiguredMarketplace:
    name: str
    path: Any
    interface: Any | None = None
    plugins: list[ConfiguredMarketplacePlugin] = field(default_factory=list)


@dataclass(frozen=True)
class ConfiguredMarketplaceListOutcome:
    marketplaces: list[ConfiguredMarketplace] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class RemotePluginSyncResult:
    installed_plugin_ids: list[str] = field(default_factory=list)
    enabled_plugin_ids: list[str] = field(default_factory=list)
    disabled_plugin_ids: list[str] = field(default_factory=list)
    uninstalled_plugin_ids: list[str] = field(default_factory=list)


class PluginRemoteSyncError(Exception):
    pass


class PluginInstallError(Exception):
    def __init__(self, message: str, *, invalid_request: bool = False) -> None:
        super().__init__(message)
        self._invalid_request = invalid_request

    def is_invalid_request(self) -> bool:
        return self._invalid_request


class PluginUninstallError(Exception):
    def __init__(self, message: str, *, invalid_request: bool = False) -> None:
        super().__init__(message)
        self._invalid_request = invalid_request

    def is_invalid_request(self) -> bool:
        return self._invalid_request


class PluginsManager:
    def __init__(self, codex_home: Any, restriction_product: Any | None = None) -> None:
        self.codex_home = Path(codex_home).resolve()
        self.restriction_product = restriction_product
        self.store = PluginStore.new(self.codex_home)
        self._cached_enabled_outcome: tuple[str, PluginLoadOutcome] | None = None
        self._remote_installed_plugins_cache: list[RemoteInstalledPlugin] | None = None
        self._cache_lock = threading.RLock()
        self._remote_sync_lock = asyncio.Lock()
        self._analytics_events_client: Any | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()

    @classmethod
    def new(cls, codex_home: Any) -> "PluginsManager":
        return cls(codex_home)

    @classmethod
    def new_with_restriction_product(
        cls,
        codex_home: Any,
        restriction_product: Any,
    ) -> "PluginsManager":
        return cls(codex_home, restriction_product)

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cached_enabled_outcome = None

    def clear_remote_installed_plugins_cache(self) -> bool:
        with self._cache_lock:
            if self._remote_installed_plugins_cache is None:
                return False
            self._remote_installed_plugins_cache = None
            self._cached_enabled_outcome = None
            return True

    def set_analytics_events_client(self, analytics_events_client: Any) -> None:
        self._analytics_events_client = analytics_events_client

    async def plugins_for_config(
        self,
        plugins_config_input: PluginsConfigInput | Any,
    ) -> PluginLoadOutcome:
        if plugins_config_input is not None and not bool(
            getattr(plugins_config_input, "plugins_enabled", True)
        ):
            return PluginLoadOutcome()
        stack = getattr(
            plugins_config_input,
            "config_layer_stack",
            plugins_config_input,
        )
        version = repr(_effective_config(stack))
        with self._cache_lock:
            cached = self._cached_enabled_outcome
            if cached is not None and cached[0] == version:
                return cached[1]
        outcome = await load_plugins_from_layer_stack(stack, self.codex_home)
        with self._cache_lock:
            self._cached_enabled_outcome = (version, outcome)
        return outcome

    async def plugins_for_layer_stack(
        self,
        config_layer_stack: Any,
        config: PluginsConfigInput,
    ) -> PluginLoadOutcome:
        if not config.plugins_enabled:
            return PluginLoadOutcome()
        return await load_plugins_from_layer_stack(
            config_layer_stack,
            self.codex_home,
        )

    async def effective_skill_roots_for_layer_stack(
        self,
        config_layer_stack: Any,
        config: PluginsConfigInput,
    ) -> list[Any]:
        outcome = await self.plugins_for_layer_stack(config_layer_stack, config)
        return list(outcome.effective_plugin_skill_roots())

    def build_remote_installed_plugin_marketplaces_from_cache(
        self,
        visible_scopes: list[RemotePluginScope] | tuple[RemotePluginScope, ...],
    ) -> list[RemoteMarketplace] | None:
        with self._cache_lock:
            cache = (
                None
                if self._remote_installed_plugins_cache is None
                else list(self._remote_installed_plugins_cache)
            )
        if cache is None:
            return None
        return group_remote_installed_plugins_by_marketplaces(
            cache,
            visible_scopes,
        )

    async def build_and_cache_remote_installed_plugin_marketplaces(
        self,
        config: PluginsConfigInput,
        auth: Any | None,
        visible_scopes: list[RemotePluginScope] | tuple[RemotePluginScope, ...],
        on_effective_plugins_changed: Any | None = None,
        *,
        fetch_installed: Any | None = None,
    ) -> list[RemoteMarketplace]:
        if fetch_installed is None:
            from .remote import fetch_remote_installed_plugins

            fetch_installed = fetch_remote_installed_plugins
        plugins = await fetch_installed(
            RemotePluginServiceConfig(config.chatgpt_base_url),
            auth,
        )
        changed = self._write_remote_installed_plugins_cache(list(plugins))
        if changed and on_effective_plugins_changed is not None:
            on_effective_plugins_changed()
        return group_remote_installed_plugins_by_marketplaces(
            plugins,
            visible_scopes,
        )

    def _write_remote_installed_plugins_cache(
        self,
        plugins: list[RemoteInstalledPlugin],
    ) -> bool:
        with self._cache_lock:
            if self._remote_installed_plugins_cache == plugins:
                return False
            self._remote_installed_plugins_cache = list(plugins)
            self._cached_enabled_outcome = None
            return True

    def list_marketplaces_for_config(
        self,
        plugins_config_input: PluginsConfigInput | None,
        extra_marketplaces: list[Any] | tuple[Any, ...],
    ) -> ConfiguredMarketplaceListOutcome:
        if plugins_config_input is None or not plugins_config_input.plugins_enabled:
            return ConfiguredMarketplaceListOutcome()
        roots = self._marketplace_roots(
            plugins_config_input,
            extra_marketplaces,
        )
        outcome = list_marketplaces(roots)
        _configured, enabled = _configured_plugin_states(
            plugins_config_input.config_layer_stack
        )
        marketplaces: list[ConfiguredMarketplace] = []
        for marketplace in outcome.marketplaces:
            plugins: list[ConfiguredMarketplacePlugin] = []
            for plugin in marketplace.plugins:
                if not self._restriction_product_matches(plugin.policy.products):
                    continue
                plugin_id = PluginId.parse(
                    f"{plugin.name}@{marketplace.name}"
                )
                key = plugin_id.as_key()
                is_installed = self.store.is_installed(plugin_id)
                plugins.append(
                    ConfiguredMarketplacePlugin(
                        id=key,
                        name=plugin.name,
                        local_version=plugin.local_version,
                        installed_version=(
                            self.store.active_plugin_version(plugin_id)
                            if is_installed
                            else None
                        ),
                        source=plugin.source,
                        policy=plugin.policy,
                        interface=plugin.interface,
                        keywords=list(plugin.keywords),
                        installed=is_installed,
                        enabled=key in enabled,
                    )
                )
            if plugins:
                marketplaces.append(
                    ConfiguredMarketplace(
                        name=marketplace.name,
                        path=marketplace.path,
                        interface=marketplace.interface,
                        plugins=plugins,
                    )
                )
        return ConfiguredMarketplaceListOutcome(
            marketplaces=marketplaces,
            errors=list(outcome.errors),
        )

    def discover_marketplaces_for_config(
        self,
        config: PluginsConfigInput,
        additional_roots: list[Any] | tuple[Any, ...],
    ) -> Any:
        if not config.plugins_enabled:
            from .marketplace import MarketplaceListOutcome

            return MarketplaceListOutcome()
        return list_marketplaces(self._marketplace_roots(config, additional_roots))

    async def read_plugin_for_config(
        self,
        config: PluginsConfigInput,
        request: PluginReadRequest,
    ) -> PluginReadOutcome:
        if not config.plugins_enabled:
            raise MarketplaceError("plugins are disabled")
        resolved = find_marketplace_plugin(
            request.marketplace_path,
            request.plugin_name,
        )
        plugin_key = resolved.plugin_id.as_key()
        _configured, enabled = _configured_plugin_states(config.config_layer_stack)
        is_installed = self.store.is_installed(resolved.plugin_id)
        detail = await self.read_plugin_detail_for_marketplace_plugin(
            config,
            resolved.plugin_id.marketplace_name,
            ConfiguredMarketplacePlugin(
                id=plugin_key,
                name=resolved.plugin_id.plugin_name,
                local_version=(
                    resolved.manifest.version
                    if resolved.manifest is not None
                    else None
                ),
                installed_version=(
                    self.store.active_plugin_version(resolved.plugin_id)
                    if is_installed
                    else None
                ),
                source=resolved.source,
                policy=resolved.policy,
                interface=resolved.interface,
                keywords=(
                    list(resolved.manifest.keywords)
                    if resolved.manifest is not None
                    else []
                ),
                installed=is_installed,
                enabled=plugin_key in enabled,
            ),
        )
        return PluginReadOutcome(
            marketplace_name=resolved.plugin_id.marketplace_name,
            marketplace_path=request.marketplace_path,
            plugin=detail,
        )

    async def read_plugin_detail_for_marketplace_plugin(
        self,
        plugins_config_input: PluginsConfigInput | None,
        marketplace_name: str,
        plugin: ConfiguredMarketplacePlugin,
    ) -> PluginDetail:
        if not self._restriction_product_matches(
            getattr(plugin.policy, "products", None)
        ):
            raise MarketplaceError(f"plugin not available: {plugin.id}")
        plugin_id = PluginId.parse(f"{plugin.name}@{marketplace_name}")
        if (
            getattr(plugin.source, "kind", None) == "git"
            and not plugin.installed
        ):
            return PluginDetail(
                id=plugin.id,
                name=plugin.name,
                description="Install this plugin to view its details.",
                source=plugin.source,
                policy=plugin.policy,
                interface=plugin.interface,
                keywords=list(plugin.keywords),
                installed=False,
                enabled=plugin.enabled,
                details_unavailable_reason=(
                    PluginDetailsUnavailableReason.INSTALL_REQUIRED_FOR_REMOTE_SOURCE
                ),
            )
        source_path = (
            self.store.active_plugin_root(plugin_id)
            if getattr(plugin.source, "kind", None) == "git"
            else Path(plugin.source.path)
        )
        if source_path is None or not Path(source_path).is_dir():
            raise MarketplaceError("path does not exist or is not a directory")
        from .manifest import load_plugin_manifest

        manifest = load_plugin_manifest(source_path)
        if manifest is None:
            raise MarketplaceError("missing or invalid plugin.json")
        return PluginDetail(
            id=plugin.id,
            name=plugin.name,
            local_version=manifest.version,
            description=manifest.description,
            source=plugin.source,
            policy=plugin.policy,
            interface=manifest.interface or plugin.interface,
            keywords=list(manifest.keywords),
            installed=plugin.installed,
            enabled=plugin.enabled,
        )

    async def install_plugin(
        self,
        request: PluginInstallRequest,
    ) -> PluginInstallOutcome:
        try:
            resolved = find_installable_marketplace_plugin(
                request.marketplace_path,
                request.plugin_name,
                self.restriction_product,
            )
            source_path, cleanup = await asyncio.to_thread(
                self._materialize_plugin_source,
                resolved.source,
            )
            try:
                version = (
                    curated_plugin_cache_version(
                        read_curated_plugins_sha(self.codex_home) or "local"
                    )
                    if resolved.plugin_id.marketplace_name == "openai-curated"
                    else None
                )
                result = await asyncio.to_thread(
                    self.store.install_with_version,
                    source_path,
                    resolved.plugin_id,
                    version
                    or (
                        resolved.manifest.version
                        if resolved.manifest is not None
                        and resolved.manifest.version
                        else "local"
                    ),
                )
            finally:
                if cleanup is not None:
                    shutil.rmtree(cleanup, ignore_errors=True)
            await apply_user_plugin_config_edits(
                self.codex_home,
                [PluginConfigEdit.set_enabled(resolved.plugin_id.as_key(), True)],
            )
            self.clear_cache()
            return PluginInstallOutcome(
                plugin_id=result.plugin_id,
                plugin_version=result.plugin_version,
                installed_path=result.installed_path,
                auth_policy=resolved.policy.authentication,
            )
        except (MarketplaceError, PluginStoreError, PluginIdError) as exc:
            raise PluginInstallError(
                str(exc),
                invalid_request=isinstance(exc, (MarketplaceError, PluginIdError)),
            ) from exc

    async def install_plugin_with_remote_sync(
        self,
        config: PluginsConfigInput,
        auth: Any | None,
        request: PluginInstallRequest,
    ) -> PluginInstallOutcome:
        from .remote_legacy import enable_remote_plugin

        resolved = find_installable_marketplace_plugin(
            request.marketplace_path,
            request.plugin_name,
            self.restriction_product,
        )
        await enable_remote_plugin(
            RemotePluginServiceConfig(config.chatgpt_base_url),
            auth,
            resolved.plugin_id.as_key(),
        )
        return await self.install_plugin(request)

    async def uninstall_plugin(self, plugin_id: str) -> None:
        try:
            parsed = PluginId.parse(plugin_id)
        except PluginIdError as exc:
            raise PluginUninstallError(str(exc), invalid_request=True) from exc
        try:
            await asyncio.to_thread(self.store.uninstall, parsed)
            await clear_user_plugin(self.codex_home, parsed.as_key())
            self.clear_cache()
        except (PluginStoreError, OSError) as exc:
            raise PluginUninstallError(str(exc)) from exc

    async def uninstall_plugin_with_remote_sync(
        self,
        config: PluginsConfigInput,
        auth: Any | None,
        plugin_id: str,
    ) -> None:
        from .remote_legacy import uninstall_remote_plugin

        parsed = PluginId.parse(plugin_id)
        await uninstall_remote_plugin(
            RemotePluginServiceConfig(config.chatgpt_base_url),
            auth,
            parsed.as_key(),
        )
        await self.uninstall_plugin(parsed.as_key())

    async def sync_plugins_from_remote(
        self,
        config: PluginsConfigInput,
        auth: Any | None,
        additive_only: bool,
    ) -> RemotePluginSyncResult:
        from .remote_legacy import fetch_remote_plugin_status

        async with self._remote_sync_lock:
            if not config.plugins_enabled:
                return RemotePluginSyncResult()
            remote_plugins = await fetch_remote_plugin_status(
                RemotePluginServiceConfig(config.chatgpt_base_url),
                auth,
            )
            marketplace_path = (
                curated_plugins_repo_path(self.codex_home)
                / ".agents"
                / "plugins"
                / "marketplace.json"
            )
            if not marketplace_path.is_file():
                raise PluginRemoteSyncError("local curated marketplace not found")
            marketplace = load_marketplace(marketplace_path)
            sha = read_curated_plugins_sha(self.codex_home)
            if sha is None:
                raise PluginRemoteSyncError(
                    "local curated marketplace sha is not available"
                )
            cache_version = curated_plugin_cache_version(sha)
            configured = _configured_plugins_from_stack(
                config.config_layer_stack
            )
            local_by_name = {plugin.name: plugin for plugin in marketplace.plugins}
            remote_names: set[str] = set()
            for plugin in remote_plugins:
                if plugin.marketplace_name != marketplace.name:
                    raise PluginRemoteSyncError(
                        f"unknown remote marketplace: {plugin.marketplace_name}"
                    )
                if plugin.name not in local_by_name or not plugin.enabled:
                    continue
                if plugin.name in remote_names:
                    raise PluginRemoteSyncError(
                        f"duplicate remote plugin: {plugin.name}"
                    )
                remote_names.add(plugin.name)

            result = RemotePluginSyncResult()
            edits: list[PluginConfigEdit] = []
            for name, local in local_by_name.items():
                try:
                    plugin_id = PluginId.parse(f"{name}@{marketplace.name}")
                except PluginIdError:
                    continue
                key = plugin_id.as_key()
                current = configured.get(key)
                installed = self.store.is_installed(plugin_id)
                if name in remote_names:
                    if not installed:
                        if local.source.kind != "local":
                            continue
                        await asyncio.to_thread(
                            self.store.install_with_version,
                            Path(local.source.path),
                            plugin_id,
                            cache_version,
                        )
                        result.installed_plugin_ids.append(key)
                    if current is None or not current:
                        edits.append(PluginConfigEdit.set_enabled(key, True))
                        result.enabled_plugin_ids.append(key)
                elif not additive_only:
                    if installed:
                        await asyncio.to_thread(self.store.uninstall, plugin_id)
                    if installed or current is not None:
                        result.uninstalled_plugin_ids.append(key)
                    if current is not None:
                        edits.append(PluginConfigEdit.clear(key))
            if edits:
                await apply_user_plugin_config_edits(self.codex_home, edits)
            self.clear_cache()
            return result

    def maybe_start_remote_installed_plugin_bundle_sync(
        self,
        config: PluginsConfigInput,
        auth: Any | None,
        on_effective_plugins_changed: Any | None = None,
        *,
        fetch_installed: Any | None = None,
    ) -> asyncio.Task[None] | None:
        if not config.plugins_enabled:
            return None
        from .remote import maybe_start_remote_installed_plugin_bundle_sync

        return maybe_start_remote_installed_plugin_bundle_sync(
            self.codex_home,
            RemotePluginServiceConfig(config.chatgpt_base_url),
            auth,
            on_effective_plugins_changed,
            fetch_installed=fetch_installed,
        )

    def maybe_start_plugin_list_background_tasks_for_config(
        self,
        config: PluginsConfigInput,
        auth: Any | None,
        roots: list[Any] | tuple[Any, ...],
        on_effective_plugins_changed: Any | None = None,
    ) -> None:
        del roots
        self.maybe_start_remote_installed_plugin_bundle_sync(
            config,
            auth,
            on_effective_plugins_changed,
        )

    def maybe_start_plugin_startup_tasks_for_config(
        self,
        config: PluginsConfigInput,
        auth_manager: Any,
        on_effective_plugins_changed: Any | None = None,
    ) -> None:
        if not config.plugins_enabled:
            return
        self._spawn_background(asyncio.to_thread(sync_openai_plugins_repo, self.codex_home))
        from .startup_remote_sync import start_startup_remote_plugin_sync_once

        task = start_startup_remote_plugin_sync_once(
            self,
            self.codex_home,
            config,
            auth_manager,
        )
        if task is not None:
            self._track_task(task)

        async def warm_remote_cache() -> None:
            auth = auth_manager.auth()
            if hasattr(auth, "__await__"):
                auth = await auth
            self.maybe_start_remote_installed_plugin_bundle_sync(
                config,
                auth,
                on_effective_plugins_changed,
            )

        self._spawn_background(warm_remote_cache())

    def upgrade_configured_marketplaces_for_config(
        self,
        config: PluginsConfigInput,
        marketplace_name: str | None = None,
    ) -> Any:
        if marketplace_name is not None and marketplace_name not in set(
            configured_git_marketplace_names(config.config_layer_stack)
        ):
            raise ValueError(
                f"marketplace `{marketplace_name}` is not configured as a Git marketplace"
            )
        outcome = upgrade_configured_git_marketplaces(
            self.codex_home,
            config.config_layer_stack,
            marketplace_name,
        )
        if outcome.upgraded_roots:
            self.clear_cache()
        return outcome

    def maybe_start_non_curated_plugin_cache_refresh(
        self,
        roots: list[Any] | tuple[Any, ...],
    ) -> None:
        if roots:
            self.clear_cache()

    def _restriction_product_matches(
        self,
        products: tuple[Any, ...] | list[Any] | None,
    ) -> bool:
        if products is None:
            return True
        if not products:
            return False
        if self.restriction_product is None:
            return False
        return any(
            getattr(product, "value", product)
            == getattr(self.restriction_product, "value", self.restriction_product)
            for product in products
        )

    def _marketplace_roots(
        self,
        config: PluginsConfigInput,
        additional_roots: list[Any] | tuple[Any, ...],
    ) -> list[Path]:
        roots = [
            curated_plugins_repo_path(self.codex_home),
            *installed_marketplace_roots_from_layer_stack(
                config.config_layer_stack,
                self.codex_home,
            ),
            *(Path(root) for root in additional_roots),
        ]
        return list(dict.fromkeys(root.resolve() for root in roots if Path(root).exists()))

    def _materialize_plugin_source(
        self,
        source: MarketplacePluginSource,
    ) -> tuple[Path, Path | None]:
        if source.kind == "local":
            return Path(source.path), None
        if source.kind != "git" or not source.url:
            raise MarketplaceError("unsupported plugin source")
        temp = Path(tempfile.mkdtemp(prefix="plugin-source-"))
        clone_git_source(source.url, source.ref_name, (), temp)
        root = temp / str(source.path) if source.path else temp
        return root, temp

    def _spawn_background(self, awaitable: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(awaitable)
        self._track_task(task)
        return task

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)


def _effective_config(stack: Any) -> dict[str, Any]:
    reader = getattr(stack, "effective_config", None)
    value = reader() if callable(reader) else stack
    if isinstance(value, Mapping):
        return dict(value)
    plugins = getattr(value, "plugins", None)
    return {"plugins": plugins} if plugins is not None else {}


def _configured_plugins_from_stack(stack: Any) -> dict[str, bool]:
    config = _effective_config(stack)
    plugins = config.get("plugins")
    if not isinstance(plugins, Mapping):
        return {}
    configured: dict[str, bool] = {}
    for plugin_key, plugin_config in plugins.items():
        if not isinstance(plugin_key, str):
            continue
        if isinstance(plugin_config, Mapping):
            enabled = plugin_config.get("enabled", True)
        else:
            enabled = getattr(plugin_config, "enabled", True)
        configured[plugin_key] = bool(enabled)
    return configured


def _configured_plugin_states(stack: Any) -> tuple[set[str], set[str]]:
    configured = _configured_plugins_from_stack(stack)
    installed = set(configured)
    enabled = {plugin_id for plugin_id, value in configured.items() if value}
    return installed, enabled


__all__ = [
    "ConfiguredMarketplace",
    "ConfiguredMarketplaceListOutcome",
    "ConfiguredMarketplacePlugin",
    "PluginDetail",
    "PluginDetailsUnavailableReason",
    "PluginHookSummary",
    "PluginInstallError",
    "PluginInstallOutcome",
    "PluginInstallRequest",
    "PluginReadOutcome",
    "PluginReadRequest",
    "PluginRemoteSyncError",
    "PluginUninstallError",
    "PluginsConfigInput",
    "PluginsManager",
    "RemotePluginSyncResult",
]
