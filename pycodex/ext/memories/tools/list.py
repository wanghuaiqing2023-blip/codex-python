"""List tool from Rust ``memories/src/tools/list.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.ext.extension_api import FunctionCallError, JsonToolOutput

from ..backend import ListMemoriesRequest, ListMemoriesResponse
from ..metrics import record_tool_call, scope_from_optional_path, truncated_tag
from . import (
    DEFAULT_LIST_MAX_RESULTS,
    MAX_LIST_RESULTS,
    backend_error_to_function_call,
    clamp_max_results,
    memory_function_tool,
    memory_tool_name,
    parse_args,
    reject_unknown_args,
    to_json_value,
)

LIST_TOOL_NAME = "list"


@dataclass(frozen=True)
class ListArgs:
    path: str | None = None
    cursor: str | None = None
    max_results: int | None = None


@dataclass
class ListTool:
    backend: Any
    metrics_client: Any = None

    def tool_name(self) -> Any:
        return memory_tool_name(LIST_TOOL_NAME)

    def spec(self) -> Any:
        return memory_function_tool(
            LIST_TOOL_NAME,
            "List immediate files and directories under a path in the Codex memories store.",
            ListArgs,
            ListMemoriesResponse,
        )

    async def handle(self, call: Any) -> JsonToolOutput:
        args = parse_args(call)
        reject_unknown_args(args, {"path", "cursor", "max_results"})
        path = _optional_string(args, "path")
        cursor = _optional_string(args, "cursor")
        max_results = _optional_int(args, "max_results")
        scope = scope_from_optional_path(path, "root")
        try:
            response = await self.backend.list(
                ListMemoriesRequest(
                    path=path,
                    cursor=cursor,
                    max_results=clamp_max_results(
                        max_results,
                        DEFAULT_LIST_MAX_RESULTS,
                        MAX_LIST_RESULTS,
                    ),
                )
            )
        except Exception as error:
            record_tool_call(self.metrics_client, LIST_TOOL_NAME, scope, False, "unknown")
            raise backend_error_to_function_call(error) from error
        record_tool_call(
            self.metrics_client,
            LIST_TOOL_NAME,
            scope,
            True,
            truncated_tag(response.truncated),
        )
        return JsonToolOutput.new(to_json_value(response))


def _optional_string(args: dict[str, Any], name: str) -> str | None:
    value = args.get(name)
    if value is not None and not isinstance(value, str):
        raise FunctionCallError.respond_to_model(f"{name} must be a string")
    return value


def _optional_int(args: dict[str, Any], name: str) -> int | None:
    value = args.get(name)
    if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        raise FunctionCallError.respond_to_model(f"{name} must be an integer")
    return value


__all__ = ["ListArgs", "ListTool"]
