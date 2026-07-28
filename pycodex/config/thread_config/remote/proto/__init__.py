"""Generated thread-config protobuf message equivalents."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any


class _ProtoMessage:
    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LoadThreadConfigRequest(_ProtoMessage):
    thread_id: str | None = None
    cwd: str | None = None


@dataclass
class LoadThreadConfigResponse(_ProtoMessage):
    sources: list["ThreadConfigSource"] = field(default_factory=list)


@dataclass
class ThreadConfigSource(_ProtoMessage):
    source: Any | None = None


@dataclass
class SessionThreadConfig(_ProtoMessage):
    model_provider: str | None = None
    model_providers: list["ModelProvider"] = field(default_factory=list)
    features: dict[str, bool] = field(default_factory=dict)


@dataclass
class UserThreadConfig(_ProtoMessage):
    pass


@dataclass
class StringMap(_ProtoMessage):
    values: dict[str, str] = field(default_factory=dict)


@dataclass
class ModelProviderAuthInfo(_ProtoMessage):
    command: str = ""
    args: list[str] = field(default_factory=list)
    timeout_ms: int = 0
    refresh_interval_ms: int = 0
    cwd: str = ""


@dataclass
class ModelProvider(_ProtoMessage):
    id: str = ""
    name: str = ""
    base_url: str | None = None
    env_key: str | None = None
    env_key_instructions: str | None = None
    experimental_bearer_token: str | None = None
    auth: ModelProviderAuthInfo | None = None
    wire_api: int = 0
    query_params: StringMap | None = None
    http_headers: StringMap | None = None
    env_http_headers: StringMap | None = None
    request_max_retries: int | None = None
    stream_max_retries: int | None = None
    stream_idle_timeout_ms: int | None = None
    websocket_connect_timeout_ms: int | None = None
    requires_openai_auth: bool = False
    supports_websockets: bool = False


class WireApi(IntEnum):
    UNSPECIFIED = 0
    RESPONSES = 1

    def as_str_name(self) -> str:
        if self is WireApi.UNSPECIFIED:
            return "WIRE_API_UNSPECIFIED"
        return "WIRE_API_RESPONSES"

    @classmethod
    def from_str_name(cls, value: str) -> "WireApi | None":
        return {
            "WIRE_API_UNSPECIFIED": cls.UNSPECIFIED,
            "WIRE_API_RESPONSES": cls.RESPONSES,
        }.get(value)


__all__ = [
    "LoadThreadConfigRequest",
    "LoadThreadConfigResponse",
    "ModelProvider",
    "ModelProviderAuthInfo",
    "SessionThreadConfig",
    "StringMap",
    "ThreadConfigSource",
    "UserThreadConfig",
    "WireApi",
]
