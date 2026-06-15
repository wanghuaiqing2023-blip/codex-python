"""Thread-scoped config loading helpers ported from ``codex-config``."""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.network_proxy import ConfigLayerEntry, ConfigLayerSource

JsonValue = Any
REMOTE_THREAD_CONFIG_LOAD_TIMEOUT_SECONDS = 5


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


@dataclass(frozen=True)
class RemoteThreadConfigLoader(ThreadConfigLoader):
    endpoint: str
    client: Any = None

    @classmethod
    def new(cls, endpoint: str, client: Any = None) -> "RemoteThreadConfigLoader":
        return cls(str(endpoint), client)

    async def load(self, context: ThreadConfigContext) -> list[ThreadConfigSource]:
        if self.client is not None:
            request = load_thread_config_request(context)
            response = self.client(request)
            if inspect.isawaitable(response):
                response = await response
            return [
                thread_config_source_from_proto(source)
                for source in _response_sources(response)
            ]
        raise ThreadConfigLoadError.new(
            ThreadConfigLoadErrorCode.REQUEST_FAILED,
            None,
            "remote thread config loading is not implemented in pycodex",
        )


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


def load_thread_config_request(context: ThreadConfigContext) -> dict[str, JsonValue]:
    if not isinstance(context, ThreadConfigContext):
        raise TypeError("context must be ThreadConfigContext")
    return {
        "thread_id": context.thread_id,
        "cwd": None if context.cwd is None else str(context.cwd),
        "timeout_seconds": REMOTE_THREAD_CONFIG_LOAD_TIMEOUT_SECONDS,
        "grpc_timeout": "5000000u",
    }


def remote_status_to_error(status: Any) -> ThreadConfigLoadError:
    code = _status_code(status)
    error_code = (
        ThreadConfigLoadErrorCode.AUTH
        if code in {"unauthenticated", "permission_denied"}
        else ThreadConfigLoadErrorCode.TIMEOUT
        if code == "deadline_exceeded"
        else ThreadConfigLoadErrorCode.REQUEST_FAILED
    )
    return ThreadConfigLoadError.new(
        error_code,
        None,
        f"remote thread config request failed: {status}",
    )


def thread_config_source_from_proto(source: Mapping[str, JsonValue] | Any) -> ThreadConfigSource:
    payload = _as_mapping(source, "thread config source")
    if "session" in payload:
        return ThreadConfigSource.session(session_thread_config_from_proto(payload["session"]))
    if "user" in payload:
        return ThreadConfigSource.user(UserThreadConfig())
    kind = payload.get("source")
    if kind == "session":
        return ThreadConfigSource.session(session_thread_config_from_proto(payload.get("config", {})))
    if kind == "user":
        return ThreadConfigSource.user(UserThreadConfig())
    raise _parse_error("remote thread config omitted source payload")


def session_thread_config_from_proto(config: Mapping[str, JsonValue] | Any) -> SessionThreadConfig:
    payload = _as_mapping(config, "session thread config")
    providers = payload.get("model_providers", ())
    if isinstance(providers, Mapping):
        provider_items = providers.items()
    elif isinstance(providers, Sequence) and not isinstance(providers, (str, bytes)):
        provider_items = (model_provider_from_proto(provider) for provider in providers)
        model_providers = {provider_id: provider for provider_id, provider in provider_items}
        return SessionThreadConfig(
            model_provider=_optional_string(payload.get("model_provider"), "model_provider"),
            model_providers=model_providers,
            features=_bool_mapping(payload.get("features", {}), "features"),
        )
    else:
        raise _parse_error("remote thread config returned invalid model_providers")
    return SessionThreadConfig(
        model_provider=_optional_string(payload.get("model_provider"), "model_provider"),
        model_providers={
            str(provider_id): _provider_to_mapping(provider)
            for provider_id, provider in provider_items
        },
        features=_bool_mapping(payload.get("features", {}), "features"),
    )


