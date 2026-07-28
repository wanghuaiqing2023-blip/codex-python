"""Remote installed-plugin bundle synchronization.

Rust owner: ``codex-core-plugins::remote::remote_installed_plugin_sync``.
"""

from __future__ import annotations

import asyncio
import shutil
import threading
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pycodex.plugin import PluginId, PluginIdError

from ..store import PLUGINS_CACHE_DIR, PluginStore
from . import (
    REMOTE_GLOBAL_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_NAME,
    RemotePluginScope,
)

_MARKETPLACES = (
    REMOTE_GLOBAL_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
    REMOTE_WORKSPACE_SHARED_WITH_ME_UNLISTED_MARKETPLACE_NAME,
)
_SYNC_LOCK = threading.Lock()
_SYNCS_IN_FLIGHT: set[Path] = set()
_MUTATION_LOCK = threading.Lock()
_MUTATIONS_IN_FLIGHT: dict[tuple[Path, str, str], int] = {}


@dataclass
class RemoteInstalledPluginBundleSyncOutcome:
    installed_plugin_ids: list[str] = field(default_factory=list)
    removed_cache_plugin_ids: list[str] = field(default_factory=list)
    failed_remote_plugin_ids: list[str] = field(default_factory=list)

    def changed_local_cache(self) -> bool:
        return bool(self.installed_plugin_ids or self.removed_cache_plugin_ids)


class RemoteInstalledPluginBundleSyncError(RuntimeError):
    pass


