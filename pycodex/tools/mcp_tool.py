"""MCP tool definition helpers ported from ``codex-rs/tools/src/mcp_tool.rs``."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from .json_schema import parse_tool_input_schema
from .tool_definition import ToolDefinition

JsonValue = Any


def parse_mcp_tool(tool: Mapping[str, JsonValue] | Any) -> ToolDefinition:
    data = _tool_mapping(tool)
    input_schema = copy.deepcopy(_input_schema(data, tool))
    if isinstance(input_schema, Mapping):
        input_schema = dict(input_schema)
        if input_schema.get("properties") is None:
            input_schema["properties"] = {}

    output_schema = _output_schema(data, tool)
    structured_content_schema = copy.deepcopy(output_schema) if output_schema is not None else {}
    return ToolDefinition(
        name=_required_str(data, "name"),
        description=_optional_str(data.get("description"), "description") or "",
        input_schema=parse_tool_input_schema(input_schema),
        output_schema=mcp_call_tool_result_output_schema(structured_content_schema),
        defer_loading=False,
    )


def mcp_call_tool_result_output_schema(structured_content_schema: JsonValue) -> dict[str, JsonValue]:
    return {
        "type": "object",
        "properties": {
            "content": {
                "type": "array",
                "items": {
                    "type": "object",
                },
            },
            "structuredContent": copy.deepcopy(structured_content_schema),
            "isError": {
                "type": "boolean",
            },
            "_meta": {
                "type": "object",
            },
        },
        "required": ["content"],
        "additionalProperties": False,
    }


def _tool_mapping(tool: Mapping[str, JsonValue] | Any) -> Mapping[str, JsonValue]:
    if hasattr(tool, "to_mapping"):
        tool = tool.to_mapping()
    if isinstance(tool, Mapping):
        return tool

    data: dict[str, JsonValue] = {}
    for attr in ("name", "description", "input_schema", "inputSchema", "output_schema", "outputSchema"):
        if hasattr(tool, attr):
            data[attr] = getattr(tool, attr)
    if data:
        return data
    raise TypeError("tool must be a mapping, expose to_mapping(), or provide MCP tool attributes")


def _input_schema(data: Mapping[str, JsonValue], tool: Any) -> JsonValue:
    for key in ("input_schema", "inputSchema", "parameters", "schema"):
        if key in data and data[key] is not None:
            return _schema_value(data[key])
    if hasattr(tool, "input_schema"):
        return _schema_value(getattr(tool, "input_schema"))
    return {}


def _output_schema(data: Mapping[str, JsonValue], tool: Any) -> JsonValue | None:
    for key in ("output_schema", "outputSchema"):
        if key in data and data[key] is not None:
            return _schema_value(data[key])
    if hasattr(tool, "output_schema"):
        return _schema_value(getattr(tool, "output_schema"))
    return None


def _schema_value(value: JsonValue) -> JsonValue:
    if hasattr(value, "to_mapping"):
        value = value.to_mapping()
    if hasattr(value, "as_ref"):
        value = value.as_ref()
    return copy.deepcopy(value)


def _required_str(data: Mapping[str, JsonValue], key: str) -> str:
    raw = data[key]
    if not isinstance(raw, str):
        raw = str(raw)
    return raw


def _optional_str(value: JsonValue, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string or None")
    return value


__all__ = [
    "mcp_call_tool_result_output_schema",
    "parse_mcp_tool",
]
