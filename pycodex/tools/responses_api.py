"""Responses API tool primitives ported from ``codex-rs/tools/src/responses_api.rs``."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import DynamicToolSpec, ToolName

from .dynamic_tool import parse_dynamic_tool
from .tool_definition import ToolDefinition

JsonValue = Any


@dataclass(frozen=True)
class FreeformToolFormat:
    type: str
    syntax: str
    definition: str

    def __post_init__(self) -> None:
        _ensure_str(self.type, "type")
        _ensure_str(self.syntax, "syntax")
        _ensure_str(self.definition, "definition")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "type": self.type,
            "syntax": self.syntax,
            "definition": self.definition,
        }


@dataclass(frozen=True)
class FreeformTool:
    name: str
    description: str
    format: FreeformToolFormat

    def __post_init__(self) -> None:
        _ensure_str(self.name, "name")
        _ensure_str(self.description, "description")
        if not isinstance(self.format, FreeformToolFormat):
            raise TypeError("format must be FreeformToolFormat")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "description": self.description,
            "format": self.format.to_mapping(),
        }


@dataclass(frozen=True)
class ResponsesApiTool:
    name: str
    description: str
    strict: bool
    parameters: JsonValue
    defer_loading: bool | None = None
    output_schema: JsonValue | None = None

    def __post_init__(self) -> None:
        _ensure_str(self.name, "name")
        _ensure_str(self.description, "description")
        _ensure_bool(self.strict, "strict")
        if self.defer_loading is not None:
            _ensure_bool(self.defer_loading, "defer_loading")
        object.__setattr__(self, "parameters", copy.deepcopy(self.parameters))
        object.__setattr__(self, "output_schema", copy.deepcopy(self.output_schema))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "strict": self.strict,
            "parameters": copy.deepcopy(self.parameters),
        }
        if self.defer_loading is not None:
            data["defer_loading"] = self.defer_loading
        return data


@dataclass(frozen=True)
class ResponsesApiNamespaceTool:
    function: ResponsesApiTool

    def __post_init__(self) -> None:
        if not isinstance(self.function, ResponsesApiTool):
            raise TypeError("function must be ResponsesApiTool")

    @classmethod
    def from_function(cls, tool: ResponsesApiTool) -> "ResponsesApiNamespaceTool":
        return cls(function=tool)

    def to_mapping(self) -> dict[str, JsonValue]:
        return self.function.to_mapping()


@dataclass(frozen=True)
class ResponsesApiNamespace:
    name: str
    description: str
    tools: tuple[ResponsesApiNamespaceTool, ...]

    def __post_init__(self) -> None:
        _ensure_str(self.name, "name")
        _ensure_str(self.description, "description")
        object.__setattr__(self, "tools", tuple(_namespace_tool(tool) for tool in self.tools))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "type": "namespace",
            "name": self.name,
            "description": self.description,
            "tools": [tool.to_mapping() for tool in self.tools],
        }


@dataclass(frozen=True)
class LoadableToolSpec:
    type: str
    value: ResponsesApiTool | ResponsesApiNamespace

    def __post_init__(self) -> None:
        if self.type == "function":
            if not isinstance(self.value, ResponsesApiTool):
                raise TypeError("function loadable spec must hold ResponsesApiTool")
        elif self.type == "namespace":
            if not isinstance(self.value, ResponsesApiNamespace):
                raise TypeError("namespace loadable spec must hold ResponsesApiNamespace")
        else:
            raise ValueError("unsupported loadable tool spec type")

    @classmethod
    def function(cls, tool: ResponsesApiTool) -> "LoadableToolSpec":
        return cls("function", tool)

    @classmethod
    def namespace(cls, namespace: ResponsesApiNamespace) -> "LoadableToolSpec":
        return cls("namespace", namespace)

    def to_mapping(self) -> dict[str, JsonValue]:
        return self.value.to_mapping()


def default_namespace_description(namespace_name: str) -> str:
    _ensure_str(namespace_name, "namespace_name")
    return f"Tools in the {namespace_name} namespace."


def dynamic_tool_to_responses_api_tool(
    tool: DynamicToolSpec | Mapping[str, JsonValue],
) -> ResponsesApiTool:
    return tool_definition_to_responses_api_tool(parse_dynamic_tool(tool))


def coalesce_loadable_tool_specs(
    specs: Iterable[LoadableToolSpec | Mapping[str, JsonValue]],
) -> tuple[LoadableToolSpec, ...]:
    coalesced: list[LoadableToolSpec] = []
    for raw_spec in specs:
        spec = _loadable_spec(raw_spec)
        if spec.type == "function":
            coalesced.append(spec)
            continue

        namespace = spec.value
        assert isinstance(namespace, ResponsesApiNamespace)
        existing = next(
            (
                item
                for item in coalesced
                if item.type == "namespace"
                and isinstance(item.value, ResponsesApiNamespace)
                and item.value.name == namespace.name
            ),
            None,
        )
        if existing is None:
            coalesced.append(spec)
        else:
            existing_namespace = existing.value
            assert isinstance(existing_namespace, ResponsesApiNamespace)
            merged = ResponsesApiNamespace(
                name=existing_namespace.name,
                description=existing_namespace.description,
                tools=existing_namespace.tools + namespace.tools,
            )
            coalesced[coalesced.index(existing)] = LoadableToolSpec.namespace(merged)
    return tuple(coalesced)


def mcp_tool_to_responses_api_tool(
    tool_name: ToolName | Mapping[str, JsonValue] | str,
    tool: Mapping[str, JsonValue] | Any,
) -> ResponsesApiTool:
    parsed_tool_name = _tool_name(tool_name)
    return tool_definition_to_responses_api_tool(_parse_mcp_tool(tool).renamed(parsed_tool_name.name))


def mcp_tool_to_deferred_responses_api_tool(
    tool_name: ToolName | Mapping[str, JsonValue] | str,
    tool: Mapping[str, JsonValue] | Any,
) -> ResponsesApiTool:
    parsed_tool_name = _tool_name(tool_name)
    return tool_definition_to_responses_api_tool(
        _parse_mcp_tool(tool).renamed(parsed_tool_name.name).into_deferred(),
    )


def tool_definition_to_responses_api_tool(
    tool_definition: ToolDefinition | Mapping[str, JsonValue],
) -> ResponsesApiTool:
    definition = (
        tool_definition
        if isinstance(tool_definition, ToolDefinition)
        else ToolDefinition.from_mapping(tool_definition)
    )
    return ResponsesApiTool(
        name=definition.name,
        description=definition.description,
        strict=False,
        defer_loading=True if definition.defer_loading else None,
        parameters=definition.input_schema,
        output_schema=definition.output_schema,
    )


def _parse_mcp_tool(tool: Mapping[str, JsonValue] | Any) -> ToolDefinition:
    data = _mapping(tool.to_mapping() if hasattr(tool, "to_mapping") else tool, "tool")
    input_schema = (
        data.get("input_schema")
        if data.get("input_schema") is not None
        else data.get("inputSchema")
        if data.get("inputSchema") is not None
        else data.get("parameters")
        if data.get("parameters") is not None
        else data.get("schema")
        if data.get("schema") is not None
        else {}
    )
    return ToolDefinition(
        name=_required_str(data, "name"),
        description=_required_str(data, "description"),
        input_schema=copy.deepcopy(input_schema),
        output_schema=copy.deepcopy(data.get("output_schema")),
        defer_loading=bool(data.get("defer_loading", False)),
    )


def _loadable_spec(value: LoadableToolSpec | Mapping[str, JsonValue]) -> LoadableToolSpec:
    if isinstance(value, LoadableToolSpec):
        return value
    data = _mapping(value.to_mapping() if hasattr(value, "to_mapping") else value, "loadable spec")
    spec_type = _required_str(data, "type")
    if spec_type == "function":
        return LoadableToolSpec.function(_responses_api_tool(data))
    if spec_type == "namespace":
        return LoadableToolSpec.namespace(
            ResponsesApiNamespace(
                name=_required_str(data, "name"),
                description=_required_str(data, "description"),
                tools=tuple(_namespace_tool(tool) for tool in data.get("tools", ())),
            ),
        )
    raise ValueError("unsupported loadable tool spec type")


def _responses_api_tool(value: ResponsesApiTool | Mapping[str, JsonValue]) -> ResponsesApiTool:
    if isinstance(value, ResponsesApiTool):
        return value
    data = _mapping(value, "responses api tool")
    return ResponsesApiTool(
        name=_required_str(data, "name"),
        description=_required_str(data, "description"),
        strict=bool(data.get("strict", False)),
        defer_loading=data.get("defer_loading"),
        parameters=copy.deepcopy(data.get("parameters", {})),
        output_schema=copy.deepcopy(data.get("output_schema")),
    )


def _namespace_tool(value: ResponsesApiNamespaceTool | ResponsesApiTool | Mapping[str, JsonValue]) -> ResponsesApiNamespaceTool:
    if isinstance(value, ResponsesApiNamespaceTool):
        return value
    if isinstance(value, ResponsesApiTool):
        return ResponsesApiNamespaceTool.from_function(value)
    data = _mapping(value, "namespace tool")
    if data.get("type", "function") != "function":
        raise TypeError("namespace tool must be a function")
    return ResponsesApiNamespaceTool.from_function(_responses_api_tool(data))


def _tool_name(value: ToolName | Mapping[str, JsonValue] | str) -> ToolName:
    if isinstance(value, ToolName):
        return value
    if isinstance(value, str):
        return ToolName.plain(value)
    return ToolName.from_mapping(value)


def _mapping(value: object, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    return value


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    raw = value[key]
    _ensure_str(raw, key)
    return raw


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_bool(value: object, name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a bool")


__all__ = [
    "FreeformTool",
    "FreeformToolFormat",
    "LoadableToolSpec",
    "ResponsesApiNamespace",
    "ResponsesApiNamespaceTool",
    "ResponsesApiTool",
    "coalesce_loadable_tool_specs",
    "default_namespace_description",
    "dynamic_tool_to_responses_api_tool",
    "mcp_tool_to_deferred_responses_api_tool",
    "mcp_tool_to_responses_api_tool",
    "tool_definition_to_responses_api_tool",
]
