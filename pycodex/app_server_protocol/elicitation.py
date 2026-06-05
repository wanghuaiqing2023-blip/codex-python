"""MCP elicitation protocol shapes ported from `codex-rs/app-server-protocol`."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

JsonValue = Any

@dataclass(frozen=True)
class McpElicitationSchema:
    schema_uri: str | None = None
    type_: str = "object"
    properties: Mapping[str, JsonValue] = field(default_factory=dict)
    required: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_uri",
            _optional_str(self.schema_uri, "schema_uri"),
        )
        object.__setattr__(self, "type_", _ensure_str(self.type_, "type_"))
        if not isinstance(self.properties, Mapping):
            raise TypeError("properties must be a mapping")
        object.__setattr__(self, "properties", copy.deepcopy(dict(self.properties)))
        if self.required is not None:
            object.__setattr__(self, "required", _string_tuple(self.required, "required"))

    @classmethod
    def empty_object(cls) -> "McpElicitationSchema":
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "type": self.type_,
            "properties": copy.deepcopy(dict(self.properties)),
        }
        if self.schema_uri is not None:
            data["$schema"] = self.schema_uri
        if self.required is not None:
            data["required"] = list(self.required)
        return data


@dataclass(frozen=True)
class McpServerElicitationRequest:
    mode: str
    message: str
    meta: JsonValue | None = None
    requested_schema: McpElicitationSchema | None = None
    url: str | None = None
    elicitation_id: str | None = None

    @classmethod
    def form(
        cls,
        message: str,
        requested_schema: McpElicitationSchema,
        meta: JsonValue | None = None,
    ) -> "McpServerElicitationRequest":
        return cls(
            mode="form",
            message=message,
            requested_schema=requested_schema,
            meta=meta,
        )

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _ensure_str(self.mode, "mode"))
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))
        object.__setattr__(self, "url", _optional_str(self.url, "url"))
        object.__setattr__(self, "elicitation_id", _optional_str(self.elicitation_id, "elicitation_id"))
        if self.requested_schema is not None and not isinstance(self.requested_schema, McpElicitationSchema):
            raise TypeError("requested_schema must be McpElicitationSchema")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "mode": self.mode,
            "_meta": copy.deepcopy(self.meta),
            "message": self.message,
        }
        if self.mode == "form":
            if self.requested_schema is None:
                raise ValueError("form elicitation request requires requested_schema")
            data["requestedSchema"] = self.requested_schema.to_mapping()
        elif self.mode == "url":
            data["url"] = self.url
            data["elicitationId"] = self.elicitation_id
        else:
            raise ValueError(f"unknown elicitation request mode: {self.mode}")
        return data


@dataclass(frozen=True)
class McpServerElicitationRequestParams:
    thread_id: str
    turn_id: str | None
    server_name: str
    request: McpServerElicitationRequest

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _optional_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "server_name", _ensure_str(self.server_name, "server_name"))
        if not isinstance(self.request, McpServerElicitationRequest):
            raise TypeError("request must be McpServerElicitationRequest")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "serverName": self.server_name,
        }
        data.update(self.request.to_mapping())
        return data



def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _string_tuple(values: Iterable[JsonValue], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: list[str] = []
    for value in values:
        result.append(_ensure_str(value, field_name))
    return tuple(result)


__all__ = [
    "McpElicitationSchema",
    "McpServerElicitationRequest",
    "McpServerElicitationRequestParams",
]
