"""Standalone web-search tool from Rust ``web-search/src/tool.rs``."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pycodex.codex_api import (
    ClickOperation,
    FinanceAssetType,
    FinanceOperation,
    FindOperation,
    OpenOperation,
    ReqwestTransport,
    ScreenshotOperation,
    SearchClient,
    SearchCommands,
    SearchQuery,
    SearchRequest,
    SearchResponseLength,
    SportsFunction,
    SportsLeague,
    SportsOperation,
    SportsToolName,
    TimeOperation,
    WeatherOperation,
)
from pycodex.extension_api import FunctionCallError, ToolName
from pycodex.tools import (
    ResponsesApiNamespace,
    ResponsesApiNamespaceTool,
    ResponsesApiTool,
    ResponsesToolSpec,
    ToolExposure,
    default_namespace_description,
    parse_tool_input_schema_without_compaction,
)

from .history import recent_input
from .output import EncryptedSearchOutput
from .schema import commands_schema

WEB_NAMESPACE = "web"
RUN_TOOL_NAME = "run"
_DESCRIPTION_PATH = Path(__file__).parent / "web_run_description.md"


@dataclass
class WebSearchTool:
    session_id: str
    provider: Any
    settings: Any

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(WEB_NAMESPACE, RUN_TOOL_NAME)

    def spec(self) -> ResponsesToolSpec:
        parameters = parse_tool_input_schema_without_compaction(commands_schema())
        tool = ResponsesApiTool(
            name=RUN_TOOL_NAME,
            description=_DESCRIPTION_PATH.read_text(encoding="utf-8"),
            strict=False,
            parameters=parameters.to_mapping(),
            output_schema=None,
            defer_loading=None,
        )
        return ResponsesToolSpec.namespace(
            ResponsesApiNamespace(
                name=WEB_NAMESPACE,
                description=default_namespace_description(WEB_NAMESPACE),
                tools=(ResponsesApiNamespaceTool.from_function(tool),),
            )
        )

    def exposure(self) -> ToolExposure:
        return ToolExposure.DIRECT_MODEL_ONLY

    async def handle(self, call: Any) -> EncryptedSearchOutput:
        commands = parse_commands(call)
        try:
            provider = await self.provider.api_provider()
            auth = await self.provider.api_auth()
            response = await SearchClient(
                ReqwestTransport(),
                provider,
                auth,
            ).search(
                SearchRequest(
                    id=self.session_id,
                    input=recent_input(call.conversation_history.items),
                    commands=commands,
                    settings=self.settings,
                    max_output_tokens=(
                        call.truncation_policy.limit
                        if call.truncation_policy is not None
                        else None
                    ),
                ),
                {},
            )
        except FunctionCallError:
            raise
        except Exception as error:
            raise FunctionCallError.fatal(str(error)) from error
        return EncryptedSearchOutput.new(response.encrypted_output)


def parse_commands(call: Any) -> SearchCommands:
    arguments = call.function_arguments()
    if not arguments.strip():
        return SearchCommands()
    try:
        value = json.loads(arguments)
        if not isinstance(value, dict):
            raise TypeError("search commands must be an object")
        return _commands_from_mapping(value)
    except (TypeError, ValueError) as error:
        raise FunctionCallError.respond_to_model(str(error)) from error


def _commands_from_mapping(value: dict[str, Any]) -> SearchCommands:
    allowed = {
        "search_query",
        "image_query",
        "open",
        "click",
        "find",
        "screenshot",
        "finance",
        "weather",
        "sports",
        "time",
        "response_length",
    }
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"unknown field: {sorted(unknown)[0]}")
    return SearchCommands(
        search_query=_items(value, "search_query", SearchQuery),
        image_query=_items(value, "image_query", SearchQuery),
        open=_items(value, "open", OpenOperation),
        click=_items(value, "click", ClickOperation),
        find=_items(value, "find", FindOperation),
        screenshot=_items(value, "screenshot", ScreenshotOperation),
        finance=_items(value, "finance", FinanceOperation, {"type": FinanceAssetType}),
        weather=_items(value, "weather", WeatherOperation),
        sports=_items(
            value,
            "sports",
            SportsOperation,
            {"fn": SportsFunction, "league": SportsLeague, "tool": SportsToolName},
        ),
        time=_items(value, "time", TimeOperation),
        response_length=(
            None
            if value.get("response_length") is None
            else SearchResponseLength(value["response_length"])
        ),
    )


def _items(
    value: dict[str, Any],
    key: str,
    item_type: type[Any],
    enums: dict[str, type[Any]] | None = None,
) -> tuple[Any, ...] | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise TypeError(f"{key} must be an array")
    result = []
    for item in raw:
        if not isinstance(item, dict):
            raise TypeError(f"{key} items must be objects")
        fields = dict(item)
        for name, enum_type in (enums or {}).items():
            if fields.get(name) is not None:
                fields[name] = enum_type(fields[name])
        result.append(item_type(**fields))
    return tuple(result)


__all__ = ["WebSearchTool", "parse_commands"]
