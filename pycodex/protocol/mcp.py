"""Model Context Protocol values embedded in the Codex protocol.

Ported from ``codex/codex-rs/protocol/src/mcp.rs``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any

_I64_MIN = -(2**63)
_I64_MAX = 2**63 - 1


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


def _ensure_optional_str(raw: JsonValue, key: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    return _ensure_optional_str(value.get(key), key)


def _alias(value: Mapping[str, JsonValue], primary: str, alternate: str, default: JsonValue = None) -> JsonValue:
    if primary in value:
        return value[primary]
    if alternate in value:
        return value[alternate]
    return default


def _optional_icons(value: JsonValue) -> tuple[JsonValue, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list | tuple):
        raise TypeError("icons must be a list")
    return tuple(value)


def _optional_i64_lossy(value: JsonValue) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("size must be a number")
    if isinstance(value, int):
        return value if _I64_MIN <= value <= _I64_MAX else None
    if isinstance(value, float):
        return None
    raise TypeError("size must be a number")


def _ensure_i64(value: JsonValue, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if not _I64_MIN <= value <= _I64_MAX:
        raise ValueError(f"{label} must fit in i64")
    return value


def _put_optional(result: dict[str, JsonValue], key: str, value: JsonValue) -> None:
    if value is not None:
        result[key] = value


@dataclass(frozen=True)
class RequestId:
    """MCP request id, serialized as either a string or an integer."""

    value: str | int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, str | int):
            raise TypeError("request id must be a string or integer")
        if isinstance(self.value, int):
            _ensure_i64(self.value, "request id")

    @classmethod
    def from_value(cls, value: "RequestId | str | int") -> "RequestId":
        if isinstance(value, RequestId):
            return value
        return cls(value)

    @classmethod
    def string(cls, value: str) -> "RequestId":
        return cls(value)

    @classmethod
    def integer(cls, value: int) -> "RequestId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)

    def to_json(self) -> str | int:
        return self.value


@dataclass(frozen=True)
class Tool:
    name: str
    input_schema: JsonValue = None
    title: str | None = None
    description: str | None = None
    output_schema: JsonValue | None = None
    annotations: JsonValue | None = None
    icons: tuple[JsonValue, ...] | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if self.title is not None and not isinstance(self.title, str):
            raise TypeError("title must be a string")
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if self.icons is not None and (isinstance(self.icons, str) or not isinstance(self.icons, list | tuple)):
            raise TypeError("icons must be a list")
        if self.icons is not None and not isinstance(self.icons, tuple):
            object.__setattr__(self, "icons", tuple(self.icons))

    @classmethod
    def from_mcp_value(cls, value: JsonValue) -> "Tool":
        data = _mapping(value, "tool")
        return cls(
            name=_required_str(data, "name"),
            title=_optional_str(data, "title"),
            description=_optional_str(data, "description"),
            input_schema=_alias(data, "inputSchema", "input_schema"),
            output_schema=_alias(data, "outputSchema", "output_schema"),
            annotations=data.get("annotations"),
            icons=_optional_icons(data.get("icons")),
            meta=data.get("_meta"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "name": self.name,
            "inputSchema": self.input_schema,
        }
        _put_optional(result, "title", self.title)
        _put_optional(result, "description", self.description)
        _put_optional(result, "outputSchema", self.output_schema)
        _put_optional(result, "annotations", self.annotations)
        if self.icons is not None:
            result["icons"] = list(self.icons)
        _put_optional(result, "_meta", self.meta)
        return result


@dataclass(frozen=True)
class Resource:
    name: str
    uri: str
    annotations: JsonValue | None = None
    description: str | None = None
    mime_type: str | None = None
    size: int | None = None
    title: str | None = None
    icons: tuple[JsonValue, ...] | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if not isinstance(self.uri, str):
            raise TypeError("uri must be a string")
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if self.mime_type is not None and not isinstance(self.mime_type, str):
            raise TypeError("mime_type must be a string")
        if self.size is not None:
            object.__setattr__(self, "size", _ensure_i64(self.size, "size"))
        if self.title is not None and not isinstance(self.title, str):
            raise TypeError("title must be a string")
        if self.icons is not None and (isinstance(self.icons, str) or not isinstance(self.icons, list | tuple)):
            raise TypeError("icons must be a list")
        if self.icons is not None and not isinstance(self.icons, tuple):
            object.__setattr__(self, "icons", tuple(self.icons))

    @classmethod
    def from_mcp_value(cls, value: JsonValue) -> "Resource":
        data = _mapping(value, "resource")
        return cls(
            name=_required_str(data, "name"),
            uri=_required_str(data, "uri"),
            annotations=data.get("annotations"),
            description=_optional_str(data, "description"),
            mime_type=_ensure_optional_str(_alias(data, "mimeType", "mime_type"), "mimeType"),
            size=_optional_i64_lossy(data.get("size")),
            title=_optional_str(data, "title"),
            icons=_optional_icons(data.get("icons")),
            meta=data.get("_meta"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "name": self.name,
            "uri": self.uri,
        }
        _put_optional(result, "annotations", self.annotations)
        _put_optional(result, "description", self.description)
        _put_optional(result, "mimeType", self.mime_type)
        _put_optional(result, "size", self.size)
        _put_optional(result, "title", self.title)
        if self.icons is not None:
            result["icons"] = list(self.icons)
        _put_optional(result, "_meta", self.meta)
        return result


@dataclass(frozen=True)
class ResourceContent:
    variant: str
    uri: str
    mime_type: str | None = None
    text: str | None = None
    blob: str | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.variant, str):
            raise TypeError("variant must be a string")
        if not isinstance(self.uri, str):
            raise TypeError("uri must be a string")
        if self.mime_type is not None and not isinstance(self.mime_type, str):
            raise TypeError("mime_type must be a string")
        if self.variant == "text" and not isinstance(self.text, str):
            raise ValueError("text resource content requires text")
        if self.variant == "blob" and not isinstance(self.blob, str):
            raise ValueError("blob resource content requires blob")
        if self.variant not in {"text", "blob"}:
            raise ValueError(f"unknown resource content variant: {self.variant}")

    @classmethod
    def text_content(
        cls,
        uri: str,
        text: str,
        mime_type: str | None = None,
        meta: JsonValue | None = None,
    ) -> "ResourceContent":
        return cls("text", uri=uri, mime_type=mime_type, text=text, meta=meta)

    @classmethod
    def blob_content(
        cls,
        uri: str,
        blob: str,
        mime_type: str | None = None,
        meta: JsonValue | None = None,
    ) -> "ResourceContent":
        return cls("blob", uri=uri, mime_type=mime_type, blob=blob, meta=meta)

    @classmethod
    def from_mcp_value(cls, value: JsonValue) -> "ResourceContent":
        data = _mapping(value, "resource content")
        uri = _required_str(data, "uri")
        mime_type = _ensure_optional_str(_alias(data, "mimeType", "mime_type"), "mimeType")
        meta = data.get("_meta")
        if "text" in data:
            text = data["text"]
            if not isinstance(text, str):
                raise TypeError("text must be a string")
            return cls.text_content(uri=uri, text=text, mime_type=mime_type, meta=meta)
        if "blob" in data:
            blob = data["blob"]
            if not isinstance(blob, str):
                raise TypeError("blob must be a string")
            return cls.blob_content(uri=uri, blob=blob, mime_type=mime_type, meta=meta)
        raise KeyError("text or blob")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"uri": self.uri}
        _put_optional(result, "mimeType", self.mime_type)
        if self.variant == "text":
            result["text"] = self.text
        else:
            result["blob"] = self.blob
        _put_optional(result, "_meta", self.meta)
        return result


@dataclass(frozen=True)
class ResourceTemplate:
    uri_template: str
    name: str
    annotations: JsonValue | None = None
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.uri_template, str):
            raise TypeError("uri_template must be a string")
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        if self.title is not None and not isinstance(self.title, str):
            raise TypeError("title must be a string")
        if self.description is not None and not isinstance(self.description, str):
            raise TypeError("description must be a string")
        if self.mime_type is not None and not isinstance(self.mime_type, str):
            raise TypeError("mime_type must be a string")

    @classmethod
    def from_mcp_value(cls, value: JsonValue) -> "ResourceTemplate":
        data = _mapping(value, "resource template")
        uri_template = _alias(data, "uriTemplate", "uri_template")
        if not isinstance(uri_template, str):
            raise TypeError("uriTemplate must be a string")
        return cls(
            uri_template=uri_template,
            name=_required_str(data, "name"),
            annotations=data.get("annotations"),
            title=_optional_str(data, "title"),
            description=_optional_str(data, "description"),
            mime_type=_ensure_optional_str(_alias(data, "mimeType", "mime_type"), "mimeType"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "uriTemplate": self.uri_template,
            "name": self.name,
        }
        _put_optional(result, "annotations", self.annotations)
        _put_optional(result, "title", self.title)
        _put_optional(result, "description", self.description)
        _put_optional(result, "mimeType", self.mime_type)
        return result


@dataclass(frozen=True)
class CallToolResult:
    content: tuple[JsonValue, ...]
    structured_content: JsonValue | None = None
    is_error: bool | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        if isinstance(self.content, str) or not isinstance(self.content, list | tuple):
            raise TypeError("content must be a list")
        if not isinstance(self.content, tuple):
            object.__setattr__(self, "content", tuple(self.content))
        if self.is_error is not None and not isinstance(self.is_error, bool):
            raise TypeError("is_error must be a bool")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CallToolResult":
        data = _mapping(value, "call tool result")
        content = data.get("content", [])
        if not isinstance(content, list | tuple):
            raise TypeError("content must be a list")
        return cls(
            content=tuple(content),
            structured_content=_alias(data, "structuredContent", "structured_content"),
            is_error=_alias(data, "isError", "is_error"),
            meta=data.get("_meta"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"content": list(self.content)}
        _put_optional(result, "structuredContent", self.structured_content)
        _put_optional(result, "isError", self.is_error)
        _put_optional(result, "_meta", self.meta)
        return result
