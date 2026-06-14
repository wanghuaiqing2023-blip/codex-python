"""Suite parity tests for ``codex-rs/core/tests/suite/models_etag_responses.rs``."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from pycodex.models_manager import CachedModelsManager, ModelsCache
from pycodex.models_manager.test_support import model_info_from_slug
from pycodex.protocol import ModelsResponse


ETAG_1 = '"models-etag-1"'
ETAG_2 = '"models-etag-2"'


class _RemoteModels:
    def __init__(self, *slugs: str, etag: str) -> None:
        self.slugs = slugs
        self.etag = etag
        self.calls = 0

    def fetch(self) -> tuple[ModelsResponse, str]:
        self.calls += 1
        return ModelsResponse(tuple(model_info_from_slug(slug) for slug in self.slugs)), self.etag


def test_refresh_models_on_models_etag_mismatch_and_avoid_duplicate_models_fetch(tmp_path) -> None:
    """Rust test: ``refresh_models_on_models_etag_mismatch_and_avoid_duplicate_models_fetch``."""

    now = datetime(2026, 6, 11, 1, tzinfo=timezone.utc)
    remote = _RemoteModels("remote-after-etag-refresh", etag=ETAG_2)
    manager = CachedModelsManager(
        tmp_path,
        remote.fetch,
        client_version="1.2.3-dev",
        ttl=timedelta(hours=24),
        clock=lambda: now,
    )
    manager.write_cache(
        ModelsCache(
            now,
            etag=ETAG_1,
            client_version="1.2.3",
            models=(model_info_from_slug("cached-before-etag-refresh"),),
        )
    )

    asyncio.run(manager.refresh_models_etag(ETAG_2))
    refreshed = manager.read_cache()

    assert refreshed is not None
    assert refreshed.etag == ETAG_2
    assert [model.slug for model in refreshed.models] == ["remote-after-etag-refresh"]
    assert remote.calls == 1

    asyncio.run(manager.refresh_models_etag(ETAG_2))

    assert remote.calls == 1
    offline = asyncio.run(manager.list_models("offline"))
    assert [preset.model for preset in offline] == ["remote-after-etag-refresh"]
