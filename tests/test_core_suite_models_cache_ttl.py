"""Suite parity tests for ``codex-rs/core/tests/suite/models_cache_ttl.rs``."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from pycodex.models_manager import CachedModelsManager, ModelsCache, RefreshStrategy, client_version_to_whole
from pycodex.models_manager.test_support import model_info_from_slug
from pycodex.protocol import ModelsResponse


ETAG = '"models-etag-ttl"'
REMOTE_MODEL = "codex-test-ttl"
VERSIONED_MODEL = "codex-test-versioned"
MISSING_VERSION_MODEL = "codex-test-missing-version"
DIFFERENT_VERSION_MODEL = "codex-test-different-version"


class _RemoteModels:
    def __init__(self, *slugs: str, etag: str | None = None) -> None:
        self.slugs = slugs
        self.etag = etag
        self.calls = 0

    def fetch(self) -> tuple[ModelsResponse, str | None]:
        self.calls += 1
        return ModelsResponse(tuple(model_info_from_slug(slug) for slug in self.slugs)), self.etag


def _manager(tmp_path, remote: _RemoteModels, *, now: datetime) -> CachedModelsManager:
    return CachedModelsManager(
        tmp_path,
        remote.fetch,
        client_version="1.2.3-dev",
        ttl=timedelta(hours=24),
        clock=lambda: now,
    )


def _models(manager: CachedModelsManager, strategy: RefreshStrategy = RefreshStrategy.ONLINE_IF_UNCACHED) -> list[str]:
    return [preset.model for preset in asyncio.run(manager.list_models(strategy))]


def test_renews_cache_ttl_on_matching_models_etag(tmp_path) -> None:
    """Rust test: ``renews_cache_ttl_on_matching_models_etag``."""

    initial_now = datetime(2026, 6, 11, 1, tzinfo=timezone.utc)
    remote = _RemoteModels(REMOTE_MODEL, etag=ETAG)
    manager = _manager(tmp_path, remote, now=initial_now)

    assert REMOTE_MODEL in _models(manager)
    cache = manager.read_cache()
    assert cache is not None
    stale_cache = ModelsCache(datetime(1970, 1, 1, tzinfo=timezone.utc), etag=cache.etag, client_version=cache.client_version, models=cache.models)
    manager.write_cache(stale_cache)

    renewed_now = datetime(2026, 6, 11, 2, tzinfo=timezone.utc)
    manager.clock = lambda: renewed_now
    asyncio.run(manager.refresh_models_etag(ETAG))

    refreshed = manager.read_cache()
    assert refreshed is not None
    assert refreshed.fetched_at == renewed_now
    assert remote.calls == 1
    assert REMOTE_MODEL in _models(manager, RefreshStrategy.OFFLINE)


def test_uses_cache_when_version_matches(tmp_path) -> None:
    """Rust test: ``uses_cache_when_version_matches``."""

    now = datetime(2026, 6, 11, 1, tzinfo=timezone.utc)
    remote = _RemoteModels("remote")
    manager = _manager(tmp_path, remote, now=now)
    manager.write_cache(
        ModelsCache(
            now,
            client_version=client_version_to_whole("1.2.3-dev"),
            models=(model_info_from_slug(VERSIONED_MODEL),),
        )
    )

    assert VERSIONED_MODEL in _models(manager)
    assert remote.calls == 0


def test_refreshes_when_cache_version_missing(tmp_path) -> None:
    """Rust test: ``refreshes_when_cache_version_missing``."""

    now = datetime(2026, 6, 11, 1, tzinfo=timezone.utc)
    remote = _RemoteModels("remote-missing")
    manager = _manager(tmp_path, remote, now=now)
    manager.write_cache(ModelsCache(now, client_version=None, models=(model_info_from_slug(MISSING_VERSION_MODEL),)))

    models = _models(manager)

    assert "remote-missing" in models
    assert MISSING_VERSION_MODEL not in models
    assert remote.calls == 1


def test_refreshes_when_cache_version_differs(tmp_path) -> None:
    """Rust test: ``refreshes_when_cache_version_differs``."""

    now = datetime(2026, 6, 11, 1, tzinfo=timezone.utc)
    remote = _RemoteModels("remote-different")
    manager = _manager(tmp_path, remote, now=now)
    manager.write_cache(
        ModelsCache(
            now,
            client_version=f"{client_version_to_whole('1.2.3-dev')}-diff",
            models=(model_info_from_slug(DIFFERENT_VERSION_MODEL),),
        )
    )

    models = _models(manager)

    assert "remote-different" in models
    assert DIFFERENT_VERSION_MODEL not in models
    assert remote.calls == 1
