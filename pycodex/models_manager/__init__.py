"""Python port of ``codex-models-manager`` top-level public API.

Rust source:
- ``codex/codex-rs/models-manager/src/lib.rs``
- ``codex/codex-rs/models-manager/src/config.rs``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pycodex.protocol import ModelPreset, ModelsResponse

from .cache import (
    CACHE_FILE,
    ModelsCache,
    ModelsCacheManager,
    models_response_from_fetch_result,
)
from .collaboration_mode_presets import (
    KNOWN_MODE_NAMES_TEMPLATE_KEY,
    builtin_collaboration_mode_presets,
    default_mode_instructions,
    format_mode_names,
)
from .config import ModelsManagerConfig
from .model_presets import (
    HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG,
    HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG,
    model_presets_from_models,
)

class RefreshStrategy(str, Enum):
    OFFLINE = "offline"
    ONLINE_IF_UNCACHED = "online_if_uncached"


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
        self.cache_manager = ModelsCacheManager(self.cache_path, self.ttl, clock=self.clock)

    @property
    def cache_path(self) -> Path:
        return self.codex_home / CACHE_FILE

    def read_cache(self) -> ModelsCache | None:
        self._sync_cache_manager()
        return self.cache_manager.load()

    def write_cache(self, cache: ModelsCache) -> None:
        self._sync_cache_manager()
        self.cache_manager.save_internal(cache)

    async def list_models(self, refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED) -> list[ModelPreset]:
        strategy = _refresh_strategy_value(refresh_strategy)
        cache = self.read_cache()
        if strategy == RefreshStrategy.OFFLINE.value:
            return [] if cache is None else cache.to_presets()
        self._sync_cache_manager()
        fresh = self.cache_manager.load_fresh(self.client_version)
        if fresh is not None:
            return fresh.to_presets()
        cache = self._fetch_and_store()
        return cache.to_presets()

    async def refresh_models_etag(self, etag: str) -> None:
        if not isinstance(etag, str):
            raise TypeError("etag must be a string")
        cache = self.read_cache()
        if cache is not None and cache.etag == etag:
            self._sync_cache_manager()
            self.cache_manager.renew_cache_ttl()
            return
        self._fetch_and_store()

    def _cache_is_usable(self, cache: ModelsCache) -> bool:
        return cache.client_version == self.client_version and cache.is_fresh(self.ttl, now=self._now())

    def _fetch_and_store(self) -> ModelsCache:
        response, etag = models_response_from_fetch_result(self.fetch_models())
        self._sync_cache_manager()
        self.cache_manager.persist_cache(response.models, etag, self.client_version)
        cache = self.cache_manager.load()
        if cache is None:
            raise FileNotFoundError("cache not found after persist")
        return cache

    def _now(self) -> datetime:
        now = self.clock()
        return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)

    def _sync_cache_manager(self) -> None:
        self.cache_manager.cache_ttl = self.ttl
        self.cache_manager.clock = self.clock


def bundled_models_response() -> dict[str, Any]:
    import json

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


def _refresh_strategy_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).lower()


from .model_info import (  # noqa: E402
    BASE_INSTRUCTIONS,
    DEFAULT_PERSONALITY_HEADER,
    LOCAL_FRIENDLY_TEMPLATE,
    LOCAL_PRAGMATIC_TEMPLATE,
    PERSONALITY_PLACEHOLDER,
    local_personality_messages_for_slug,
    model_info_from_slug,
    with_config_overrides,
)
from .manager import (  # noqa: E402
    DEFAULT_MODEL_CACHE_TTL,
    MODEL_CACHE_FILE,
    CachedModelsManager,
    ModelsEndpointClient,
    OpenAiModelsManager,
    RefreshStrategy,
    StaticModelsManager,
    build_available_models,
    construct_model_info_from_candidates,
    current_auth_uses_codex_backend,
    default_model_from_available,
    find_model_by_longest_prefix,
    find_model_by_namespaced_suffix,
    is_chatgpt_auth_mode,
    load_remote_models_from_file,
)
from .test_support import (  # noqa: E402
    construct_model_info_offline_for_tests,
    get_model_offline_for_tests,
)


__all__ = [
    "BASE_INSTRUCTIONS",
    "CACHE_FILE",
    "CachedModelsManager",
    "DEFAULT_MODEL_CACHE_TTL",
    "DEFAULT_PERSONALITY_HEADER",
    "HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG",
    "HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG",
    "KNOWN_MODE_NAMES_TEMPLATE_KEY",
    "LOCAL_FRIENDLY_TEMPLATE",
    "LOCAL_PRAGMATIC_TEMPLATE",
    "ModelsCache",
    "ModelsCacheManager",
    "ModelsManagerConfig",
    "MODEL_CACHE_FILE",
    "ModelsEndpointClient",
    "PERSONALITY_PLACEHOLDER",
    "OpenAiModelsManager",
    "RefreshStrategy",
    "StaticModelsManager",
    "builtin_collaboration_mode_presets",
    "build_available_models",
    "bundled_models_response",
    "client_version_to_whole",
    "construct_model_info_from_candidates",
    "construct_model_info_offline_for_tests",
    "current_auth_uses_codex_backend",
    "default_mode_instructions",
    "default_model_from_available",
    "find_model_by_longest_prefix",
    "find_model_by_namespaced_suffix",
    "format_mode_names",
    "get_model_offline_for_tests",
    "is_chatgpt_auth_mode",
    "load_remote_models_from_file",
    "local_personality_messages_for_slug",
    "model_info_from_slug",
    "model_presets_from_models",
    "with_config_overrides",
]
