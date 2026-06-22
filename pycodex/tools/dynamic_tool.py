"""Dynamic tool parser ported from ``codex-rs/tools/src/dynamic_tool.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.protocol import DynamicToolSpec

from .json_schema import parse_tool_input_schema
from .tool_definition import ToolDefinition

JsonValue = Any


def parse_dynamic_tool(tool: DynamicToolSpec | Mapping[str, JsonValue]) -> ToolDefinition:
    spec = tool if isinstance(tool, DynamicToolSpec) else DynamicToolSpec.from_mapping(tool)
    return ToolDefinition(
        name=spec.name,
        description=spec.description,
        input_schema=parse_tool_input_schema(spec.input_schema),
        output_schema=None,
        defer_loading=spec.defer_loading,
    )


__all__ = ["parse_dynamic_tool"]
