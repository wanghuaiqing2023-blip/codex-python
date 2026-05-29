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

from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tool_context import FunctionToolOutput, McpToolOutput, ToolPayload
from pycodex.core.hook_names import HookToolName
from pycodex.core.tool_registry import PostToolUsePayload, PreToolUsePayload, ToolExposure, ToolInvocation, flat_tool_name
from pycodex.core.tool_search_entry import ToolSearchInfo, ToolSearchSourceInfo
from pycodex.protocol import CallToolResult, Tool, ToolName

JsonValue = Any
LEGACY_MCP_TOOL_NAME_PREFIX = "mcp__"
MCP_TOOL_NAME_DELIMITER = "__"
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
        return isinstance(payload, ToolPayload) and payload.type in {"function", "tool_search"}

    def hook_tool_name(self) -> HookToolName:
        return HookToolName.new(ensure_mcp_prefix(join_tool_name(self.tool_name())))

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

    def pre_tool_use_payload(self, invocation: ToolInvocation) -> PreToolUsePayload | None:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            return None
        return PreToolUsePayload(
            tool_name=self.hook_tool_name(),
            tool_input=mcp_hook_tool_input(invocation.payload.arguments or ""),
        )

    def with_updated_hook_input(self, invocation: ToolInvocation, updated_input: JsonValue) -> ToolInvocation:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            raise FunctionCallError.respond_to_model(
                f"tool {self.tool_name()} does not support hook input rewriting for payload {invocation.payload!r}"
            )
        try:
            arguments = json.dumps(updated_input, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as err:
            raise FunctionCallError.respond_to_model(
                f"failed to serialize rewritten MCP arguments: {err}"
            ) from err
        from dataclasses import replace

        return replace(invocation, payload=ToolPayload.function(arguments))

    def post_tool_use_payload(self, invocation: ToolInvocation, result: JsonValue) -> PostToolUsePayload | None:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            return None
        response_method = getattr(result, "post_tool_use_response", None)
        input_method = getattr(result, "post_tool_use_input", None)
        if response_method is None or input_method is None:
            return None
        tool_input = input_method(invocation.payload)
        if tool_input is None:
            return None
        tool_response = response_method(invocation.call_id, invocation.payload)
        if tool_response is None:
            return None
        return PostToolUsePayload(
            tool_name=self.hook_tool_name(),
            tool_use_id=invocation.call_id,
            tool_input=tool_input,
            tool_response=tool_response,
        )

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | McpToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        call_id = str(getattr(invocation_or_payload, "call_id", ""))
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model(
                "mcp handler received unsupported payload"
            )
        if payload.arguments is None:
            raise FunctionCallError.respond_to_model(
                "mcp handler received unsupported payload"
            )
        try:
            arguments = json.loads(payload.arguments) if payload.arguments.strip() else {}
        except json.JSONDecodeError as err:
            raise FunctionCallError.respond_to_model(
                f"failed to parse function arguments: {err}"
            ) from err
        if self.request_callback is None:
            raise FunctionCallError.respond_to_model(
                "mcp tool call requires a request callback in the Python port"
            )
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


def join_tool_name(tool_name: ToolName) -> str:
    if not isinstance(tool_name, ToolName):
        raise TypeError("tool_name must be ToolName")
    if tool_name.namespace is not None:
        namespace = tool_name.namespace.rstrip("_")
        name = tool_name.name.lstrip("_")
        return f"{namespace}{MCP_TOOL_NAME_DELIMITER}{name}"
    return tool_name.name


def ensure_mcp_prefix(name: str) -> str:
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    return name if name.startswith(LEGACY_MCP_TOOL_NAME_PREFIX) else f"{LEGACY_MCP_TOOL_NAME_PREFIX}{name}"


def mcp_hook_tool_input(raw_arguments: str) -> JsonValue:
    if not isinstance(raw_arguments, str):
        raise TypeError("raw_arguments must be a string")
    if raw_arguments.strip() == "":
        return {}
    try:
        return json.loads(raw_arguments)
    except json.JSONDecodeError:
        return raw_arguments


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
    "LEGACY_MCP_TOOL_NAME_PREFIX",
    "MCP_TOOL_NAME_DELIMITER",
    "McpHandler",
    "McpToolRequestCallback",
    "ToolInfo",
    "build_mcp_search_text",
    "create_mcp_tool_spec",
    "ensure_mcp_prefix",
    "join_tool_name",
    "mcp_hook_tool_input",
    "mcp_tool_to_responses_api_tool",
]
