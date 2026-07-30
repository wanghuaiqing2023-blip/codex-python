"""Dedicated memory tools from Rust ``memories/src/tools/mod.rs``."""

from __future__ import annotations

import dataclasses
import json
import builtins
from enum import Enum
from typing import Any

from pycodex.core.tools.registry import ToolExposure
from pycodex.ext.extension_api import FunctionCallError, ToolName
from pycodex.tools import (
    ResponsesApiNamespace,
    ResponsesApiNamespaceTool,
    ResponsesApiTool,
    ResponsesToolSpec,
    default_namespace_description,
    parse_tool_input_schema,
)

from ..backend import MemoriesBackendError
from ..schema import input_schema_for, output_schema_for

MEMORY_TOOLS_NAMESPACE = "memories"
DEFAULT_LIST_MAX_RESULTS = 2_000
MAX_LIST_RESULTS = 2_000
DEFAULT_SEARCH_MAX_RESULTS = 200
MAX_SEARCH_RESULTS = 200
DEFAULT_READ_MAX_TOKENS = 20_000


def memory_tools(backend: Any, metrics_client: Any = None) -> list[Any]:
    from .ad_hoc_note import AddAdHocNoteTool
    from .list import ListTool
    from .read import ReadTool
    from .search import SearchTool

    return [
        AddAdHocNoteTool(backend, metrics_client),
        ListTool(backend, metrics_client),
        ReadTool(backend, metrics_client),
        SearchTool(backend, metrics_client),
    ]


def memory_tool_name(name: str) -> ToolName:
    return ToolName.namespaced(MEMORY_TOOLS_NAMESPACE, name)


def memory_function_tool(
    name: str,
    description: str,
    input_type: type[Any],
    output_type: type[Any],
) -> ResponsesToolSpec:
    tool = ResponsesApiTool(
        name=name,
        description=description,
        strict=False,
        defer_loading=None,
        parameters=parse_tool_input_schema(input_schema_for(input_type)).to_mapping(),
        output_schema=output_schema_for(output_type),
    )
    namespace = ResponsesApiNamespace(
        name=MEMORY_TOOLS_NAMESPACE,
        description=default_namespace_description(MEMORY_TOOLS_NAMESPACE),
        tools=(ResponsesApiNamespaceTool.from_function(tool),),
    )
    return ResponsesToolSpec.namespace(namespace)


def parse_args(call: Any) -> dict[str, Any]:
    arguments = call.function_arguments()
    if not arguments.strip():
        return {}
    try:
        value = json.loads(arguments)
    except (TypeError, ValueError) as error:
        raise FunctionCallError.respond_to_model(str(error)) from error
    if not isinstance(value, dict):
        raise FunctionCallError.respond_to_model("tool arguments must be an object")
    return value


def reject_unknown_args(args: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise FunctionCallError.respond_to_model(
            f"unknown field{'' if len(unknown) == 1 else 's'}: {', '.join(unknown)}"
        )


def clamp_max_results(requested: int | None, default: int, maximum: int) -> int:
    return min(max(default if requested is None else requested, 1), maximum)


def backend_error_to_function_call(error: Exception) -> FunctionCallError:
    if isinstance(error, OSError) or isinstance(error.__cause__, OSError):
        return FunctionCallError.fatal(str(error))
    if isinstance(error, MemoriesBackendError):
        return FunctionCallError.respond_to_model(str(error))
    return FunctionCallError.fatal(str(error))


def to_json_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {
            field.name: to_json_value(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [to_json_value(item) for item in value]
    if isinstance(value, builtins.list):
        return [to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    return value


__all__ = [
    "DEFAULT_LIST_MAX_RESULTS",
    "DEFAULT_READ_MAX_TOKENS",
    "DEFAULT_SEARCH_MAX_RESULTS",
    "MAX_LIST_RESULTS",
    "MAX_SEARCH_RESULTS",
    "ToolExposure",
    "backend_error_to_function_call",
    "clamp_max_results",
    "memory_function_tool",
    "memory_tool_name",
    "memory_tools",
    "parse_args",
    "reject_unknown_args",
    "to_json_value",
]
