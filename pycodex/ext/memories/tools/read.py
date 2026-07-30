"""Read tool from Rust ``memories/src/tools/read.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.ext.extension_api import FunctionCallError, JsonToolOutput

from ..backend import ReadMemoryRequest, ReadMemoryResponse
from ..metrics import record_tool_call, scope_from_path, truncated_tag
from . import (
    DEFAULT_READ_MAX_TOKENS,
    backend_error_to_function_call,
    memory_function_tool,
    memory_tool_name,
    parse_args,
    reject_unknown_args,
    to_json_value,
)

READ_TOOL_NAME = "read"


@dataclass(frozen=True)
class ReadArgs:
    path: str
    line_offset: int | None = None
    max_lines: int | None = None


@dataclass
class ReadTool:
    backend: Any
    metrics_client: Any = None

    def tool_name(self) -> Any:
        return memory_tool_name(READ_TOOL_NAME)

    def spec(self) -> Any:
        return memory_function_tool(
            READ_TOOL_NAME,
            "Read a Codex memory file by relative path, optionally starting at a 1-indexed line offset and limiting the number of lines returned.",
            ReadArgs,
            ReadMemoryResponse,
        )

    async def handle(self, call: Any) -> JsonToolOutput:
        args = parse_args(call)
        reject_unknown_args(args, {"path", "line_offset", "max_lines"})
        path = args.get("path")
        if not isinstance(path, str):
            raise FunctionCallError.respond_to_model("path must be a string")
        line_offset = _positive_optional_int(args, "line_offset")
        max_lines = _positive_optional_int(args, "max_lines")
        scope = scope_from_path(path)
        try:
            response = await self.backend.read(
                ReadMemoryRequest(
                    path=path,
                    line_offset=1 if line_offset is None else line_offset,
                    max_lines=max_lines,
                    max_tokens=DEFAULT_READ_MAX_TOKENS,
                )
            )
        except Exception as error:
            record_tool_call(self.metrics_client, READ_TOOL_NAME, scope, False, "unknown")
            raise backend_error_to_function_call(error) from error
        record_tool_call(
            self.metrics_client,
            READ_TOOL_NAME,
            scope,
            True,
            truncated_tag(response.truncated),
        )
        return JsonToolOutput.new(to_json_value(response))


def _positive_optional_int(args: dict[str, Any], name: str) -> int | None:
    value = args.get(name)
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 1
    ):
        raise FunctionCallError.respond_to_model(f"{name} must be a positive integer")
    return value


__all__ = ["ReadArgs", "ReadTool"]
