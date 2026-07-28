from __future__ import annotations

from pathlib import Path


def _cached_plugin(home: Path, marketplace: str, name: str) -> Path:
    manifest = (
        home
        / "plugins"
        / "cache"
        / marketplace
        / name
        / "1.2.3"
        / ".codex-plugin"
        / "plugin.json"
    )
    manifest.parent.mkdir(parents=True)
    manifest.write_text(f'{{"name":"{name}"}}', encoding="utf-8")
    return manifest


def test_stale_cleanup_skips_nested_cache_mutation_guards(tmp_path: Path) -> None:
    from pycodex.core_plugins.remote import REMOTE_GLOBAL_MARKETPLACE_NAME
    from pycodex.core_plugins.remote.remote_installed_plugin_sync import (
        mark_remote_plugin_cache_mutation_in_flight,
        remove_stale_remote_plugin_caches,
    )

    manifest = _cached_plugin(tmp_path, REMOTE_GLOBAL_MARKETPLACE_NAME, "linear")
    installed = {REMOTE_GLOBAL_MARKETPLACE_NAME: set()}
    first = mark_remote_plugin_cache_mutation_in_flight(
        tmp_path,
        REMOTE_GLOBAL_MARKETPLACE_NAME,
        "linear",
    )
    second = mark_remote_plugin_cache_mutation_in_flight(
        tmp_path,
        REMOTE_GLOBAL_MARKETPLACE_NAME,
        "linear",
    )
    assert remove_stale_remote_plugin_caches(tmp_path, installed) == []
    first.close()
    assert remove_stale_remote_plugin_caches(tmp_path, installed) == []
    second.close()

    assert remove_stale_remote_plugin_caches(tmp_path, installed) == [
        "linear@openai-curated-remote"
    ]
    assert not manifest.exists()


def test_stale_cleanup_removes_old_share_bucket_and_keeps_canonical(
    tmp_path: Path,
) -> None:
    from pycodex.core_plugins.remote import (
        REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
    )
    from pycodex.core_plugins.remote.remote_installed_plugin_sync import (
        remove_stale_remote_plugin_caches,
    )

    stale = _cached_plugin(
        tmp_path,
        REMOTE_WORKSPACE_SHARED_WITH_ME_PRIVATE_MARKETPLACE_NAME,
        "private-plugin",
    )
    canonical = _cached_plugin(
        tmp_path,
        REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME,
        "shared-plugin",
    )
    installed = {
        REMOTE_WORKSPACE_SHARED_WITH_ME_MARKETPLACE_NAME: {"shared-plugin"},
    }

    assert remove_stale_remote_plugin_caches(tmp_path, installed) == [
        "private-plugin@workspace-shared-with-me-private"
    ]
    assert not stale.exists()
    assert canonical.is_file()


def test_sync_outcome_reports_cache_change() -> None:
    from pycodex.core_plugins.remote.remote_installed_plugin_sync import (
        RemoteInstalledPluginBundleSyncOutcome,
    )

    assert not RemoteInstalledPluginBundleSyncOutcome().changed_local_cache()
    assert RemoteInstalledPluginBundleSyncOutcome(
        installed_plugin_ids=["a@market"]
    ).changed_local_cache()
    assert RemoteInstalledPluginBundleSyncOutcome(
        removed_cache_plugin_ids=["a@market"]
    ).changed_local_cache()
