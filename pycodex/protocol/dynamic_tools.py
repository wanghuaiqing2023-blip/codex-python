"""Dynamic tool protocol types.

Ported from ``codex/codex-rs/protocol/src/dynamic_tools.rs``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any
I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


def _mapping(value: JsonValue, label: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_bool(value: Mapping[str, JsonValue], key: str) -> bool | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


@dataclass(frozen=True)
class DynamicToolSpec:
    name: str
    description: str
    input_schema: JsonValue
    namespace: str | None = None
    defer_loading: bool = False

    def __post_init__(self) -> None:
        if self.namespace is not None and not isinstance(self.namespace, str):
            raise TypeError("namespace must be a string or None")
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if not isinstance(self.defer_loading, bool):
            raise TypeError("defer_loading must be a bool")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "DynamicToolSpec":
        data = _mapping(value, "dynamic tool spec")
        defer_loading = _optional_bool(data, "deferLoading")
        if defer_loading is None:
            expose_to_context = _optional_bool(data, "exposeToContext")
            defer_loading = not expose_to_context if expose_to_context is not None else False
        return cls(
            namespace=_optional_str(data, "namespace"),
            name=_required_str(data, "name"),
            description=_required_str(data, "description"),
            input_schema=data["inputSchema"],
            defer_loading=defer_loading,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "deferLoading": self.defer_loading,
        }
        if self.namespace is not None:
            result["namespace"] = self.namespace
        return result


@dataclass(frozen=True)
class DynamicToolCallRequest:
    call_id: str
    turn_id: str
    tool: str
    arguments: JsonValue
    started_at_ms: int = 0
    namespace: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if isinstance(self.started_at_ms, bool) or not isinstance(self.started_at_ms, int):
            raise TypeError("started_at_ms must be an integer")
        if self.started_at_ms < I64_MIN or self.started_at_ms > I64_MAX:
            raise ValueError("started_at_ms must fit in i64")
        if self.namespace is not None and not isinstance(self.namespace, str):
            raise TypeError("namespace must be a string or None")
        if not isinstance(self.tool, str):
            raise TypeError("tool must be a string")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "DynamicToolCallRequest":
        data = _mapping(value, "dynamic tool call request")
        started_at_ms = data.get("startedAtMs", 0)
        if isinstance(started_at_ms, bool) or not isinstance(started_at_ms, int):
            raise TypeError("startedAtMs must be an integer")
        if started_at_ms < I64_MIN or started_at_ms > I64_MAX:
            raise ValueError("startedAtMs must fit in i64")
        return cls(
            call_id=_required_str(data, "callId"),
            turn_id=_required_str(data, "turnId"),
            started_at_ms=started_at_ms,
            namespace=_optional_str(data, "namespace"),
            tool=_required_str(data, "tool"),
            arguments=data["arguments"],
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "callId": self.call_id,
            "turnId": self.turn_id,
            "startedAtMs": self.started_at_ms,
            "namespace": self.namespace,
            "tool": self.tool,
            "arguments": self.arguments,
        }


@dataclass(frozen=True)
class DynamicToolCallOutputContentItem:
    type: str
    text: str | None = None
    image_url: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type == "inputText":
            if not isinstance(self.text, str):
                raise TypeError("inputText item requires text")
            if self.image_url is not None:
                raise ValueError("inputText item cannot include image_url")
        if self.type == "inputImage":
            if not isinstance(self.image_url, str):
                raise TypeError("inputImage item requires image_url")
            if self.text is not None:
                raise ValueError("inputImage item cannot include text")
        if self.type not in {"inputText", "inputImage"}:
            raise ValueError(f"unknown dynamic tool output content type: {self.type}")

    @classmethod
    def input_text(cls, text: str) -> "DynamicToolCallOutputContentItem":
        return cls("inputText", text=text)

    @classmethod
    def input_image(cls, image_url: str) -> "DynamicToolCallOutputContentItem":
        return cls("inputImage", image_url=image_url)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "DynamicToolCallOutputContentItem":
        data = _mapping(value, "dynamic tool output content item")
        item_type = _required_str(data, "type")
        if item_type == "inputText":
            return cls.input_text(_required_str(data, "text"))
        if item_type == "inputImage":
            return cls.input_image(_required_str(data, "imageUrl"))
        raise ValueError(f"unknown dynamic tool output content type: {item_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "inputText":
            return {"type": "inputText", "text": self.text}
        return {"type": "inputImage", "imageUrl": self.image_url}


@dataclass(frozen=True)
class DynamicToolResponse:
    content_items: tuple[DynamicToolCallOutputContentItem, ...]
    success: bool

    def __post_init__(self) -> None:
        if not isinstance(self.content_items, tuple):
            object.__setattr__(self, "content_items", tuple(self.content_items))
        if not all(isinstance(item, DynamicToolCallOutputContentItem) for item in self.content_items):
            raise TypeError("content_items entries must be DynamicToolCallOutputContentItem")
        if not isinstance(self.success, bool):
            raise TypeError("success must be a bool")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "DynamicToolResponse":
        data = _mapping(value, "dynamic tool response")
        raw_items = data["contentItems"]
        if not isinstance(raw_items, list | tuple):
            raise TypeError("contentItems must be a list")
        return cls(
            content_items=tuple(DynamicToolCallOutputContentItem.from_mapping(item) for item in raw_items),
            success=data["success"],
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "contentItems": [item.to_mapping() for item in self.content_items],
            "success": self.success,
        }