def model_provider_from_proto(provider: Mapping[str, JsonValue] | Any) -> tuple[str, Mapping[str, JsonValue]]:
    payload = _as_mapping(provider, "model provider")
    provider_id = payload.get("id")
    if not isinstance(provider_id, str) or not provider_id:
        raise _parse_error("remote thread config returned model provider without an id")
    wire_api = payload.get("wire_api")
    if wire_api in {None, "", "unspecified", 0}:
        raise _parse_error("remote thread config omitted wire_api")
    if wire_api not in {"responses", "Responses", 1}:
        raise _parse_error(f"remote thread config returned unknown wire_api: {wire_api}")
    info: dict[str, JsonValue] = {}
    for key in (
        "name",
        "base_url",
        "env_key",
        "env_key_instructions",
        "experimental_bearer_token",
        "query_params",
        "http_headers",
        "env_http_headers",
        "request_max_retries",
        "stream_max_retries",
        "stream_idle_timeout_ms",
        "websocket_connect_timeout_ms",
        "requires_openai_auth",
        "supports_websockets",
    ):
        if key in payload:
            info[key] = payload[key]
    info["wire_api"] = "responses"
    if "auth" in payload and payload["auth"] is not None:
        info["auth"] = model_provider_auth_from_proto(payload["auth"])
    if "name" not in info:
        info["name"] = provider_id
    return provider_id, info


def model_provider_auth_from_proto(auth: Mapping[str, JsonValue] | Any) -> dict[str, JsonValue]:
    payload = _as_mapping(auth, "model provider auth")
    timeout_ms = payload.get("timeout_ms")
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms == 0:
        raise _parse_error("remote thread config returned zero auth timeout_ms")
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not Path(cwd).is_absolute():
        raise _parse_error(f"remote thread config returned invalid auth cwd {cwd!r}")
    return {
        "command": _required_string(payload.get("command"), "command"),
        "args": list(_string_sequence(payload.get("args", ()), "args")),
        "timeout_ms": timeout_ms,
        "refresh_interval_ms": payload.get("refresh_interval_ms"),
        "cwd": cwd,
    }


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


def _response_sources(response: Any) -> Sequence[Any]:
    payload = _as_mapping(response, "remote thread config response")
    sources = payload.get("sources", ())
    if isinstance(sources, str) or not isinstance(sources, Sequence):
        raise _parse_error("remote thread config returned invalid sources")
    return sources


def _status_code(status: Any) -> str:
    code = status() if callable(status) else getattr(status, "code", None)
    if callable(code):
        code = code()
    if code is None and isinstance(status, Mapping):
        code = status.get("code")
    text = str(code if code is not None else status).rsplit(".", 1)[-1].replace("-", "_")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def _as_mapping(value: Mapping[str, JsonValue] | Any, label: str) -> Mapping[str, JsonValue]:
    if isinstance(value, Mapping):
        return value
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        mapped = to_mapping()
        if isinstance(mapped, Mapping):
            return mapped
    if hasattr(value, "__dict__"):
        return vars(value)
    raise _parse_error(f"{label} must be a mapping")


def _parse_error(message: str) -> ThreadConfigLoadError:
    return ThreadConfigLoadError.new(ThreadConfigLoadErrorCode.PARSE, None, message)


def _optional_string(value: JsonValue, label: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, label)


def _required_string(value: JsonValue, label: str) -> str:
    if not isinstance(value, str):
        raise _parse_error(f"{label} must be a string")
    return value


def _string_sequence(value: JsonValue, label: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise _parse_error(f"{label} must be a sequence of strings")
    if not all(isinstance(item, str) for item in value):
        raise _parse_error(f"{label} must be a sequence of strings")
    return tuple(value)


def _bool_mapping(value: JsonValue, label: str) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        raise _parse_error(f"{label} must be a mapping")
    result: dict[str, bool] = {}
    for key, item in value.items():
        if not isinstance(item, bool):
            raise _parse_error(f"{label} values must be bools")
        result[str(key)] = item
    return dict(sorted(result.items()))


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
    "load_thread_config_request",
    "model_provider_auth_from_proto",
    "model_provider_from_proto",
    "remote_status_to_error",
    "session_thread_config_from_proto",
    "thread_config_source_from_proto",
    "thread_config_source_to_layer",
]
