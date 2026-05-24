"""Dynamic tool runtime helpers ported from Codex core.

This mirrors the dependency-free parts of
``core/src/tools/handlers/dynamic.rs``: converting dynamic tool specs into
Responses API tool specs, exposing deferred-tool search metadata, and turning a
dynamic tool response into a model-visible function output.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.core.tool_context import FunctionToolOutput, ToolPayload
from pycodex.core.tool_registry import ToolExposure
from pycodex.core.tool_search_entry import (
    ToolSearchInfo,
    ToolSearchSourceInfo,
    default_namespace_description,
)
from pycodex.protocol import (
    DynamicToolCallOutputContentItem,
    DynamicToolResponse,
    DynamicToolSpec,
    FunctionCallOutputContentItem,
    ToolName,
)

JsonValue = Any
DynamicToolRequestCallback = Callable[[str, ToolName, JsonValue], DynamicToolResponse | Mapping[str, JsonValue] | None]


@dataclass(frozen=True)
class DynamicToolHandler:
    name: ToolName
    tool_spec: dict[str, JsonValue]
    exposure_value: ToolExposure
    search_text: str
    request_callback: DynamicToolRequestCallback | None = None

    @classmethod
    def new(
        cls,
        tool: DynamicToolSpec | Mapping[str, JsonValue],
        request_callback: DynamicToolRequestCallback | None = None,
    ) -> "DynamicToolHandler | None":
        try:
            spec = tool if isinstance(tool, DynamicToolSpec) else DynamicToolSpec.from_mapping(tool)
            tool_name = ToolName.new(spec.namespace, spec.name)
            output_tool = dynamic_tool_to_responses_api_tool(spec)
            if spec.namespace is None:
                tool_spec = output_tool
            else:
                tool_spec = {
                    "type": "namespace",
                    "name": spec.namespace,
                    "description": default_namespace_description(spec.namespace),
                    "tools": [output_tool],
                }
            return cls(
                name=tool_name,
                tool_spec=tool_spec,
                exposure_value=ToolExposure.DEFERRED if spec.defer_loading else ToolExposure.DIRECT,
                search_text=build_dynamic_search_text(spec),
                request_callback=request_callback,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def tool_name(self) -> ToolName:
        return self.name

    def spec(self) -> dict[str, JsonValue]:
        return copy.deepcopy(self.tool_spec)

    def exposure(self) -> ToolExposure:
        return self.exposure_value

    def matches_kind(self, payload: ToolPayload) -> bool:
        return payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return ToolSearchInfo.from_spec(
            self.search_text,
            self.spec(),
            ToolSearchSourceInfo(
                "Dynamic tools",
                "Tools provided by the current Codex thread.",
            ),
        )

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput:
        payload = getattr(invocation_or_payload, "payload", invocation_or_payload)
        call_id = str(getattr(invocation_or_payload, "call_id", ""))
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise ValueError("dynamic tool handler received unsupported payload")
        if payload.arguments is None:
            raise ValueError("dynamic tool handler received unsupported payload")

        try:
            arguments = json.loads(payload.arguments) if payload.arguments.strip() else {}
        except json.JSONDecodeError as err:
            raise ValueError(f"failed to parse dynamic tool arguments: {err}") from err

        if self.request_callback is None:
            raise ValueError("dynamic tool call was cancelled before receiving a response")
        response = self.request_callback(call_id, self.name, arguments)
        if response is None:
            raise ValueError("dynamic tool call was cancelled before receiving a response")
        if not isinstance(response, DynamicToolResponse):
            response = DynamicToolResponse.from_mapping(response)

        return FunctionToolOutput.from_content(
            tuple(_dynamic_content_item_to_function_item(item) for item in response.content_items),
            response.success,
        )


def dynamic_tool_to_responses_api_tool(tool: DynamicToolSpec) -> dict[str, JsonValue]:
    if not isinstance(tool.input_schema, Mapping):
        raise TypeError("dynamic tool input_schema must be a mapping")
    data: dict[str, JsonValue] = {
        "type": "function",
        "name": tool.name,
        "description": tool.description,
        "strict": False,
        "parameters": copy.deepcopy(dict(tool.input_schema)),
    }
    if tool.defer_loading:
        data["defer_loading"] = True
    return data


def build_dynamic_search_text(tool: DynamicToolSpec) -> str:
    schema_properties = ()
    if isinstance(tool.input_schema, Mapping):
        raw_properties = tool.input_schema.get("properties")
        if isinstance(raw_properties, Mapping):
            schema_properties = tuple(sorted(str(key) for key in raw_properties))

    parts = [
        tool.name,
        tool.name.replace("_", " "),
        tool.description,
    ]
    if tool.namespace is not None:
        parts.append(tool.namespace)
    parts.extend(schema_properties)
    return " ".join(parts)


def _dynamic_content_item_to_function_item(
    item: DynamicToolCallOutputContentItem,
) -> FunctionCallOutputContentItem:
    if item.type == "inputText":
        return FunctionCallOutputContentItem.input_text(item.text or "")
    if item.type == "inputImage":
        return FunctionCallOutputContentItem.input_image(item.image_url or "")
    raise ValueError(f"unknown dynamic tool output content type: {item.type}")


__all__ = [
    "DynamicToolHandler",
    "DynamicToolRequestCallback",
    "build_dynamic_search_text",
    "dynamic_tool_to_responses_api_tool",
]
