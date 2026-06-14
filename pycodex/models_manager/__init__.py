"""Python port of ``codex-models-manager`` top-level public API.

Rust source:
- ``codex/codex-rs/models-manager/src/lib.rs``
- ``codex/codex-rs/models-manager/src/config.rs``
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pycodex.protocol import ModelInfo, ModelPreset, ModelsResponse


@dataclass
class ModelsManagerConfig:
    model_context_window: int | None = None
    model_auto_compact_token_limit: int | None = None
    tool_output_token_limit: int | None = None
    base_instructions: str | None = None
    personality_enabled: bool = False
    model_supports_reasoning_summaries: bool | None = None
    model_catalog: dict[str, Any] | None = None


CACHE_FILE = "models_cache.json"


class RefreshStrategy(str, Enum):
    OFFLINE = "offline"
    ONLINE_IF_UNCACHED = "online_if_uncached"


@dataclass(frozen=True)
class ModelsCache:
    fetched_at: datetime
    etag: str | None = None
    client_version: str | None = None
    models: tuple[ModelInfo, ...] = ()

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ModelsCache":
        fetched_at = value.get("fetched_at")
        if not isinstance(fetched_at, str):
            raise TypeError("models cache fetched_at must be a string")
        models = tuple(_model_info_from_cache_item(item) for item in value.get("models", ()))
        return cls(
            fetched_at=_parse_cache_datetime(fetched_at),
            etag=value.get("etag") if isinstance(value.get("etag"), str) else None,
            client_version=value.get("client_version") if isinstance(value.get("client_version"), str) else None,
            models=models,
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "fetched_at": self.fetched_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "etag": self.etag,
            "client_version": self.client_version,
            "models": [{"slug": model.slug} for model in self.models],
        }

    def to_presets(self) -> list[ModelPreset]:
        return [ModelPreset.from_model_info(model) for model in sorted(self.models, key=lambda item: item.priority)]


class CachedModelsManager:
    """Small persistent models-cache manager aligned with Rust TTL/version rules."""

    def __init__(
        self,
        codex_home: str | Path,
        fetch_models: Callable[[], ModelsResponse | tuple[ModelsResponse, str | None]],
        *,
        client_version: str | None = None,
        ttl: timedelta = timedelta(hours=24),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.codex_home = Path(codex_home)
        self.fetch_models = fetch_models
        self.client_version = client_version_to_whole(client_version)
        self.ttl = ttl
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def cache_path(self) -> Path:
        return self.codex_home / CACHE_FILE

    def read_cache(self) -> ModelsCache | None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        return ModelsCache.from_mapping(data)

    def write_cache(self, cache: ModelsCache) -> None:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(cache.to_mapping(), indent=2), encoding="utf-8")

    async def list_models(self, refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED) -> list[ModelPreset]:
        strategy = _refresh_strategy_value(refresh_strategy)
        cache = self.read_cache()
        if strategy == RefreshStrategy.OFFLINE.value:
            return [] if cache is None else cache.to_presets()
        if cache is not None and self._cache_is_usable(cache):
            return cache.to_presets()
        cache = self._fetch_and_store()
        return cache.to_presets()

    async def refresh_models_etag(self, etag: str) -> None:
        if not isinstance(etag, str):
            raise TypeError("etag must be a string")
        cache = self.read_cache()
        if cache is not None and cache.etag == etag:
            self.write_cache(ModelsCache(self._now(), etag=cache.etag, client_version=self.client_version, models=cache.models))
            return
        self._fetch_and_store()

    def _cache_is_usable(self, cache: ModelsCache) -> bool:
        return cache.client_version == self.client_version and self._now() - cache.fetched_at <= self.ttl

    def _fetch_and_store(self) -> ModelsCache:
        response = self.fetch_models()
        etag = None
        if isinstance(response, tuple):
            response, etag = response
        if not isinstance(response, ModelsResponse):
            response = ModelsResponse.from_mapping(response)
        cache = ModelsCache(self._now(), etag=etag, client_version=self.client_version, models=response.models)
        self.write_cache(cache)
        return cache

    def _now(self) -> datetime:
        now = self.clock()
        return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def bundled_models_response() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    models_json = root / "codex" / "codex-rs" / "models-manager" / "models.json"
    return json.loads(models_json.read_text(encoding="utf-8"))


def client_version_to_whole(version: str | None = None) -> str:
    if version is None:
        return "0.0.0"
    parts = version.split("-", 1)[0].split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def _parse_cache_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _model_info_from_cache_item(value: Any) -> ModelInfo:
    if isinstance(value, ModelInfo):
        return value
    if isinstance(value, dict):
        if set(value) == {"slug"}:
            from .test_support import model_info_from_slug

            return model_info_from_slug(str(value["slug"]))
        return ModelInfo.from_mapping(value)
    if isinstance(value, str):
        from .test_support import model_info_from_slug

        return model_info_from_slug(value)
    raise TypeError("models cache entries must be ModelInfo, mapping, or slug")


def _refresh_strategy_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).lower()


from .test_support import (  # noqa: E402
    builtin_collaboration_mode_presets,
    construct_model_info_from_candidates,
    construct_model_info_offline_for_tests,
    get_model_offline_for_tests,
    model_info_from_slug,
    with_config_overrides,
)


__all__ = [
    "CACHE_FILE",
    "CachedModelsManager",
    "ModelsCache",
    "ModelsManagerConfig",
    "RefreshStrategy",
    "builtin_collaboration_mode_presets",
    "bundled_models_response",
    "client_version_to_whole",
    "construct_model_info_from_candidates",
    "construct_model_info_offline_for_tests",
    "get_model_offline_for_tests",
    "model_info_from_slug",
    "with_config_overrides",
]
