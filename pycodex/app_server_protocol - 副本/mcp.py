"""MCP protocol types ported from ``protocol/v2/mcp.rs``.

This module mirrors the app-server protocol layer. It intentionally keeps MCP
tool/resource/content payloads as JSON-shaped values instead of implementing an
MCP runtime or the full upstream RMCP model.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


class McpAuthStatus(_StringEnum):
    UNSUPPORTED = "unsupported"
    NOT_LOGGED_IN = "notLoggedIn"
    BEARER_TOKEN = "bearerToken"
    OAUTH = "oAuth"


class McpServerStatusDetail(_StringEnum):
    FULL = "full"
    TOOLS_AND_AUTH_ONLY = "toolsAndAuthOnly"


@dataclass(frozen=True)
class ListMcpServerStatusParams:
    cursor: str | None = None
    limit: int | None = None
    detail: McpServerStatusDetail | str | None = None
    thread_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cursor", _optional_str(self.cursor, "cursor"))
        object.__setattr__(self, "limit", _optional_u32(self.limit, "limit"))
        object.__setattr__(
            self,
            "detail",
            McpServerStatusDetail.parse(self.detail) if self.detail is not None else None,
        )
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ListMcpServerStatusParams":
        data = _mapping(value, "ListMcpServerStatusParams")
        return cls(
            cursor=_optional_str(data.get("cursor"), "cursor"),
            limit=_optional_u32(data.get("limit"), "limit"),
            detail=_pick(data, "detail"),
            thread_id=_optional_str(_pick(data, "thread_id", "threadId"), "thread_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {}
        if self.cursor is not None:
            result["cursor"] = self.cursor
        if self.limit is not None:
            result["limit"] = self.limit
        if self.detail is not None:
            result["detail"] = self.detail.value
        if self.thread_id is not None:
            result["thread_id"] = self.thread_id
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = self.to_mapping()
        if "thread_id" in result:
            result["threadId"] = result.pop("thread_id")
        return result


@dataclass(frozen=True)
class McpServerStatus:
    name: str
    tools: Mapping[str, JsonValue] = field(default_factory=dict)
    resources: tuple[JsonValue, ...] = ()
    resource_templates: tuple[JsonValue, ...] = ()
    auth_status: McpAuthStatus | str = McpAuthStatus.UNSUPPORTED

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "tools", _deep_mapping(self.tools, "tools"))
        object.__setattr__(self, "resources", _json_tuple(self.resources, "resources"))
        object.__setattr__(
            self,
            "resource_templates",
            _json_tuple(self.resource_templates, "resource_templates"),
        )
        object.__setattr__(self, "auth_status", McpAuthStatus.parse(self.auth_status))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerStatus":
        data = _mapping(value, "McpServerStatus")
        return cls(
            name=_ensure_str(data["name"], "name"),
            tools=_mapping(data.get("tools", {}), "tools"),
            resources=tuple(_list(data.get("resources", []), "resources")),
            resource_templates=tuple(_list(_pick(data, "resource_templates", "resourceTemplates", default=[]), "resource_templates")),
            auth_status=McpAuthStatus.parse(_pick(data, "auth_status", "authStatus")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "tools": copy.deepcopy(dict(self.tools)),
            "resources": _serialize(self.resources),
            "resource_templates": _serialize(self.resource_templates),
            "auth_status": self.auth_status.value,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = self.to_mapping()
        result["resourceTemplates"] = result.pop("resource_templates")
        result["authStatus"] = result.pop("auth_status")
        return result


@dataclass(frozen=True)
class ListMcpServerStatusResponse:
    data: tuple[McpServerStatus, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", tuple(_mcp_server_status(item) for item in self.data))
        object.__setattr__(self, "next_cursor", _optional_str(self.next_cursor, "next_cursor"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ListMcpServerStatusResponse":
        data = _mapping(value, "ListMcpServerStatusResponse")
        return cls(
            data=tuple(McpServerStatus.from_mapping(item) for item in _list(data["data"], "data")),
            next_cursor=_optional_str(_pick(data, "next_cursor", "nextCursor"), "next_cursor"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": [item.to_mapping() for item in self.data],
            "next_cursor": self.next_cursor,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": [item.to_camel_mapping() for item in self.data],
            "nextCursor": self.next_cursor,
        }


@dataclass(frozen=True)
class McpResourceReadParams:
    server: str
    uri: str
    thread_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "server", _ensure_str(self.server, "server"))
        object.__setattr__(self, "uri", _ensure_str(self.uri, "uri"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpResourceReadParams":
        data = _mapping(value, "McpResourceReadParams")
        return cls(
            thread_id=_optional_str(_pick(data, "thread_id", "threadId"), "thread_id"),
            server=_ensure_str(data["server"], "server"),
            uri=_ensure_str(data["uri"], "uri"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result = {"server": self.server, "uri": self.uri}
        if self.thread_id is not None:
            result["thread_id"] = self.thread_id
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = {"server": self.server, "uri": self.uri}
        if self.thread_id is not None:
            result["threadId"] = self.thread_id
        return result


@dataclass(frozen=True)
class McpResourceReadResponse:
    contents: tuple[JsonValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contents", _json_tuple(self.contents, "contents"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpResourceReadResponse":
        data = _mapping(value, "McpResourceReadResponse")
        return cls(contents=tuple(_list(data["contents"], "contents")))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"contents": _serialize(self.contents)}


@dataclass(frozen=True)
class McpServerToolCallParams:
    thread_id: str
    server: str
    tool: str
    arguments: JsonValue | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "server", _ensure_str(self.server, "server"))
        object.__setattr__(self, "tool", _ensure_str(self.tool, "tool"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerToolCallParams":
        data = _mapping(value, "McpServerToolCallParams")
        return cls(
            thread_id=_ensure_str(_pick(data, "thread_id", "threadId"), "thread_id"),
            server=_ensure_str(data["server"], "server"),
            tool=_ensure_str(data["tool"], "tool"),
            arguments=data.get("arguments"),
            meta=_pick(data, "meta", "_meta"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "thread_id": self.thread_id,
            "server": self.server,
            "tool": self.tool,
        }
        if self.arguments is not None:
            result["arguments"] = copy.deepcopy(self.arguments)
        if self.meta is not None:
            result["meta"] = copy.deepcopy(self.meta)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "threadId": self.thread_id,
            "server": self.server,
            "tool": self.tool,
        }
        if self.arguments is not None:
            result["arguments"] = copy.deepcopy(self.arguments)
        if self.meta is not None:
            result["_meta"] = copy.deepcopy(self.meta)
        return result


@dataclass(frozen=True)
class McpServerToolCallResponse:
    content: tuple[JsonValue, ...]
    structured_content: JsonValue | None = None
    is_error: bool | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", _json_tuple(self.content, "content"))
        object.__setattr__(self, "is_error", _optional_bool(self.is_error, "is_error"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerToolCallResponse":
        data = _mapping(value, "McpServerToolCallResponse")
        return cls(
            content=tuple(_list(data["content"], "content")),
            structured_content=_pick(data, "structured_content", "structuredContent"),
            is_error=_optional_bool(_pick(data, "is_error", "isError"), "is_error"),
            meta=_pick(data, "meta", "_meta"),
        )

    @classmethod
    def from_core(cls, value: JsonValue) -> "McpServerToolCallResponse":
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        return cls(
            content=tuple(getattr(value, "content")),
            structured_content=getattr(value, "structured_content", None),
            is_error=getattr(value, "is_error", None),
            meta=getattr(value, "meta", None),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"content": _serialize(self.content)}
        if self.structured_content is not None:
            result["structured_content"] = copy.deepcopy(self.structured_content)
        if self.is_error is not None:
            result["is_error"] = self.is_error
        if self.meta is not None:
            result["meta"] = copy.deepcopy(self.meta)
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"content": _serialize(self.content)}
        if self.structured_content is not None:
            result["structuredContent"] = copy.deepcopy(self.structured_content)
        if self.is_error is not None:
            result["isError"] = self.is_error
        if self.meta is not None:
            result["_meta"] = copy.deepcopy(self.meta)
        return result


@dataclass(frozen=True)
class McpToolCallResult:
    content: tuple[JsonValue, ...]
    structured_content: JsonValue | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", _json_tuple(self.content, "content"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpToolCallResult":
        data = _mapping(value, "McpToolCallResult")
        return cls(
            content=tuple(_list(data["content"], "content")),
            structured_content=_pick(data, "structured_content", "structuredContent"),
            meta=_pick(data, "meta", "_meta"),
        )

    @classmethod
    def from_core(cls, value: JsonValue) -> "McpToolCallResult":
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        return cls(
            content=tuple(getattr(value, "content")),
            structured_content=getattr(value, "structured_content", None),
            meta=getattr(value, "meta", None),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "content": _serialize(self.content),
            "structured_content": copy.deepcopy(self.structured_content),
            "meta": copy.deepcopy(self.meta),
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "content": _serialize(self.content),
            "structuredContent": copy.deepcopy(self.structured_content),
            "_meta": copy.deepcopy(self.meta),
        }


@dataclass(frozen=True)
class McpToolCallError:
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpToolCallError":
        data = _mapping(value, "McpToolCallError")
        return cls(message=_ensure_str(data["message"], "message"))

    @classmethod
    def from_core(cls, value: JsonValue) -> "McpToolCallError":
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        return cls(message=_ensure_str(getattr(value, "message"), "message"))

    def to_mapping(self) -> dict[str, str]:
        return {"message": self.message}


@dataclass(frozen=True)
class McpServerRefreshParams:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "McpServerRefreshParams":
        if value is not None:
            _mapping(value, "McpServerRefreshParams")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class McpServerRefreshResponse(McpServerRefreshParams):
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "McpServerRefreshResponse":
        if value is not None:
            _mapping(value, "McpServerRefreshResponse")
        return cls()


@dataclass(frozen=True)
class McpServerOauthLoginParams:
    name: str
    scopes: tuple[str, ...] | None = None
    timeout_secs: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "scopes", _optional_str_tuple(self.scopes, "scopes"))
        object.__setattr__(self, "timeout_secs", _optional_i64(self.timeout_secs, "timeout_secs"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerOauthLoginParams":
        data = _mapping(value, "McpServerOauthLoginParams")
        return cls(
            name=_ensure_str(data["name"], "name"),
            scopes=_optional_str_tuple(data.get("scopes"), "scopes"),
            timeout_secs=_optional_i64(_pick(data, "timeout_secs", "timeoutSecs"), "timeout_secs"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"name": self.name}
        if self.scopes is not None:
            result["scopes"] = list(self.scopes)
        if self.timeout_secs is not None:
            result["timeout_secs"] = self.timeout_secs
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result = self.to_mapping()
        if "timeout_secs" in result:
            result["timeoutSecs"] = result.pop("timeout_secs")
        return result


@dataclass(frozen=True)
class McpServerOauthLoginResponse:
    authorization_url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorization_url", _ensure_str(self.authorization_url, "authorization_url"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerOauthLoginResponse":
        data = _mapping(value, "McpServerOauthLoginResponse")
        return cls(authorization_url=_ensure_str(_pick(data, "authorization_url", "authorizationUrl"), "authorization_url"))

    def to_mapping(self) -> dict[str, str]:
        return {"authorization_url": self.authorization_url}

    def to_camel_mapping(self) -> dict[str, str]:
        return {"authorizationUrl": self.authorization_url}


@dataclass(frozen=True)
class McpToolCallProgressNotification:
    thread_id: str
    turn_id: str
    item_id: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "item_id", _ensure_str(self.item_id, "item_id"))
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpToolCallProgressNotification":
        data = _mapping(value, "McpToolCallProgressNotification")
        return cls(
            thread_id=_ensure_str(_pick(data, "thread_id", "threadId"), "thread_id"),
            turn_id=_ensure_str(_pick(data, "turn_id", "turnId"), "turn_id"),
            item_id=_ensure_str(_pick(data, "item_id", "itemId"), "item_id"),
            message=_ensure_str(data["message"], "message"),
        )

    def to_mapping(self) -> dict[str, str]:
        return {
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "item_id": self.item_id,
            "message": self.message,
        }

    def to_camel_mapping(self) -> dict[str, str]:
        return {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "itemId": self.item_id,
            "message": self.message,
        }


@dataclass(frozen=True)
class McpServerOauthLoginCompletedNotification:
    name: str
    success: bool
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "success", _ensure_bool(self.success, "success"))
        object.__setattr__(self, "error", _optional_str(self.error, "error"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerOauthLoginCompletedNotification":
        data = _mapping(value, "McpServerOauthLoginCompletedNotification")
        return cls(
            name=_ensure_str(data["name"], "name"),
            success=_ensure_bool(data["success"], "success"),
            error=_optional_str(data.get("error"), "error"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"name": self.name, "success": self.success}
        if self.error is not None:
            result["error"] = self.error
        return result


class McpServerStartupState(_StringEnum):
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class McpServerStatusUpdatedNotification:
    name: str
    status: McpServerStartupState | str
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "status", McpServerStartupState.parse(self.status))
        object.__setattr__(self, "error", _optional_str(self.error, "error"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerStatusUpdatedNotification":
        data = _mapping(value, "McpServerStatusUpdatedNotification")
        return cls(
            name=_ensure_str(data["name"], "name"),
            status=McpServerStartupState.parse(data["status"]),
            error=_optional_str(data.get("error"), "error"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"name": self.name, "status": self.status.value, "error": self.error}


class McpServerElicitationAction(_StringEnum):
    ACCEPT = "accept"
    DECLINE = "decline"
    CANCEL = "cancel"

    def to_core(self) -> str:
        return self.value


@dataclass(frozen=True)
class McpServerElicitationRequestParams:
    thread_id: str
    turn_id: str | None
    server_name: str
    request: "McpServerElicitationRequest"

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _optional_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "server_name", _ensure_str(self.server_name, "server_name"))
        object.__setattr__(self, "request", _elicitation_request(self.request))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerElicitationRequestParams":
        data = dict(_mapping(value, "McpServerElicitationRequestParams"))
        thread_id = _ensure_str(_pick(data, "thread_id", "threadId"), "thread_id")
        turn_id = _optional_str(_pick(data, "turn_id", "turnId"), "turn_id")
        server_name = _ensure_str(_pick(data, "server_name", "serverName"), "server_name")
        for key in ("thread_id", "threadId", "turn_id", "turnId", "server_name", "serverName"):
            data.pop(key, None)
        return cls(thread_id=thread_id, turn_id=turn_id, server_name=server_name, request=McpServerElicitationRequest.from_mapping(data))

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "server_name": self.server_name,
        }
        result.update(self.request.to_mapping())
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "threadId": self.thread_id,
            "turnId": self.turn_id,
            "serverName": self.server_name,
        }
        result.update(self.request.to_mapping())
        return result


@dataclass(frozen=True)
class McpElicitationSchema:
    schema_uri: str | None = None
    type_: str = "object"
    properties: Mapping[str, JsonValue] = field(default_factory=dict)
    required: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_uri", _optional_str(self.schema_uri, "schema_uri"))
        object.__setattr__(self, "type_", _ensure_str(self.type_, "type_"))
        if self.type_ != "object":
            raise ValueError("MCP elicitation schema type must be 'object'")
        object.__setattr__(self, "properties", _deep_mapping(self.properties, "properties"))
        object.__setattr__(self, "required", _optional_str_tuple(self.required, "required"))

    @classmethod
    def empty_object(cls) -> "McpElicitationSchema":
        return cls()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpElicitationSchema":
        data = _mapping(value, "McpElicitationSchema")
        return cls(
            schema_uri=_optional_str(data.get("$schema"), "schema_uri"),
            type_=_ensure_str(data.get("type", "object"), "type"),
            properties=_mapping(data.get("properties", {}), "properties"),
            required=_optional_str_tuple(data.get("required"), "required"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "type": self.type_,
            "properties": copy.deepcopy(dict(self.properties)),
        }
        if self.schema_uri is not None:
            result["$schema"] = self.schema_uri
        if self.required is not None:
            result["required"] = list(self.required)
        return result


class McpElicitationObjectType(_StringEnum):
    OBJECT = "object"


class McpElicitationStringType(_StringEnum):
    STRING = "string"


class McpElicitationStringFormat(_StringEnum):
    EMAIL = "email"
    URI = "uri"
    DATE = "date"
    DATE_TIME = "date-time"


class McpElicitationNumberType(_StringEnum):
    NUMBER = "number"
    INTEGER = "integer"


class McpElicitationBooleanType(_StringEnum):
    BOOLEAN = "boolean"


class McpElicitationArrayType(_StringEnum):
    ARRAY = "array"


@dataclass(frozen=True)
class McpElicitationConstOption:
    const_: str
    title: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpElicitationConstOption":
        data = _mapping(value, "McpElicitationConstOption")
        return cls(const_=_ensure_str(data["const"], "const"), title=_ensure_str(data["title"], "title"))

    def to_mapping(self) -> dict[str, str]:
        return {"const": self.const_, "title": self.title}


@dataclass(frozen=True)
class McpServerElicitationRequest:
    mode: str
    message: str
    meta: JsonValue | None = None
    requested_schema: McpElicitationSchema | Mapping[str, JsonValue] | None = None
    url: str | None = None
    elicitation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _ensure_str(self.mode, "mode"))
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))
        object.__setattr__(self, "url", _optional_str(self.url, "url"))
        object.__setattr__(self, "elicitation_id", _optional_str(self.elicitation_id, "elicitation_id"))
        if isinstance(self.requested_schema, Mapping):
            object.__setattr__(self, "requested_schema", McpElicitationSchema.from_mapping(self.requested_schema))
        elif self.requested_schema is not None and not isinstance(self.requested_schema, McpElicitationSchema):
            raise TypeError("requested_schema must be McpElicitationSchema or a mapping")

    @classmethod
    def form(
        cls,
        message: str,
        requested_schema: McpElicitationSchema | Mapping[str, JsonValue],
        meta: JsonValue | None = None,
    ) -> "McpServerElicitationRequest":
        return cls(mode="form", message=message, requested_schema=requested_schema, meta=meta)

    @classmethod
    def url_request(
        cls,
        message: str,
        url: str,
        elicitation_id: str,
        meta: JsonValue | None = None,
    ) -> "McpServerElicitationRequest":
        return cls(mode="url", message=message, url=url, elicitation_id=elicitation_id, meta=meta)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerElicitationRequest":
        data = _mapping(value, "McpServerElicitationRequest")
        mode = _ensure_str(data["mode"], "mode")
        if mode == "form":
            return cls.form(
                message=_ensure_str(data["message"], "message"),
                requested_schema=_mapping(_pick(data, "requested_schema", "requestedSchema"), "requested_schema"),
                meta=_pick(data, "meta", "_meta"),
            )
        if mode == "url":
            return cls.url_request(
                message=_ensure_str(data["message"], "message"),
                url=_ensure_str(data["url"], "url"),
                elicitation_id=_ensure_str(_pick(data, "elicitation_id", "elicitationId"), "elicitation_id"),
                meta=_pick(data, "meta", "_meta"),
            )
        raise ValueError(f"unknown elicitation request mode: {mode}")

    @classmethod
    def from_core(cls, value: JsonValue) -> "McpServerElicitationRequest":
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        mode = getattr(value, "mode", None)
        if mode == "form":
            return cls.form(
                message=getattr(value, "message"),
                requested_schema=getattr(value, "requested_schema"),
                meta=getattr(value, "meta", None),
            )
        if mode == "url":
            return cls.url_request(
                message=getattr(value, "message"),
                url=getattr(value, "url"),
                elicitation_id=getattr(value, "elicitation_id"),
                meta=getattr(value, "meta", None),
            )
        raise ValueError(f"unknown core elicitation request mode: {mode}")

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "mode": self.mode,
            "_meta": copy.deepcopy(self.meta),
            "message": self.message,
        }
        if self.mode == "form":
            if self.requested_schema is None:
                raise ValueError("form elicitation request requires requested_schema")
            result["requestedSchema"] = self.requested_schema.to_mapping()
        elif self.mode == "url":
            if self.url is None or self.elicitation_id is None:
                raise ValueError("url elicitation request requires url and elicitation_id")
            result["url"] = self.url
            result["elicitationId"] = self.elicitation_id
        else:
            raise ValueError(f"unknown elicitation request mode: {self.mode}")
        return result


@dataclass(frozen=True)
class McpServerElicitationRequestResponse:
    action: McpServerElicitationAction | str
    content: JsonValue | None = None
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", McpServerElicitationAction.parse(self.action))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "McpServerElicitationRequestResponse":
        data = _mapping(value, "McpServerElicitationRequestResponse")
        return cls(
            action=McpServerElicitationAction.parse(data["action"]),
            content=data.get("content"),
            meta=_pick(data, "meta", "_meta"),
        )

    @classmethod
    def from_core(cls, value: JsonValue) -> "McpServerElicitationRequestResponse":
        if isinstance(value, Mapping):
            return cls.from_mapping(value)
        return cls(
            action=getattr(value, "action"),
            content=getattr(value, "content", None),
            meta=getattr(value, "meta", None),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "action": self.action.value,
            "content": copy.deepcopy(self.content),
            "meta": copy.deepcopy(self.meta),
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "action": self.action.value,
            "content": copy.deepcopy(self.content),
            "_meta": copy.deepcopy(self.meta),
        }


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _deep_mapping(value: JsonValue, type_name: str) -> dict[str, JsonValue]:
    return copy.deepcopy(dict(_mapping(value, type_name)))


def _pick(data: Mapping[str, JsonValue], *keys: str, default: JsonValue = None) -> JsonValue:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_bool(value: JsonValue, field_name: str) -> bool | None:
    if value is None:
        return None
    return _ensure_bool(value, field_name)


def _optional_u32(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 2**32 - 1:
        raise TypeError(f"{field_name} must be an unsigned 32-bit integer")
    return value


def _optional_i64(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < -(2**63) or value > 2**63 - 1:
        raise TypeError(f"{field_name} must be a signed 64-bit integer")
    return value


def _list(value: JsonValue, field_name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _json_tuple(value: JsonValue, field_name: str) -> tuple[JsonValue, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable")
    return tuple(copy.deepcopy(tuple(value)))


def _optional_str_tuple(value: JsonValue, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result = tuple(value)
    if not all(isinstance(item, str) for item in result):
        raise TypeError(f"{field_name} must be an iterable of strings")
    return result


def _mcp_server_status(value: McpServerStatus | Mapping[str, JsonValue]) -> McpServerStatus:
    if isinstance(value, McpServerStatus):
        return value
    return McpServerStatus.from_mapping(value)


def _elicitation_request(
    value: McpServerElicitationRequest | Mapping[str, JsonValue],
) -> McpServerElicitationRequest:
    if isinstance(value, McpServerElicitationRequest):
        return value
    return McpServerElicitationRequest.from_mapping(value)


def _serialize(value: JsonValue) -> JsonValue:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return copy.deepcopy(value)


__all__ = [
    "ListMcpServerStatusParams",
    "ListMcpServerStatusResponse",
    "McpAuthStatus",
    "McpElicitationArrayType",
    "McpElicitationBooleanType",
    "McpElicitationConstOption",
    "McpElicitationNumberType",
    "McpElicitationObjectType",
    "McpElicitationSchema",
    "McpElicitationStringFormat",
    "McpElicitationStringType",
    "McpResourceReadParams",
    "McpResourceReadResponse",
    "McpServerElicitationAction",
    "McpServerElicitationRequest",
    "McpServerElicitationRequestParams",
    "McpServerElicitationRequestResponse",
    "McpServerOauthLoginCompletedNotification",
    "McpServerOauthLoginParams",
    "McpServerOauthLoginResponse",
    "McpServerRefreshParams",
    "McpServerRefreshResponse",
    "McpServerStartupState",
    "McpServerStatus",
    "McpServerStatusDetail",
    "McpServerStatusUpdatedNotification",
    "McpServerToolCallParams",
    "McpServerToolCallResponse",
    "McpToolCallError",
    "McpToolCallProgressNotification",
    "McpToolCallResult",
]
