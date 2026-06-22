"""Model manager orchestration ported from ``codex-models-manager::manager``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
import inspect
from typing import Any, Callable, Protocol, runtime_checkable

from pycodex.protocol import ModelInfo, ModelPreset, ModelVisibility, ModelsResponse

from .cache import (
    CACHE_FILE,
    ModelsCache,
    ModelsCacheManager,
    models_response_from_fetch_result,
)
from .collaboration_mode_presets import builtin_collaboration_mode_presets
from .config import ModelsManagerConfig
from .model_info import model_info_from_slug, with_config_overrides
from .model_presets import model_presets_from_models


DEFAULT_MODEL_CACHE_TTL = timedelta(seconds=300)
MODEL_CACHE_FILE = CACHE_FILE


class RefreshStrategy(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    ONLINE_IF_UNCACHED = "online_if_uncached"

    def __str__(self) -> str:
        return self.value


@runtime_checkable
class ModelsEndpointClient(Protocol):
    """Provider endpoint facade aligned with Rust ``ModelsEndpointClient``."""

    def has_command_auth(self) -> bool:
        ...

    def uses_codex_backend(self) -> bool:
        ...

    def list_models(self, client_version: str) -> ModelsResponse | tuple[Any, str | None]:
        ...


class CachedModelsManager:
    """Small cache-backed models manager aligned with Rust refresh semantics."""

    def __init__(
        self,
        codex_home: str | Path,
        fetch_models: Callable[[], ModelsResponse | tuple[ModelsResponse, str | None]],
        *,
        client_version: str | None = None,
        ttl: timedelta = DEFAULT_MODEL_CACHE_TTL,
        clock: Callable[[], datetime] | None = None,
        auth_manager: Any = None,
        has_command_auth: bool | Callable[[], bool] = True,
        uses_codex_backend: bool | Callable[[], bool] | None = None,
    ) -> None:
        self.codex_home = Path(codex_home)
        self.fetch_models = fetch_models
        self.client_version = client_version_to_whole(client_version)
        self.ttl = ttl
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.cache_manager = ModelsCacheManager(self.cache_path, self.ttl, clock=self.clock)
        self.remote_models: tuple[ModelInfo, ...] = tuple(load_remote_models_from_file())
        self.etag: str | None = None
        self.auth_manager = auth_manager
        self.has_command_auth = has_command_auth
        self.uses_codex_backend = uses_codex_backend

    @property
    def cache_path(self) -> Path:
        return self.codex_home / MODEL_CACHE_FILE

    def read_cache(self) -> ModelsCache | None:
        self._sync_cache_manager()
        return self.cache_manager.load()

    def write_cache(self, cache: ModelsCache) -> None:
        self._sync_cache_manager()
        self.cache_manager.save_internal(cache)

    async def list_models(self, refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED) -> list[ModelPreset]:
        catalog = await self.raw_model_catalog(refresh_strategy)
        return build_available_models(
            catalog.models,
            uses_codex_backend=current_auth_uses_codex_backend(self.auth_manager),
        )

    async def raw_model_catalog(self, refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED) -> ModelsResponse:
        await self.refresh_available_models(refresh_strategy)
        return ModelsResponse(self.get_remote_models())

    def get_remote_models(self) -> tuple[ModelInfo, ...]:
        return self.remote_models

    def try_get_remote_models(self) -> tuple[ModelInfo, ...]:
        return self.get_remote_models()

    def try_list_models(self) -> list[ModelPreset]:
        return build_available_models(
            self.get_remote_models(),
            uses_codex_backend=current_auth_uses_codex_backend(self.auth_manager),
        )

    def list_collaboration_modes(self):
        return builtin_collaboration_mode_presets()

    async def get_default_model(
        self,
        model: str | None = None,
        refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED,
    ) -> str:
        if model is not None:
            return str(model)
        return default_model_from_available(await self.list_models(refresh_strategy))

    async def get_model_info(self, model: str, config: ModelsManagerConfig | Any) -> ModelInfo:
        if not isinstance(config, ModelsManagerConfig):
            config = ModelsManagerConfig.from_mapping(getattr(config, "to_mapping", lambda: None)())
        return construct_model_info_from_candidates(str(model), self.get_remote_models(), config)

    async def refresh_models_etag(self, etag: str) -> None:
        await self.refresh_if_new_etag(etag)

    async def refresh_if_new_etag(self, etag: str) -> None:
        if not isinstance(etag, str):
            raise TypeError("etag must be a string")
        if self.etag is not None and self.etag == etag:
            self._sync_cache_manager()
            try:
                self.cache_manager.renew_cache_ttl()
            except OSError:
                return
            return
        await self.refresh_available_models(RefreshStrategy.ONLINE)

    async def refresh_available_models(self, refresh_strategy: Any) -> None:
        strategy = refresh_strategy_value(refresh_strategy)
        if not await self.should_refresh_models():
            if strategy in {RefreshStrategy.OFFLINE.value, RefreshStrategy.ONLINE_IF_UNCACHED.value}:
                self.try_load_cache()
            return
        if strategy == RefreshStrategy.OFFLINE.value:
            self.try_load_cache()
            return
        if strategy == RefreshStrategy.ONLINE_IF_UNCACHED.value and self.try_load_cache():
            return
        await self.fetch_and_update_models()

    async def should_refresh_models(self) -> bool:
        if self.uses_codex_backend is not None:
            uses_backend = await _resolve_bool(self.uses_codex_backend, default=False)
        else:
            uses_backend = current_auth_uses_codex_backend(self.auth_manager)
        return uses_backend or await _resolve_bool(self.has_command_auth, default=False)

    async def fetch_and_update_models(self) -> None:
        fetched = self.fetch_models()
        if inspect.isawaitable(fetched):
            fetched = await fetched
        response, etag = models_response_from_fetch_result(fetched)
        self.apply_remote_models(response.models)
        self.etag = etag
        self._sync_cache_manager()
        self.cache_manager.persist_cache(response.models, etag, self.client_version)

    def apply_remote_models(self, models: tuple[ModelInfo, ...] | list[ModelInfo]) -> None:
        remote_models = tuple(models)
        if (
            remote_models
            and any(model.visibility is ModelVisibility.LIST for model in remote_models)
            and is_chatgpt_auth_mode(self.auth_manager)
        ):
            self.remote_models = remote_models
            return

        merged = list(load_remote_models_from_file())
        for model in remote_models:
            existing = next((idx for idx, candidate in enumerate(merged) if candidate.slug == model.slug), None)
            if existing is None:
                merged.append(model)
            else:
                merged[existing] = model
        self.remote_models = tuple(merged)

    def try_load_cache(self) -> bool:
        self._sync_cache_manager()
        cache = self.cache_manager.load_fresh(self.client_version)
        if cache is None:
            return False
        self.apply_remote_models(cache.models)
        self.etag = cache.etag
        return True

    def _sync_cache_manager(self) -> None:
        self.cache_manager.cache_ttl = self.ttl
        self.cache_manager.clock = self.clock


class StaticModelsManager:
    """Authoritative in-process catalog manager."""

    def __init__(self, auth_manager: Any = None, model_catalog: ModelsResponse | dict[str, Any] | None = None) -> None:
        self.auth_manager = auth_manager
        if model_catalog is None:
            model_catalog = ModelsResponse()
        if not isinstance(model_catalog, ModelsResponse):
            model_catalog = ModelsResponse.from_mapping(model_catalog)
        self.model_catalog = model_catalog

    async def raw_model_catalog(self, _refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED) -> ModelsResponse:
        return self.model_catalog

    def get_remote_models(self) -> tuple[ModelInfo, ...]:
        return self.model_catalog.models

    def try_get_remote_models(self) -> tuple[ModelInfo, ...]:
        return self.get_remote_models()

    async def list_models(self, _refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED) -> list[ModelPreset]:
        return build_available_models(self.model_catalog.models, uses_codex_backend=current_auth_uses_codex_backend(self.auth_manager))

    def try_list_models(self) -> list[ModelPreset]:
        return build_available_models(self.model_catalog.models, uses_codex_backend=current_auth_uses_codex_backend(self.auth_manager))

    def list_collaboration_modes(self):
        return builtin_collaboration_mode_presets()

    async def get_default_model(
        self,
        model: str | None = None,
        refresh_strategy: Any = RefreshStrategy.ONLINE_IF_UNCACHED,
    ) -> str:
        if model is not None:
            return str(model)
        return default_model_from_available(await self.list_models(refresh_strategy))

    async def get_model_info(self, model: str, config: ModelsManagerConfig | Any) -> ModelInfo:
        if not isinstance(config, ModelsManagerConfig):
            config = ModelsManagerConfig.from_mapping(getattr(config, "to_mapping", lambda: None)())
        return construct_model_info_from_candidates(str(model), self.model_catalog.models, config)

    async def refresh_if_new_etag(self, _etag: str) -> None:
        return None

    async def refresh_models_etag(self, etag: str) -> None:
        await self.refresh_if_new_etag(etag)


class OpenAiModelsManager(CachedModelsManager):
    """Endpoint-backed manager matching the Rust ``OpenAiModelsManager`` constructor."""

    def __init__(
        self,
        codex_home: str | Path,
        endpoint_client: ModelsEndpointClient | Any,
        auth_manager: Any = None,
        *,
        client_version: str | None = None,
        ttl: timedelta = DEFAULT_MODEL_CACHE_TTL,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.endpoint_client = endpoint_client

        async def fetch_from_endpoint() -> Any:
            return await _endpoint_list_models(endpoint_client, self.client_version)

        super().__init__(
            codex_home,
            fetch_from_endpoint,
            client_version=client_version,
            ttl=ttl,
            clock=clock,
            auth_manager=auth_manager,
            has_command_auth=lambda: _endpoint_has_command_auth(endpoint_client),
            uses_codex_backend=lambda: _endpoint_uses_codex_backend(endpoint_client),
        )


def build_available_models(
    remote_models: list[ModelInfo] | tuple[ModelInfo, ...],
    *,
    uses_codex_backend: bool = False,
) -> list[ModelPreset]:
    presets = model_presets_from_models(tuple(remote_models))
    return ModelPreset.filter_by_auth(presets, chatgpt_mode=uses_codex_backend)


def default_model_from_available(available: list[ModelPreset] | tuple[ModelPreset, ...]) -> str:
    selected = next((model for model in available if model.is_default), None)
    if selected is None and available:
        selected = available[0]
    return "" if selected is None else selected.model


def load_remote_models_from_file() -> tuple[ModelInfo, ...]:
    from . import bundled_models_response

    return ModelsResponse.from_mapping(bundled_models_response()).models


def construct_model_info_from_candidates(
    model: str,
    candidates: list[ModelInfo] | tuple[ModelInfo, ...],
    config: ModelsManagerConfig,
) -> ModelInfo:
    remote = find_model_by_longest_prefix(model, candidates) or find_model_by_namespaced_suffix(model, candidates)
    if remote is not None:
        from dataclasses import replace

        model_info = replace(remote, slug=model, used_fallback_model_metadata=False)
    else:
        model_info = model_info_from_slug(model)
    return with_config_overrides(model_info, config)


def find_model_by_longest_prefix(
    model: str,
    candidates: list[ModelInfo] | tuple[ModelInfo, ...],
) -> ModelInfo | None:
    best: ModelInfo | None = None
    for candidate in candidates:
        if not model.startswith(candidate.slug):
            continue
        if best is None or len(candidate.slug) > len(best.slug):
            best = candidate
    return best


def find_model_by_namespaced_suffix(
    model: str,
    candidates: list[ModelInfo] | tuple[ModelInfo, ...],
) -> ModelInfo | None:
    parts = model.split("/", 1)
    if len(parts) != 2:
        return None
    namespace, suffix = parts
    if "/" in suffix:
        return None
    if not namespace or not all(character.isascii() and (character.isalnum() or character in "_-") for character in namespace):
        return None
    return find_model_by_longest_prefix(suffix, candidates)


def refresh_strategy_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    text = str(raw)
    if text == "OnlineIfUncached":
        return RefreshStrategy.ONLINE_IF_UNCACHED.value
    return text.lower()


def client_version_to_whole(version: str | None = None) -> str:
    if version is None:
        return "0.0.0"
    parts = version.split("-", 1)[0].split(".")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def current_auth_uses_codex_backend(auth_manager: Any) -> bool:
    if auth_manager is None:
        return False
    method = getattr(auth_manager, "current_auth_uses_codex_backend", None)
    if callable(method):
        return bool(method())
    method = getattr(auth_manager, "uses_codex_backend", None)
    if callable(method):
        return bool(method())
    auth_mode = getattr(auth_manager, "auth_mode", None)
    auth_mode = auth_mode() if callable(auth_mode) else auth_mode
    return _is_chatgpt_auth_mode_value(auth_mode)


def is_chatgpt_auth_mode(auth_manager: Any) -> bool:
    if auth_manager is None:
        return True
    auth_mode = getattr(auth_manager, "auth_mode", None)
    auth_mode = auth_mode() if callable(auth_mode) else auth_mode
    if auth_mode is not None:
        return _is_chatgpt_auth_mode_value(auth_mode)
    return current_auth_uses_codex_backend(auth_manager)


def _is_chatgpt_auth_mode_value(value: Any) -> bool:
    text = str(getattr(value, "value", value)).lower().replace("-", "_")
    return text in {"chatgpt", "chatgptauthtokens", "chatgpt_auth_tokens"}


async def _resolve_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    result = value() if callable(value) else value
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


def _endpoint_has_command_auth(endpoint_client: Any) -> bool:
    method = getattr(endpoint_client, "has_command_auth", None)
    if callable(method):
        return bool(method())
    return bool(method)


async def _endpoint_uses_codex_backend(endpoint_client: Any) -> bool:
    method = getattr(endpoint_client, "uses_codex_backend", None)
    if callable(method):
        result = method()
    else:
        result = method
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


async def _endpoint_list_models(endpoint_client: Any, client_version: str) -> Any:
    method = getattr(endpoint_client, "list_models")
    try:
        result = method(client_version)
    except TypeError:
        result = method()
    if inspect.isawaitable(result):
        result = await result
    if isinstance(result, tuple):
        models, etag = result
    else:
        models, etag = result, None
    if isinstance(models, ModelsResponse):
        return models, etag
    if isinstance(models, dict):
        return ModelsResponse.from_mapping(models), etag
    return ModelsResponse(tuple(_coerce_model_info(model) for model in models)), etag


def _coerce_model_info(value: Any) -> ModelInfo:
    if isinstance(value, ModelInfo):
        return value
    if isinstance(value, dict):
        return ModelInfo.from_mapping(value)
    raise TypeError("endpoint model entries must be ModelInfo or mapping")


__all__ = [
    "DEFAULT_MODEL_CACHE_TTL",
    "MODEL_CACHE_FILE",
    "CachedModelsManager",
    "ModelsEndpointClient",
    "OpenAiModelsManager",
    "RefreshStrategy",
    "StaticModelsManager",
    "build_available_models",
    "client_version_to_whole",
    "construct_model_info_from_candidates",
    "current_auth_uses_codex_backend",
    "default_model_from_available",
    "find_model_by_longest_prefix",
    "find_model_by_namespaced_suffix",
    "is_chatgpt_auth_mode",
    "load_remote_models_from_file",
    "refresh_strategy_value",
]
