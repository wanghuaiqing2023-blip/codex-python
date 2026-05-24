"""Tool-call routing helpers ported from Codex core.

This module starts with the pure ``ToolRouter::build_tool_call`` logic from
``codex/codex-rs/core/src/tools/router.rs``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pycodex.core.tool_context import ToolPayload
from pycodex.core.tool_registry import ToolRegistry
from pycodex.protocol import ResponseItem, SearchToolCallParams, ToolName

JsonValue = Any


@dataclass(frozen=True)
class ToolCall:
    tool_name: ToolName
    call_id: str
    payload: ToolPayload


class ToolRouter:
    def __init__(
        self,
        model_visible_specs: tuple[JsonValue, ...] = (),
        registry: ToolRegistry | None = None,
    ) -> None:
        self._model_visible_specs = tuple(model_visible_specs)
        self._registry = registry or ToolRegistry.empty()

    @classmethod
    def from_parts(
        cls,
        registry_or_specs: ToolRegistry | tuple[JsonValue, ...] | list[JsonValue],
        model_visible_specs: tuple[JsonValue, ...] | list[JsonValue] | None = None,
    ) -> "ToolRouter":
        if model_visible_specs is None:
            return cls(tuple(registry_or_specs))  # type: ignore[arg-type]
        if not isinstance(registry_or_specs, ToolRegistry):
            raise TypeError("ToolRouter.from_parts(registry, specs) requires a ToolRegistry")
        return cls(tuple(model_visible_specs), registry_or_specs)

    def model_visible_specs(self) -> tuple[JsonValue, ...]:
        return self._model_visible_specs

    def registered_tool_names_for_test(self) -> tuple[ToolName, ...]:
        return self._registry.tool_names_for_test()

    def tool_exposure_for_test(self, name: ToolName) -> Any:
        return self._registry.tool_exposure(name)

    def tool_supports_parallel(self, call: ToolCall) -> bool:
        return self._registry.supports_parallel_tool_calls(call.tool_name) or False

    @staticmethod
    def build_tool_call(item: ResponseItem) -> ToolCall | None:
        return build_tool_call(item)


def build_tool_call(item: ResponseItem) -> ToolCall | None:
    if item.type == "function_call":
        return ToolCall(
            tool_name=ToolName.new(item.namespace, item.name or ""),
            call_id=item.call_id or "",
            payload=ToolPayload.function(_function_arguments(item.arguments)),
        )

    if item.type == "tool_search_call":
        if item.call_id is None or item.execution != "client":
            return None
        return ToolCall(
            tool_name=ToolName.plain("tool_search"),
            call_id=item.call_id,
            payload=ToolPayload.tool_search(_search_arguments(item.arguments)),
        )

    if item.type == "custom_tool_call":
        return ToolCall(
            tool_name=ToolName.plain(item.name or ""),
            call_id=item.call_id or "",
            payload=ToolPayload.custom(item.input or ""),
        )

    return None


def _function_arguments(arguments: str | JsonValue | None) -> str:
    if isinstance(arguments, str):
        return arguments
    if arguments is None:
        return ""
    return json.dumps(arguments, separators=(",", ":"))


def _search_arguments(arguments: str | JsonValue | None) -> SearchToolCallParams:
    try:
        if isinstance(arguments, SearchToolCallParams):
            return arguments
        if isinstance(arguments, str):
            decoded = json.loads(arguments)
        elif arguments is None:
            decoded = {}
        else:
            decoded = arguments
        return SearchToolCallParams.from_mapping(decoded)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as err:
        raise ValueError(f"failed to parse tool_search arguments: {err}") from err


__all__ = [
    "ToolCall",
    "ToolRouter",
    "build_tool_call",
]
