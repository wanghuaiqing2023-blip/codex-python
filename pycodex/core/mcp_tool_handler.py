"""MCP tool runtime helpers ported from Codex core.

This is the dependency-free part of ``core/src/tools/handlers/mcp.rs``:
turning MCP tool metadata into namespaced Responses API specs, exposing
tool-search metadata, and preserving parallel-call capability rules.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pycodex.core.tool_context import FunctionToolOutput, McpToolOutput, ToolPayload
from pycodex.core.tool_registry import ToolExposure, flat_tool_name
from pycodex.core.tool_search_entry import ToolSearchInfo, ToolSearchSourceInfo
from pycodex.protocol import CallToolResult, Tool, ToolName

JsonValue = Any
McpToolRequestCallback = Callable[
    ["ToolInfo", str, ToolName, JsonValue],
    FunctionToolOutput | McpToolOutput | CallToolResult | str | Mapping[str, JsonValue],
]


@dataclass(frozen=True)
class ToolInfo:
    server_name: str
    callable_namespace: str
    callable_name: str
    tool: Tool
    supports_parallel_tool_calls: bool = False
    server_origin: str | None = None
    namespace_description: str | None = None
    connector_id: str | None = None
    connector_name: str | None = None
    plugin_display_names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.tool, Tool):
            object.__setattr__(self, "tool", Tool.from_mcp_value(self.tool))
        if not isinstance(self.plugin_display_names, tuple):
            object.__setattr__(self, "plugin_display_names", tuple(self.plugin_display_names))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ToolInfo":
        return cls(
            server_name=str(value["server_name"]),
            supports_parallel_tool_calls=bool(value.get("supports_parallel_tool_calls", False)),
            server_origin=_optional_str(value.get("server_origin")),
            callable_name=str(value["callable_name"]),
            callable_namespace=str(value["callable_namespace"]),
            namespace_description=_optional_str(value.get("namespace_description")),
            connector_id=_optional_str(value.get("connector_id")),
            connector_name=_optional_str(value.get("connector_name")),
            plugin_display_names=tuple(str(name) for name in value.get("plugin_display_names", ())),
            tool=Tool.from_mcp_value(value["tool"]),
        )

    def canonical_tool_name(self) -> ToolName:
        return ToolName.namespaced(self.callable_namespace, self.callable_name)


@dataclass(frozen=True)
class McpHandler:
    tool_info: ToolInfo
    tool_spec: dict[str, JsonValue]
    request_callback: McpToolRequestCallback | None = None

    @classmethod
    def new(
        cls,
        tool_info: ToolInfo | Mapping[str, JsonValue],
        request_callback: McpToolRequestCallback | None = None,
    ) -> "McpHandler":
        info = tool_info if isinstance(tool_info, ToolInfo) else ToolInfo.from_mapping(tool_info)
        return cls(info, create_mcp_tool_spec(info), request_callback)

    def tool_name(self) -> ToolName:
        return self.tool_info.canonical_tool_name()

    def spec(self) -> dict[str, JsonValue]:
        return copy.deepcopy(self.tool_spec)

    def exposure(self) -> ToolExposure:
        return ToolExposure.DIRECT

    def supports_parallel_tool_calls(self) -> bool:
        return self.tool_info.supports_parallel_tool_calls or _tool_read_only_hint(self.tool_info.tool)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        source_name = _trimmed(self.tool_info.connector_name) or _trimmed(self.tool_info.server_name)
        source_info = None
        if source_name:
            source_info = ToolSearchSourceInfo(
                source_name,
                _trimmed(self.tool_info.namespace_description),
            )
        return ToolSearchInfo.from_spec(
            build_mcp_search_text(self.tool_info),
            self.spec(),
            source_info,
        )

    def telemetry_tags(self) -> tuple[tuple[str, str], ...]:
        tags = [("mcp_server", self.tool_info.server_name)]
        if self.tool_info.server_origin is not None:
            tags.append(("mcp_server_origin", self.tool_info.server_origin))
        return tuple(tags)

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | McpToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        call_id = str(getattr(invocation_or_payload, "call_id", ""))
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise ValueError("mcp handler received unsupported payload")
        if payload.arguments is None:
            raise ValueError("mcp handler received unsupported payload")
        try:
            arguments = json.loads(payload.arguments) if payload.arguments.strip() else {}
        except json.JSONDecodeError as err:
            raise ValueError(f"failed to parse mcp tool arguments: {err}") from err
        if self.request_callback is None:
            raise ValueError("mcp tool call requires a request callback in the Python port")
        output = self.request_callback(self.tool_info, call_id, self.tool_name(), arguments)
        if isinstance(output, FunctionToolOutput | McpToolOutput):
            return output
        if isinstance(output, str):
            return FunctionToolOutput.from_text(output, True)
        result = output if isinstance(output, CallToolResult) else CallToolResult.from_mapping(output)
        return McpToolOutput(
            result=result,
            tool_input=arguments,
            wall_time_seconds=0.0,
            original_image_detail_supported=False,
            truncation_policy=_default_truncation_policy(),
        )


def create_mcp_tool_spec(tool_info: ToolInfo) -> dict[str, JsonValue]:
    description = (
        _trimmed(tool_info.namespace_description)
        or (
            f"Tools for working with {_trimmed(tool_info.connector_name)}."
            if _trimmed(tool_info.connector_name)
            else ""
        )
    )
    return {
        "type": "namespace",
        "name": tool_info.callable_namespace,
        "description": description,
        "tools": [mcp_tool_to_responses_api_tool(tool_info)],
    }


def mcp_tool_to_responses_api_tool(tool_info: ToolInfo) -> dict[str, JsonValue]:
    tool = tool_info.tool
    data: dict[str, JsonValue] = {
        "type": "function",
        "name": tool_info.callable_name,
        "description": tool.description or "",
        "strict": False,
        "parameters": copy.deepcopy(tool.input_schema),
    }
    if tool.output_schema is not None:
        data["output_schema"] = copy.deepcopy(tool.output_schema)
    return data


def build_mcp_search_text(info: ToolInfo) -> str:
    schema_properties = ()
    if isinstance(info.tool.input_schema, Mapping):
        raw_properties = info.tool.input_schema.get("properties")
        if isinstance(raw_properties, Mapping):
            schema_properties = tuple(sorted(str(key) for key in raw_properties))

    parts = [
        flat_tool_name(info.canonical_tool_name()),
        info.callable_name,
        info.tool.name,
        info.server_name,
    ]
    for value in (
        info.tool.title,
        info.tool.description,
        info.connector_name,
        info.namespace_description,
        *info.plugin_display_names,
    ):
        trimmed = _trimmed(value)
        if trimmed:
            parts.append(trimmed)
    parts.extend(schema_properties)
    return " ".join(parts)


def _tool_read_only_hint(tool: Tool) -> bool:
    annotations = tool.annotations
    if annotations is None:
        return False
    value = getattr(annotations, "read_only_hint", None)
    if value is None and isinstance(annotations, Mapping):
        value = annotations.get("readOnlyHint", annotations.get("read_only_hint"))
    return bool(value)


def _trimmed(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _optional_str(value: JsonValue) -> str | None:
    return None if value is None else str(value)


def _default_truncation_policy():
    from pycodex.protocol import TruncationPolicyConfig

    return TruncationPolicyConfig.tokens(10_000)


__all__ = [
    "McpHandler",
    "McpToolRequestCallback",
    "ToolInfo",
    "build_mcp_search_text",
    "create_mcp_tool_spec",
    "mcp_tool_to_responses_api_tool",
]
