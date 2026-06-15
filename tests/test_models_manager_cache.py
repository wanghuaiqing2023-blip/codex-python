from datetime import datetime, timedelta, timezone

import pytest

from pycodex.models_manager import ModelsCache, ModelsCacheManager
from pycodex.models_manager.cache import format_cache_datetime, parse_cache_datetime
from pycodex.models_manager.model_info import model_info_from_slug


def test_models_cache_round_trips_timestamp_and_legacy_slug_entries() -> None:
    # Rust crate/module: codex-models-manager::cache
    now = datetime(2026, 6, 14, 18, tzinfo=timezone.utc)
    cache = ModelsCache(now, etag='"etag"', client_version="1.2.3", models=(model_info_from_slug("cached"),))

    round_tripped = ModelsCache.from_mapping(cache.to_mapping())

    assert round_tripped.fetched_at == now
    assert round_tripped.etag == '"etag"'
    assert round_tripped.client_version == "1.2.3"
    assert [model.slug for model in round_tripped.models] == ["cached"]
    assert format_cache_datetime(now) == "2026-06-14T18:00:00Z"
    assert parse_cache_datetime("2026-06-14T18:00:00Z") == now


def test_load_fresh_returns_none_for_missing_cache(tmp_path) -> None:
    manager = ModelsCacheManager(tmp_path / "missing" / "models_cache.json", timedelta(hours=24))

    assert manager.load_fresh("1.2.3") is None


def test_load_fresh_rejects_version_mismatch_and_stale_cache(tmp_path) -> None:
    now = datetime(2026, 6, 14, 18, tzinfo=timezone.utc)
    manager = ModelsCacheManager(tmp_path / "models_cache.json", timedelta(hours=24), clock=lambda: now)
    manager.persist_cache((model_info_from_slug("cached"),), None, "1.2.3")

    assert manager.load_fresh("1.2.3") is not None
    assert manager.load_fresh("1.2.4") is None

    stale = ModelsCache(now - timedelta(days=2), client_version="1.2.3", models=(model_info_from_slug("old"),))
    manager.save_internal(stale)

    assert manager.load_fresh("1.2.3") is None


def test_load_fresh_rejects_zero_ttl(tmp_path) -> None:
    now = datetime(2026, 6, 14, 18, tzinfo=timezone.utc)
    manager = ModelsCacheManager(tmp_path / "models_cache.json", timedelta(0), clock=lambda: now)
    manager.persist_cache((model_info_from_slug("cached"),), None, "1.2.3")

    assert manager.load_fresh("1.2.3") is None


def test_persist_cache_creates_parent_dirs_and_renew_updates_timestamp(tmp_path) -> None:
    first_now = datetime(2026, 6, 14, 18, tzinfo=timezone.utc)
    second_now = datetime(2026, 6, 14, 19, tzinfo=timezone.utc)
    current = {"now": first_now}
    manager = ModelsCacheManager(
        tmp_path / "nested" / "models_cache.json",
        timedelta(hours=24),
        clock=lambda: current["now"],
    )

    manager.persist_cache((model_info_from_slug("cached"),), '"etag"', "1.2.3")
    current["now"] = second_now
    manager.renew_cache_ttl()

    cache = manager.load()
    assert cache is not None
    assert cache.fetched_at == second_now
    assert cache.etag == '"etag"'
    assert [model.slug for model in cache.models] == ["cached"]


def test_renew_cache_ttl_requires_existing_cache(tmp_path) -> None:
    manager = ModelsCacheManager(tmp_path / "models_cache.json", timedelta(hours=24))

    with pytest.raises(FileNotFoundError):
        manager.renew_cache_ttl()


def test_invalid_cache_json_surfaces_as_load_error(tmp_path) -> None:
    cache_path = tmp_path / "models_cache.json"
    cache_path.write_text("{not-json", encoding="utf-8")
    manager = ModelsCacheManager(cache_path, timedelta(hours=24))

    with pytest.raises(OSError):
        manager.load()
    assert manager.load_fresh("1.2.3") is None
