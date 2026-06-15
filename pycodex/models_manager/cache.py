"""Disk cache helpers ported from ``codex-models-manager::cache``."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from pycodex.protocol import ModelInfo, ModelPreset, ModelsResponse

from .model_info import model_info_from_slug
from .model_presets import model_presets_from_models


CACHE_FILE = "models_cache.json"


@dataclass(frozen=True)
class ModelsCache:
    fetched_at: datetime
    etag: str | None = None
    client_version: str | None = None
    models: tuple[ModelInfo, ...] = ()

    def __post_init__(self) -> None:
        fetched_at = self.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        object.__setattr__(self, "fetched_at", fetched_at)
        object.__setattr__(self, "models", tuple(self.models))

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "ModelsCache":
        if not isinstance(value, dict):
            raise TypeError("models cache must be a mapping")
        fetched_at = value.get("fetched_at")
        if not isinstance(fetched_at, str):
            raise TypeError("models cache fetched_at must be a string")
        models = tuple(_model_info_from_cache_item(item) for item in value.get("models", ()))
        etag = value.get("etag")
        client_version = value.get("client_version")
        return cls(
            fetched_at=parse_cache_datetime(fetched_at),
            etag=etag if isinstance(etag, str) else None,
            client_version=client_version if isinstance(client_version, str) else None,
            models=models,
        )

    def to_mapping(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "fetched_at": format_cache_datetime(self.fetched_at),
            "models": [_json_compatible(model) for model in self.models],
        }
        if self.etag is not None:
            data["etag"] = self.etag
        if self.client_version is not None:
            data["client_version"] = self.client_version
        return data

    def is_fresh(self, ttl: timedelta, *, now: datetime | None = None) -> bool:
        if ttl <= timedelta(0):
            return False
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        return current - self.fetched_at <= ttl

    def to_presets(self) -> list[ModelPreset]:
        return model_presets_from_models(self.models)


class ModelsCacheManager:
    def __init__(
        self,
        cache_path: str | Path,
        cache_ttl: timedelta,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.cache_path = Path(cache_path)
        self.cache_ttl = cache_ttl
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def load_fresh(self, expected_version: str) -> ModelsCache | None:
        try:
            cache = self.load()
        except OSError:
            return None
        if cache is None:
            return None
        if cache.client_version != expected_version:
            return None
        if not cache.is_fresh(self.cache_ttl, now=self._now()):
            return None
        return cache

    def persist_cache(
        self,
        models: list[ModelInfo] | tuple[ModelInfo, ...],
        etag: str | None,
        client_version: str,
    ) -> None:
        cache = ModelsCache(
            fetched_at=self._now(),
            etag=etag,
            client_version=client_version,
            models=tuple(models),
        )
        self.save_internal(cache)

    def renew_cache_ttl(self) -> None:
        cache = self.load()
        if cache is None:
            raise FileNotFoundError("cache not found")
        self.save_internal(
            ModelsCache(
                fetched_at=self._now(),
                etag=cache.etag,
                client_version=cache.client_version,
                models=cache.models,
            )
        )

    def load(self) -> ModelsCache | None:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise OSError(str(exc)) from exc
        return ModelsCache.from_mapping(data)

    def save_internal(self, cache: ModelsCache) -> None:
        if self.cache_path.parent:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(cache.to_mapping(), indent=2), encoding="utf-8")

    def mutate_cache_for_test(self, mutate: Callable[[ModelsCache], ModelsCache]) -> None:
        cache = self.load()
        if cache is None:
            raise FileNotFoundError("cache not found")
        self.save_internal(mutate(cache))

    def _now(self) -> datetime:
        now = self.clock()
        return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def parse_cache_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def format_cache_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _model_info_from_cache_item(value: Any) -> ModelInfo:
    if isinstance(value, ModelInfo):
        return value
    if isinstance(value, dict):
        if set(value) == {"slug"}:
            return model_info_from_slug(str(value["slug"]))
        return ModelInfo.from_mapping(value)
    if isinstance(value, str):
        return model_info_from_slug(value)
    raise TypeError("models cache entries must be ModelInfo, mapping, or slug")


def _json_compatible(value: Any) -> Any:
    if is_dataclass(value):
        return _json_compatible(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items() if item is not None}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


def models_response_from_fetch_result(value: Any) -> tuple[ModelsResponse, str | None]:
    etag = None
    response = value
    if isinstance(value, tuple):
        response, etag = value
    if not isinstance(response, ModelsResponse):
        response = ModelsResponse.from_mapping(response)
    return response, etag


__all__ = [
    "CACHE_FILE",
    "ModelsCache",
    "ModelsCacheManager",
    "format_cache_datetime",
    "models_response_from_fetch_result",
    "parse_cache_datetime",
]
