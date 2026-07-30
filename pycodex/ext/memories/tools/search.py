"""Search tool from Rust ``memories/src/tools/search.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.ext.extension_api import FunctionCallError, JsonToolOutput

from ..backend import (
    SearchMatchMode,
    SearchMemoriesRequest,
    SearchMemoriesResponse,
)
from ..metrics import record_tool_call, scope_from_optional_path, truncated_tag
from . import (
    DEFAULT_SEARCH_MAX_RESULTS,
    MAX_SEARCH_RESULTS,
    backend_error_to_function_call,
    clamp_max_results,
    memory_function_tool,
    memory_tool_name,
    parse_args,
    reject_unknown_args,
    to_json_value,
)

SEARCH_TOOL_NAME = "search"


@dataclass(frozen=True)
class SearchArgs:
    queries: tuple[str, ...]
    match_mode: SearchMatchMode | None = None
    path: str | None = None
    cursor: str | None = None
    context_lines: int | None = None
    case_sensitive: bool | None = None
    normalized: bool | None = None
    max_results: int | None = None


@dataclass
class SearchTool:
    backend: Any
    metrics_client: Any = None

    def tool_name(self) -> Any:
        return memory_tool_name(SEARCH_TOOL_NAME)

    def spec(self) -> Any:
        return memory_function_tool(
            SEARCH_TOOL_NAME,
            "Search Codex memory files for substring matches, optionally normalizing separators or requiring all query substrings on the same line or within a line window.",
            SearchArgs,
            SearchMemoriesResponse,
        )

    async def handle(self, call: Any) -> JsonToolOutput:
        args = parse_args(call)
        reject_unknown_args(
            args,
            {
                "queries",
                "match_mode",
                "path",
                "cursor",
                "context_lines",
                "case_sensitive",
                "normalized",
                "max_results",
            },
        )
        request = _request_from_args(args)
        scope = scope_from_optional_path(request.path, "all")
        try:
            response = await self.backend.search(request)
        except Exception as error:
            record_tool_call(self.metrics_client, SEARCH_TOOL_NAME, scope, False, "unknown")
            raise backend_error_to_function_call(error) from error
        record_tool_call(
            self.metrics_client,
            SEARCH_TOOL_NAME,
            scope,
            True,
            truncated_tag(response.truncated),
        )
        return JsonToolOutput.new(to_json_value(response))


def _request_from_args(args: dict[str, Any]) -> SearchMemoriesRequest:
    queries = args.get("queries")
    if not isinstance(queries, list) or not queries or not all(
        isinstance(query, str) and query for query in queries
    ):
        raise FunctionCallError.respond_to_model(
            "queries must be a non-empty array of non-empty strings"
        )
    path = _optional_string(args, "path")
    cursor = _optional_string(args, "cursor")
    context_lines = _non_negative_optional_int(args, "context_lines")
    max_results = _positive_optional_int(args, "max_results")
    return SearchMemoriesRequest(
        queries=tuple(queries),
        match_mode=_match_mode(args.get("match_mode")),
        path=path,
        cursor=cursor,
        context_lines=0 if context_lines is None else context_lines,
        case_sensitive=_optional_bool(args, "case_sensitive", True),
        normalized=_optional_bool(args, "normalized", False),
        max_results=clamp_max_results(
            max_results,
            DEFAULT_SEARCH_MAX_RESULTS,
            MAX_SEARCH_RESULTS,
        ),
    )


def _match_mode(value: Any) -> SearchMatchMode:
    if value is None or value == "any":
        return SearchMatchMode.any()
    if value == "all_on_same_line":
        return SearchMatchMode.all_on_same_line()
    if isinstance(value, dict) and set(value) == {"all_within_lines"}:
        count = value["all_within_lines"]
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            return SearchMatchMode.all_within_lines(count)
    raise FunctionCallError.respond_to_model("invalid match_mode")


def _optional_string(args: dict[str, Any], name: str) -> str | None:
    value = args.get(name)
    if value is not None and not isinstance(value, str):
        raise FunctionCallError.respond_to_model(f"{name} must be a string")
    return value


def _non_negative_optional_int(args: dict[str, Any], name: str) -> int | None:
    value = args.get(name)
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise FunctionCallError.respond_to_model(
            f"{name} must be a non-negative integer"
        )
    return value


def _positive_optional_int(args: dict[str, Any], name: str) -> int | None:
    value = args.get(name)
    if value is not None and (
        not isinstance(value, int) or isinstance(value, bool) or value < 1
    ):
        raise FunctionCallError.respond_to_model(f"{name} must be a positive integer")
    return value


def _optional_bool(args: dict[str, Any], name: str, default: bool) -> bool:
    value = args.get(name, default)
    if not isinstance(value, bool):
        raise FunctionCallError.respond_to_model(f"{name} must be a boolean")
    return value


__all__ = ["SearchArgs", "SearchTool"]
