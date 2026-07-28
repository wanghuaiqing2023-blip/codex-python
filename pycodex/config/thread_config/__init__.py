"""Thread-scoped config loading package ported from ``codex-config``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.app_server_protocol.config import ConfigLayerSource
from pycodex.config.state import ConfigLayerEntry

JsonValue = Any
@dataclass(frozen=True)
class ThreadConfigContext:
    thread_id: str | None = None
    cwd: Path | None = None

    def __post_init__(self) -> None:
        if self.thread_id is not None and not isinstance(self.thread_id, str):
            raise TypeError("thread_id must be a string or None")
        if self.cwd is not None:
            object.__setattr__(self, "cwd", Path(self.cwd))


@dataclass(frozen=True)
class SessionThreadConfig:
    model_provider: str | None = None
    model_providers: Mapping[str, Mapping[str, JsonValue] | Any] = field(default_factory=dict)
    features: Mapping[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.model_provider is not None and not isinstance(self.model_provider, str):
            raise TypeError("model_provider must be a string or None")
        if not isinstance(self.model_providers, Mapping):
            raise TypeError("model_providers must be a mapping")
        if not isinstance(self.features, Mapping):
            raise TypeError("features must be a mapping")
        features: dict[str, bool] = {}
        for key, value in self.features.items():
            if not isinstance(value, bool):
                raise TypeError("feature values must be bools")
            features[str(key)] = value
        object.__setattr__(self, "features", dict(sorted(features.items())))
        object.__setattr__(
            self,
            "model_providers",
            {str(key): _provider_to_mapping(value) for key, value in self.model_providers.items()},
        )


@dataclass(frozen=True)
class UserThreadConfig:
    pass


@dataclass(frozen=True)
class ThreadConfigSource:
    kind: str
    config: SessionThreadConfig | UserThreadConfig

    @classmethod
    def session(cls, config: SessionThreadConfig | Mapping[str, JsonValue]) -> "ThreadConfigSource":
        if not isinstance(config, SessionThreadConfig):
            config = SessionThreadConfig(**dict(config))
        return cls("session", config)

    @classmethod
    def user(cls, config: UserThreadConfig | None = None) -> "ThreadConfigSource":
        return cls("user", config or UserThreadConfig())

    def __post_init__(self) -> None:
        if self.kind not in {"session", "user"}:
            raise ValueError(f"unknown thread config source kind: {self.kind}")
        if self.kind == "session" and not isinstance(self.config, SessionThreadConfig):
            raise TypeError("session thread config source requires SessionThreadConfig")
        if self.kind == "user" and not isinstance(self.config, UserThreadConfig):
            raise TypeError("user thread config source requires UserThreadConfig")


class ThreadConfigLoadErrorCode(str, Enum):
    AUTH = "auth"
    TIMEOUT = "timeout"
    PARSE = "parse"
    REQUEST_FAILED = "request_failed"
    INTERNAL = "internal"


@dataclass(frozen=True)
class ThreadConfigLoadError(Exception):
    code_value: ThreadConfigLoadErrorCode
    message: str
    status_code_value: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.code_value, ThreadConfigLoadErrorCode):
            object.__setattr__(self, "code_value", ThreadConfigLoadErrorCode(str(self.code_value)))
        if self.status_code_value is not None and not isinstance(self.status_code_value, int):
            raise TypeError("status_code must be an int or None")

    @classmethod
    def new(
        cls,
        code: ThreadConfigLoadErrorCode | str,
        status_code: int | None,
        message: str,
    ) -> "ThreadConfigLoadError":
        error_code = code if isinstance(code, ThreadConfigLoadErrorCode) else ThreadConfigLoadErrorCode(str(code))
        return cls(error_code, str(message), status_code)

    def code(self) -> ThreadConfigLoadErrorCode:
        return self.code_value

    def status_code(self) -> int | None:
        return self.status_code_value

    def __str__(self) -> str:
        return self.message


class ThreadConfigLoader:
    async def load(self, context: ThreadConfigContext) -> list[ThreadConfigSource]:
        raise NotImplementedError

    async def load_config_layers(self, context: ThreadConfigContext) -> list[ConfigLayerEntry]:
        layers: list[ConfigLayerEntry] = []
        for source in await self.load(context):
            layer = thread_config_source_to_layer(source)
            if layer is not None:
                layers.append(layer)
        return layers


@dataclass(frozen=True)
class StaticThreadConfigLoader(ThreadConfigLoader):
    sources: tuple[ThreadConfigSource, ...] = ()

    @classmethod
    def new(cls, sources: Sequence[ThreadConfigSource]) -> "StaticThreadConfigLoader":
        return cls(tuple(sources))

    async def load(self, context: ThreadConfigContext) -> list[ThreadConfigSource]:
        return list(self.sources)


class NoopThreadConfigLoader(ThreadConfigLoader):
    async def load(self, context: ThreadConfigContext) -> list[ThreadConfigSource]:
        return []


def thread_config_source_to_layer(source: ThreadConfigSource) -> ConfigLayerEntry | None:
    if source.kind == "user":
        return None
    assert isinstance(source.config, SessionThreadConfig)
    config = session_thread_config_to_toml(source.config)
    if not config:
        return None
    return ConfigLayerEntry(ConfigLayerSource.session_flags(), config)


def session_thread_config_to_toml(config: SessionThreadConfig) -> dict[str, JsonValue]:
    table: dict[str, JsonValue] = {}
    if config.model_provider is not None:
        table["model_provider"] = config.model_provider
    if config.model_providers:
        table["model_providers"] = dict(config.model_providers)
    if config.features:
        table["features"] = dict(config.features)
    return table


def _provider_to_mapping(provider: Mapping[str, JsonValue] | Any) -> Mapping[str, JsonValue]:
    if isinstance(provider, Mapping):
        return dict(provider)
    to_mapping = getattr(provider, "to_mapping", None)
    if callable(to_mapping):
        mapped = to_mapping()
        if isinstance(mapped, Mapping):
            return dict(mapped)
    fields: dict[str, JsonValue] = {}
    for key in (
        "name",
        "base_url",
        "wire_api",
        "requires_openai_auth",
        "supports_websockets",
    ):
        if hasattr(provider, key):
            fields[key] = getattr(provider, key)
    return fields


from .remote import RemoteThreadConfigLoader


__all__ = [
    "NoopThreadConfigLoader",
    "RemoteThreadConfigLoader",
    "SessionThreadConfig",
    "StaticThreadConfigLoader",
    "ThreadConfigContext",
    "ThreadConfigLoadError",
    "ThreadConfigLoadErrorCode",
    "ThreadConfigLoader",
    "ThreadConfigSource",
    "UserThreadConfig",
    "session_thread_config_to_toml",
    "thread_config_source_to_layer",
]
