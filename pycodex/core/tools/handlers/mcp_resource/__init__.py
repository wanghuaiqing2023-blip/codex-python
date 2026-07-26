"""Shared MCP resource handler types ported from Codex core."""

from __future__ import annotations

import json
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.handlers import mcp_resource_spec
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import (
    CallToolResult,
    McpToolCallError,
    McpToolCallItem,
    McpToolCallStatus,
    Resource,
    ResourceContent,
    ResourceTemplate,
    ToolName,
    TurnItem,
)

JsonValue = Any

@dataclass(frozen=True)
class ListResourcesArgs:
    server: str | None = None
    cursor: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "ListResourcesArgs":
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise TypeError("list_mcp_resources args must be a mapping")
        return cls(_optional_str(value, "server"), _optional_str(value, "cursor"))


@dataclass(frozen=True)
class ListResourceTemplatesArgs:
    server: str | None = None
    cursor: str | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "ListResourceTemplatesArgs":
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise TypeError("list_mcp_resource_templates args must be a mapping")
        return cls(_optional_str(value, "server"), _optional_str(value, "cursor"))


@dataclass(frozen=True)
class ReadResourceArgs:
    server: str
    uri: str

    @classmethod
    def from_mapping(cls, value: JsonValue | None) -> "ReadResourceArgs":
        if value is None:
            raise FunctionCallError.respond_to_model(
                "failed to parse function arguments: expected value"
            )
        if not isinstance(value, dict):
            raise FunctionCallError.respond_to_model(
                "failed to parse function arguments: expected object"
            )
        try:
            return cls(_required_str(value, "server"), _required_str(value, "uri"))
        except (KeyError, TypeError) as err:
            raise FunctionCallError.respond_to_model(
                f"failed to parse function arguments: {err}"
            ) from err


@dataclass(frozen=True)
class ListResourcesResult:
    resources: tuple[Resource, ...] = field(default_factory=tuple)
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", tuple(_coerce_resource(item) for item in self.resources))
        if self.next_cursor is not None and not isinstance(self.next_cursor, str):
            raise TypeError("next_cursor must be a string or None")


@dataclass(frozen=True)
class ListResourceTemplatesResult:
    resource_templates: tuple[ResourceTemplate, ...] = field(default_factory=tuple)
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_templates",
            tuple(_coerce_resource_template(item) for item in self.resource_templates),
        )
        if self.next_cursor is not None and not isinstance(self.next_cursor, str):
            raise TypeError("next_cursor must be a string or None")


@dataclass(frozen=True)
class ReadResourceResult:
    contents: tuple[ResourceContent, ...] = field(default_factory=tuple)
    meta: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "contents", tuple(_coerce_resource_content(item) for item in self.contents))

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"contents": [item.to_mapping() for item in self.contents]}
        if self.meta is not None:
            result["_meta"] = self.meta
        return result


@dataclass(frozen=True)
class ResourceWithServer:
    server: str
    resource: Resource

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"server": self.server, **self.resource.to_mapping()}


@dataclass(frozen=True)
class ResourceTemplateWithServer:
    server: str
    template: ResourceTemplate

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"server": self.server, **self.template.to_mapping()}


@dataclass(frozen=True)
class ListResourcesPayload:
    resources: tuple[ResourceWithServer, ...]
    server: str | None = None
    next_cursor: str | None = None

    @classmethod
    def from_single_server(cls, server: str, result: ListResourcesResult) -> "ListResourcesPayload":
        return cls(tuple(ResourceWithServer(server, item) for item in result.resources), server, result.next_cursor)

    @classmethod
    def from_all_servers(cls, resources_by_server: Mapping[str, Any]) -> "ListResourcesPayload":
        if not isinstance(resources_by_server, Mapping):
            raise TypeError("resources_by_server must be a mapping")
        resources: list[ResourceWithServer] = []
        for server in sorted(resources_by_server):
            if not isinstance(server, str):
                raise TypeError("server names must be strings")
            for resource in _resource_tuple(resources_by_server[server]):
                resources.append(ResourceWithServer(server, resource))
        return cls(tuple(resources))

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"resources": [item.to_mapping() for item in self.resources]}
        if self.server is not None:
            result["server"] = self.server
        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor
        return result