class RemotePluginCacheMutationGuard:
    def __init__(self, key: tuple[Path, str, str]) -> None:
        self._key = key
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with _MUTATION_LOCK:
            count = _MUTATIONS_IN_FLIGHT.get(self._key, 0)
            if count <= 1:
                _MUTATIONS_IN_FLIGHT.pop(self._key, None)
            else:
                _MUTATIONS_IN_FLIGHT[self._key] = count - 1

    def __enter__(self) -> "RemotePluginCacheMutationGuard":
        return self

    def __exit__(self, *unused: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


def mark_remote_plugin_cache_mutation_in_flight(
    codex_home: Path,
    marketplace_name: str,
    plugin_name: str,
) -> RemotePluginCacheMutationGuard:
    key = (
        _remote_plugin_cache_root(Path(codex_home)),
        str(marketplace_name),
        str(plugin_name),
    )
    with _MUTATION_LOCK:
        _MUTATIONS_IN_FLIGHT[key] = _MUTATIONS_IN_FLIGHT.get(key, 0) + 1
    return RemotePluginCacheMutationGuard(key)


def maybe_start_remote_installed_plugin_bundle_sync(
    codex_home: Path,
    config: Any,
    auth: Any | None,
    on_local_cache_changed: Callable[[], None] | None = None,
    *,
    fetch_installed: Callable[..., Awaitable[Any]] | None = None,
) -> asyncio.Task[None] | None:
    if auth is None:
        return None
    cache_root = _remote_plugin_cache_root(Path(codex_home))
    with _SYNC_LOCK:
        if cache_root in _SYNCS_IN_FLIGHT:
            return None
        _SYNCS_IN_FLIGHT.add(cache_root)

    async def run() -> None:
        try:
            outcome = await sync_remote_installed_plugin_bundles_once(
                Path(codex_home),
                config,
                auth,
                fetch_installed=fetch_installed,
            )
            if outcome.changed_local_cache() and on_local_cache_changed is not None:
                on_local_cache_changed()
        finally:
            with _SYNC_LOCK:
                _SYNCS_IN_FLIGHT.discard(cache_root)

    return asyncio.create_task(run())


async def sync_remote_installed_plugin_bundles_once(
    codex_home: Path,
    config: Any,
    auth: Any | None,
    *,
    fetch_installed: Callable[..., Awaitable[Any]] | None = None,
) -> RemoteInstalledPluginBundleSyncOutcome:
    from ..remote_bundle import (
        download_and_install_remote_plugin_bundle,
        validate_remote_plugin_bundle,
    )

    if auth is None:
        raise RemoteInstalledPluginBundleSyncError(
            "chatgpt authentication required for remote plugin catalog"
        )
    if fetch_installed is None:
        from . import fetch_installed_plugins_for_scope

        fetch_installed = fetch_installed_plugins_for_scope

    global_plugins, workspace_plugins = await asyncio.gather(
        fetch_installed(config, auth, RemotePluginScope.GLOBAL, True),
        fetch_installed(config, auth, RemotePluginScope.WORKSPACE, True),
    )
    installed_names: dict[str, set[str]] = {
        marketplace: set() for marketplace in _MARKETPLACES
    }
    installed_ids: set[str] = set()
    failed_ids: set[str] = set()
    store = PluginStore.try_new(Path(codex_home).resolve())

    for installed in [*global_plugins, *workspace_plugins]:
        plugin = _field(installed, "plugin", installed)
        remote_id = str(_field(plugin, "id", ""))
        name = str(_field(plugin, "name", ""))
        marketplace = _canonical_marketplace_name(plugin)
        installed_names.setdefault(marketplace, set()).add(name)
        try:
            plugin_id = PluginId.parse(f"{name}@{marketplace}")
        except PluginIdError:
            failed_ids.add(remote_id)
            continue

        release = _field(plugin, "release", {})
        version = _field(release, "version", None)
        if store.active_plugin_version(plugin_id) == _trimmed(version):
            continue
        try:
            bundle = validate_remote_plugin_bundle(
                remote_id,
                marketplace,
                name,
                version,
                _field(release, "bundle_download_url", None),
                _field(release, "app_manifest", None),
            )
            result = await download_and_install_remote_plugin_bundle(
                Path(codex_home).resolve(),
                bundle,
            )
            installed_ids.add(result.plugin_id.as_key())
        except Exception:
            failed_ids.add(remote_id)

    removed = await asyncio.to_thread(
        remove_stale_remote_plugin_caches,
        Path(codex_home),
        installed_names,
    )
    return RemoteInstalledPluginBundleSyncOutcome(
        installed_plugin_ids=sorted(installed_ids),
        removed_cache_plugin_ids=removed,
        failed_remote_plugin_ids=sorted(failed_ids),
    )


def remove_stale_remote_plugin_caches(
    codex_home: Path,
    installed_plugin_names_by_marketplace: Mapping[str, set[str]],
) -> list[str]:
    removed: list[str] = []
    for marketplace in _MARKETPLACES:
        root = _remote_plugin_cache_root(Path(codex_home)) / marketplace
        if not root.exists():
            continue
        installed = installed_plugin_names_by_marketplace.get(marketplace, set())
        for entry in root.iterdir():
            plugin_name = entry.name
            if plugin_name in installed or _is_cache_mutation_in_flight(
                codex_home,
                marketplace,
                plugin_name,
            ):
                continue
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()
            removed.append(f"{plugin_name}@{marketplace}")
    return sorted(removed)


def _is_cache_mutation_in_flight(
    codex_home: Path,
    marketplace_name: str,
    plugin_name: str,
) -> bool:
    key = (
        _remote_plugin_cache_root(Path(codex_home)),
        marketplace_name,
        plugin_name,
    )
    with _MUTATION_LOCK:
        return key in _MUTATIONS_IN_FLIGHT


def _remote_plugin_cache_root(codex_home: Path) -> Path:
    return (Path(codex_home) / PLUGINS_CACHE_DIR).resolve()


def _canonical_marketplace_name(plugin: Any) -> str:
    scope = _field(plugin, "scope", RemotePluginScope.GLOBAL)
    if not isinstance(scope, RemotePluginScope):
        scope = RemotePluginScope(str(getattr(scope, "value", scope)).upper())
    if scope is RemotePluginScope.GLOBAL:
        return REMOTE_GLOBAL_MARKETPLACE_NAME
    discoverability = str(
        getattr(_field(plugin, "discoverability", ""), "value", _field(plugin, "discoverability", ""))
    ).upper()
    if discoverability == "LISTED":
        return REMOTE_WORKSPACE_MARKETPLACE_NAME
    return REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _trimmed(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


__all__ = [
    "RemoteInstalledPluginBundleSyncError",
    "RemoteInstalledPluginBundleSyncOutcome",
    "RemotePluginCacheMutationGuard",
    "mark_remote_plugin_cache_mutation_in_flight",
    "maybe_start_remote_installed_plugin_bundle_sync",
    "remove_stale_remote_plugin_caches",
    "sync_remote_installed_plugin_bundles_once",
]