@dataclass(frozen=True)
class ListResourceTemplatesPayload:
    resource_templates: tuple[ResourceTemplateWithServer, ...]
    server: str | None = None
    next_cursor: str | None = None

    @classmethod
    def from_single_server(cls, server: str, result: ListResourceTemplatesResult) -> "ListResourceTemplatesPayload":
        return cls(tuple(ResourceTemplateWithServer(server, item) for item in result.resource_templates), server, result.next_cursor)

    @classmethod
    def from_all_servers(cls, templates_by_server: Mapping[str, Any]) -> "ListResourceTemplatesPayload":
        if not isinstance(templates_by_server, Mapping):
            raise TypeError("templates_by_server must be a mapping")
        templates: list[ResourceTemplateWithServer] = []
        for server in sorted(templates_by_server):
            if not isinstance(server, str):
                raise TypeError("server names must be strings")
            for template in _resource_template_tuple(templates_by_server[server]):
                templates.append(ResourceTemplateWithServer(server, template))
        return cls(tuple(templates))

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"resourceTemplates": [item.to_mapping() for item in self.resource_templates]}
        if self.server is not None:
            result["server"] = self.server
        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor
        return result


@dataclass(frozen=True)
class ReadResourcePayload:
    server: str
    uri: str
    result: ReadResourceResult

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"server": self.server, "uri": self.uri, **self.result.to_mapping()}


class McpResourceProvider(Protocol):
    def list_resources(self, server: str, cursor: str | None = None) -> ListResourcesResult:
        ...

    def list_all_resources(self) -> Mapping[str, Any]:
        ...

    def list_resource_templates(self, server: str, cursor: str | None = None) -> ListResourceTemplatesResult:
        ...

    def list_all_resource_templates(self) -> Mapping[str, Any]:
        ...

    def read_resource(self, server: str, uri: str) -> ReadResourceResult:
        ...


class InMemoryMcpResourceProvider:
    def __init__(
        self,
        *,
        resources: Mapping[str, Any] | None = None,
        templates: Mapping[str, Any] | None = None,
        contents: Mapping[tuple[str, str], ReadResourceResult] | None = None,
    ) -> None:
        self.resources = dict(resources or {})
        self.templates = dict(templates or {})
        self.contents = dict(contents or {})

    def list_resources(self, server: str, cursor: str | None = None) -> ListResourcesResult:
        _required_normalized("server", server)
        return ListResourcesResult(_resource_tuple(self.resources.get(server, ())), _optional_normalized(cursor))

    def list_all_resources(self) -> Mapping[str, Any]:
        return self.resources

    def list_resource_templates(self, server: str, cursor: str | None = None) -> ListResourceTemplatesResult:
        _required_normalized("server", server)
        return ListResourceTemplatesResult(_resource_template_tuple(self.templates.get(server, ())), _optional_normalized(cursor))

    def list_all_resource_templates(self) -> Mapping[str, Any]:
        return self.templates

    def read_resource(self, server: str, uri: str) -> ReadResourceResult:
        server = _required_normalized("server", server)
        uri = _required_normalized("uri", uri)
        try:
            return self.contents[(server, uri)]
        except KeyError as err:
            raise ValueError(f"resource not found: {server} {uri}") from err


def parse_mcp_resource_arguments(raw_args: str | None) -> JsonValue | None:
    if raw_args is None:
        raise FunctionCallError.respond_to_model("failed to parse function arguments: expected value")
    if not isinstance(raw_args, str):
        raise TypeError("arguments must be a string")
    if raw_args.strip() == "":
        return None
    try:
        value = json.loads(raw_args)
    except json.JSONDecodeError as err:
        raise FunctionCallError.respond_to_model(f"failed to parse function arguments: {err}") from err
    return None if value is None else value


def serialize_function_output(payload: JsonValue) -> FunctionToolOutput:
    try:
        content = json.dumps(payload, separators=(",", ":"))
    except (TypeError, ValueError) as err:
        raise FunctionCallError.respond_to_model(f"failed to serialize MCP resource response: {err}") from err
    return FunctionToolOutput.from_text(content, True)


def _mcp_invocation(server: str, tool: str, arguments: JsonValue | None) -> dict[str, JsonValue]:
    return {"server": server, "tool": tool, "arguments": arguments}


def _call_tool_result_from_content(content: str, success: bool | None) -> CallToolResult:
    return CallToolResult(
        content=({"type": "text", "text": content},),
        is_error=None if success is None else not success,
    )


def _emit_tool_call_begin(invocation_or_payload: Any, invocation: Mapping[str, JsonValue]) -> Any | None:
    session, turn, call_id = _event_context(invocation_or_payload)
    if session is None:
        return None
    started = getattr(session, "emit_turn_item_started", None)
    if not callable(started):
        return None
    item = TurnItem.mcp_tool_call(
        McpToolCallItem(
            id=call_id,
            server=str(invocation["server"]),
            tool=str(invocation["tool"]),
            arguments=invocation["arguments"] if invocation["arguments"] is not None else None,
            status=McpToolCallStatus.IN_PROGRESS,
        )
    )
    return started(turn, item)


def _emit_tool_call_end(
    invocation_or_payload: Any,
    invocation: Mapping[str, JsonValue],
    duration_ms: int,
    *,
    result: CallToolResult | None = None,
    error: str | None = None,
) -> Any | None:
    session, turn, call_id = _event_context(invocation_or_payload)
    if session is None:
        return None
    completed = getattr(session, "emit_turn_item_completed", None)
    if not callable(completed):
        return None
    status = (
        McpToolCallStatus.FAILED
        if error is not None or (result is not None and result.is_error is True)
        else McpToolCallStatus.COMPLETED
    )
    item = TurnItem.mcp_tool_call(
        McpToolCallItem(
            id=call_id,
            server=str(invocation["server"]),
            tool=str(invocation["tool"]),
            arguments=invocation["arguments"] if invocation["arguments"] is not None else None,
            status=status,
            result=result,
            error=McpToolCallError(error) if error is not None else None,
            duration=duration_ms,
        )
    )
    return completed(turn, item)


def _event_context(invocation_or_payload: Any) -> tuple[Any | None, Any | None, str]:
    session = getattr(invocation_or_payload, "session", None)
    turn = getattr(invocation_or_payload, "turn", None)
    call_id = getattr(invocation_or_payload, "call_id", None)
    if session is None or turn is None or not isinstance(call_id, str) or not call_id:
        return None, None, ""
    return session, turn, call_id


def _duration_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


async def _await_events_then_output(
    started: Any,
    ended: Any,
    output: FunctionToolOutput,
) -> FunctionToolOutput:
    if inspect.isawaitable(started):
        await started
    if inspect.isawaitable(ended):
        await ended
    return output


async def _await_events_then_raise(started: Any, ended: Any, err: FunctionCallError) -> FunctionToolOutput:
    if inspect.isawaitable(started):
        await started
    if inspect.isawaitable(ended):
        await ended
    raise err


def _function_payload(invocation_or_payload: Any, tool_name: str) -> ToolPayload:
    payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
    if not isinstance(payload, ToolPayload) or payload.type != "function":
        raise FunctionCallError.respond_to_model(f"{tool_name} handler received unsupported payload")
    return payload


def _matches_function(payload: ToolPayload) -> bool:
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    return payload.type in {"function", "tool_search"}


def _provider_call(func: Any, label: str) -> Any:
    try:
        return func()
    except FunctionCallError:
        raise
    except Exception as err:
        raise FunctionCallError.respond_to_model(f"{label} failed: {err}") from err


def _optional_normalized(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _required_normalized(field: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    normalized = value.strip()
    if normalized == "":
        raise FunctionCallError.respond_to_model(f"{field} must be provided")
    return normalized


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
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


def _resource_tuple(values: Any) -> tuple[Resource, ...]:
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise TypeError("resources must be a list")
    return tuple(_coerce_resource(item) for item in values)


def _resource_template_tuple(values: Any) -> tuple[ResourceTemplate, ...]:
    if isinstance(values, str) or not isinstance(values, (list, tuple)):
        raise TypeError("resource templates must be a list")
    return tuple(_coerce_resource_template(item) for item in values)


def _coerce_resource(value: Resource | JsonValue) -> Resource:
    if isinstance(value, Resource):
        return value
    return Resource.from_mcp_value(value)


def _coerce_resource_template(value: ResourceTemplate | JsonValue) -> ResourceTemplate:
    if isinstance(value, ResourceTemplate):
        return value
    return ResourceTemplate.from_mcp_value(value)


def _coerce_resource_content(value: ResourceContent | JsonValue) -> ResourceContent:
    if isinstance(value, ResourceContent):
        return value
    return ResourceContent.from_mcp_value(value)


from .list_mcp_resource_templates import ListMcpResourceTemplatesHandler
from .list_mcp_resources import ListMcpResourcesHandler
from .read_mcp_resource import ReadMcpResourceHandler
