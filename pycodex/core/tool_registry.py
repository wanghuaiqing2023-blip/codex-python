"""Tool registry hook helpers ported from Codex core.

This module contains the pure default behavior from
``core/src/tools/registry.rs``: hook-facing payload construction, function
tool argument rewriting, and flattened tool names used at legacy boundaries.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from pycodex.core.hook_names import HookToolName
from pycodex.core.tool_context import ToolPayload
from pycodex.protocol import FunctionCallOutputPayload, ResponseInputItem, ToolName

JsonValue = Any
MULTI_AGENT_V1_NAMESPACE = "multi_agent_v1"


class ToolExposure(str, Enum):
    """Controls where a registered tool is exposed to the model."""

    DIRECT = "direct"
    DEFERRED = "deferred"
    DIRECT_MODEL_ONLY = "direct_model_only"
    HIDDEN = "hidden"

    @classmethod
    def from_value(cls, value: "ToolExposure | str") -> "ToolExposure":
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise TypeError("tool exposure must be ToolExposure or string")
        return cls(value)

    def is_direct(self) -> bool:
        return self in {ToolExposure.DIRECT, ToolExposure.DIRECT_MODEL_ONLY}


class CoreToolRuntime:
    """Minimal standard-library runtime contract for locally executed tools."""

    def tool_name(self) -> ToolName:
        raise NotImplementedError("CoreToolRuntime subclasses must implement tool_name()")

    def handle(self, invocation: "ToolInvocation") -> Any:
        raise NotImplementedError("CoreToolRuntime subclasses must implement handle()")

    def spec(self) -> JsonValue:
        return None

    def exposure(self) -> ToolExposure:
        return ToolExposure.DIRECT

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def waits_for_runtime_cancellation(self) -> bool:
        return False

    def telemetry_tags(self, invocation: "ToolInvocation") -> tuple[tuple[str, str], ...]:
        return ()

    def search_info(self) -> Any:
        return None

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def pre_tool_use_payload(self, invocation: "ToolInvocation") -> "PreToolUsePayload | None":
        return pre_tool_use_payload(invocation)

    def post_tool_use_payload(self, invocation: "ToolInvocation", result: Any) -> "PostToolUsePayload | None":
        return post_tool_use_payload(invocation, result)

    def with_updated_hook_input(self, invocation: "ToolInvocation", updated_input: JsonValue) -> "ToolInvocation":
        return with_updated_hook_input(invocation, updated_input)

    def create_diff_consumer(self) -> Any:
        return None


@dataclass(frozen=True)
class RegisteredTool(CoreToolRuntime):
    name: ToolName
    tool_spec: JsonValue = None
    exposure_value: ToolExposure = ToolExposure.DIRECT
    supports_parallel: bool = False
    waits_for_cancellation: bool = False
    payload_types: tuple[str, ...] = ("function", "tool_search")

    def __post_init__(self) -> None:
        if not isinstance(self.name, ToolName):
            raise TypeError("name must be ToolName")
        object.__setattr__(self, "exposure_value", ToolExposure.from_value(self.exposure_value))
        if not isinstance(self.supports_parallel, bool):
            raise TypeError("supports_parallel must be a bool")
        if not isinstance(self.waits_for_cancellation, bool):
            raise TypeError("waits_for_cancellation must be a bool")
        object.__setattr__(self, "payload_types", _string_tuple(self.payload_types, "payload_types"))

    @classmethod
    def plain(
        cls,
        name: str,
        *,
        tool_spec: JsonValue = None,
        exposure: ToolExposure | str = ToolExposure.DIRECT,
        supports_parallel: bool = False,
        waits_for_cancellation: bool = False,
        payload_types: tuple[str, ...] = ("function", "tool_search"),
    ) -> "RegisteredTool":
        return cls(
            name=ToolName.plain(name),
            tool_spec=tool_spec,
            exposure_value=ToolExposure.from_value(exposure),
            supports_parallel=supports_parallel,
            waits_for_cancellation=waits_for_cancellation,
            payload_types=payload_types,
        )

    @classmethod
    def namespaced(
        cls,
        namespace: str,
        name: str,
        *,
        tool_spec: JsonValue = None,
        exposure: ToolExposure | str = ToolExposure.DIRECT,
        supports_parallel: bool = False,
        waits_for_cancellation: bool = False,
        payload_types: tuple[str, ...] = ("function", "tool_search"),
    ) -> "RegisteredTool":
        return cls(
            name=ToolName.namespaced(namespace, name),
            tool_spec=tool_spec,
            exposure_value=ToolExposure.from_value(exposure),
            supports_parallel=supports_parallel,
            waits_for_cancellation=waits_for_cancellation,
            payload_types=payload_types,
        )

    def tool_name(self) -> ToolName:
        return self.name

    def spec(self) -> JsonValue:
        return self.tool_spec

    def exposure(self) -> ToolExposure:
        return self.exposure_value

    def supports_parallel_tool_calls(self) -> bool:
        return self.exposure_value is not ToolExposure.HIDDEN and self.supports_parallel

    def waits_for_runtime_cancellation(self) -> bool:
        return self.waits_for_cancellation

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in self.payload_types


@dataclass(frozen=True)
class ExposureOverride(CoreToolRuntime):
    handler: Any
    exposure_value: ToolExposure

    def __post_init__(self) -> None:
        _runtime_tool_name(self.handler)
        object.__setattr__(self, "exposure_value", ToolExposure.from_value(self.exposure_value))

    def tool_name(self) -> ToolName:
        return _runtime_tool_name(self.handler)

    def handle(self, invocation: "ToolInvocation") -> Any:
        return _runtime_handle(self.handler, invocation)

    def spec(self) -> JsonValue:
        return _runtime_spec(self.handler)

    def exposure(self) -> ToolExposure:
        return self.exposure_value

    def supports_parallel_tool_calls(self) -> bool:
        return self.exposure_value is not ToolExposure.HIDDEN and _runtime_supports_parallel_tool_calls(self.handler)

    def waits_for_runtime_cancellation(self) -> bool:
        return _runtime_waits_for_runtime_cancellation(self.handler)

    def telemetry_tags(self, invocation: "ToolInvocation") -> Any:
        return _runtime_telemetry_tags(self.handler, invocation)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return _runtime_matches_kind(self.handler, payload)

    def pre_tool_use_payload(self, invocation: "ToolInvocation") -> "PreToolUsePayload | None":
        return _runtime_pre_tool_use_payload(self.handler, invocation)

    def post_tool_use_payload(self, invocation: "ToolInvocation", result: Any) -> "PostToolUsePayload | None":
        return _runtime_post_tool_use_payload(self.handler, invocation, result)

    def with_updated_hook_input(self, invocation: "ToolInvocation", updated_input: JsonValue) -> "ToolInvocation":
        return _runtime_with_updated_hook_input(self.handler, invocation, updated_input)

    def search_info(self) -> Any:
        return _runtime_search_info(self.handler)

    def create_diff_consumer(self) -> Any:
        return _runtime_create_diff_consumer(self.handler)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.handler, name)


class ToolRegistry:
    def __init__(self, tools: Mapping[ToolName, Any] | None = None) -> None:
        if tools is None:
            self._tools = {}
            return
        if not isinstance(tools, Mapping):
            raise TypeError("tools must be a mapping")
        tools_by_name: dict[ToolName, Any] = {}
        for name, tool in tools.items():
            if not isinstance(name, ToolName):
                raise TypeError("tool registry keys must be ToolName")
            if _runtime_tool_name(tool) != name:
                raise ValueError("tool registry key must match handler tool_name")
            tools_by_name[name] = tool
        self._tools = tools_by_name

    @classmethod
    def new(cls, tools: Mapping[ToolName, Any]) -> "ToolRegistry":
        return cls(tools)

    @classmethod
    def empty(cls) -> "ToolRegistry":
        return cls()

    @classmethod
    def empty_for_test(cls) -> "ToolRegistry":
        return cls.empty()

    @classmethod
    def from_tools(cls, tools: Iterable[Any] | Mapping[Any, Any]) -> "ToolRegistry":
        tools_by_name: dict[ToolName, Any] = {}
        if isinstance(tools, (str, bytes)) or not isinstance(tools, Iterable):
            raise TypeError("tools must be an iterable of tool runtimes")
        values = tools.values() if isinstance(tools, Mapping) else tools
        for tool in values:
            name = _runtime_tool_name(tool)
            if name in tools_by_name:
                raise ValueError(f"tool {name} already registered")
            tools_by_name[name] = tool
        return cls.new(tools_by_name)

    @classmethod
    def with_handler_for_test(cls, handler: Any) -> "ToolRegistry":
        return cls.from_tools([handler])

    def tool(self, name: ToolName) -> Any | None:
        if not isinstance(name, ToolName):
            raise TypeError("name must be ToolName")
        return self._tools.get(name)

    def tool_names(self) -> tuple[ToolName, ...]:
        return tuple(sorted(self._tools))

    def tool_names_for_test(self) -> tuple[ToolName, ...]:
        return self.tool_names()

    def tool_exposure(self, name: ToolName) -> ToolExposure | None:
        tool = self.tool(name)
        if tool is None:
            return None
        return _runtime_exposure(tool)

    def create_diff_consumer(self, name: ToolName) -> Any:
        if not isinstance(name, ToolName):
            raise TypeError("name must be ToolName")
        tool = self.tool(name)
        if tool is None:
            return None
        return _runtime_create_diff_consumer(tool)

    def supports_parallel_tool_calls(self, name: ToolName) -> bool | None:
        tool = self.tool(name)
        if tool is None:
            return None
        return _runtime_supports_parallel_tool_calls(tool)

    def waits_for_runtime_cancellation(self, name: ToolName) -> bool | None:
        tool = self.tool(name)
        if tool is None:
            return None
        return _runtime_waits_for_runtime_cancellation(tool)

    def matches_kind(self, name: ToolName, payload: ToolPayload) -> bool | None:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        tool = self.tool(name)
        if tool is None:
            return None
        return _runtime_matches_kind(tool, payload)

    def search_infos(self) -> tuple[Any, ...]:
        return tuple(
            search_info
            for search_info in (_runtime_search_info(tool) for tool in self._tools.values())
            if search_info is not None
        )


@dataclass(frozen=True)
class ToolCallSource:
    type: str
    cell_id: str | None = None
    runtime_tool_call_id: str | None = None

    @classmethod
    def direct(cls) -> "ToolCallSource":
        return cls(type="direct")

    @classmethod
    def code_mode(cls, cell_id: str, runtime_tool_call_id: str) -> "ToolCallSource":
        return cls(type="code_mode", cell_id=cell_id, runtime_tool_call_id=runtime_tool_call_id)

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type == "direct":
            if self.cell_id is not None or self.runtime_tool_call_id is not None:
                raise ValueError("direct tool call source must not include code-mode ids")
            return
        if self.type == "code_mode":
            if not isinstance(self.cell_id, str) or not isinstance(self.runtime_tool_call_id, str):
                raise TypeError("code_mode source requires string cell_id and runtime_tool_call_id")
            return
        raise ValueError(f"unknown tool call source type: {self.type}")

    @property
    def is_direct(self) -> bool:
        return self.type == "direct"

    @property
    def is_code_mode(self) -> bool:
        return self.type == "code_mode"


@dataclass(frozen=True)
class ToolInvocation:
    call_id: str
    tool_name: ToolName | str
    payload: ToolPayload
    source: ToolCallSource = field(default_factory=ToolCallSource.direct)
    session: Any = None
    turn: Any = None
    cancellation_token: Any = None
    tracker: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id:
            raise TypeError("call_id must be a non-empty string")
        try:
            tool_name = ToolName.from_value(self.tool_name)
        except TypeError as exc:
            raise TypeError("tool_name must be ToolName or string") from exc
        if not tool_name.name:
            raise TypeError("tool_name must be non-empty")
        object.__setattr__(self, "tool_name", tool_name)
        if not isinstance(self.payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        if not isinstance(self.source, ToolCallSource):
            raise TypeError("source must be ToolCallSource")

    @property
    def is_code_mode(self) -> bool:
        return self.source.is_code_mode


@dataclass(frozen=True)
class PreToolUsePayload:
    tool_name: HookToolName
    tool_input: JsonValue

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, HookToolName):
            raise TypeError("tool_name must be HookToolName")


@dataclass(frozen=True)
class PostToolUsePayload:
    tool_name: HookToolName
    tool_use_id: str
    tool_input: JsonValue
    tool_response: JsonValue

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, HookToolName):
            raise TypeError("tool_name must be HookToolName")
        if not isinstance(self.tool_use_id, str):
            raise TypeError("tool_use_id must be a string")


def flat_tool_name(tool_name: ToolName) -> str:
    if not isinstance(tool_name, ToolName):
        raise TypeError("tool_name must be ToolName")
    if tool_name.namespace is None:
        return tool_name.name
    return f"{tool_name.namespace}{tool_name.name}"


def function_hook_tool_name(invocation: ToolInvocation) -> HookToolName:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    tool_name = invocation.tool_name
    if tool_name.name == "spawn_agent" and tool_name.namespace in {None, MULTI_AGENT_V1_NAMESPACE}:
        return HookToolName.spawn_agent()
    return HookToolName.new(flat_tool_name(tool_name))


def function_hook_tool_input(arguments: str) -> JsonValue:
    if not isinstance(arguments, str):
        raise TypeError("arguments must be a string")
    if arguments.strip() == "":
        return {}
    try:
        return json.loads(arguments)
    except json.JSONDecodeError:
        return arguments


def pre_tool_use_payload(invocation: ToolInvocation) -> PreToolUsePayload | None:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    if invocation.payload.type != "function":
        return None
    return PreToolUsePayload(
        tool_name=function_hook_tool_name(invocation),
        tool_input=function_hook_tool_input(invocation.payload.arguments or ""),
    )


def post_tool_use_payload(invocation: ToolInvocation, result: Any) -> PostToolUsePayload | None:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    if invocation.payload.type != "function":
        return None

    arguments = invocation.payload.arguments or ""
    tool_input = _call_optional_result_method(result, "post_tool_use_input", invocation.payload)
    if tool_input is None:
        tool_input = function_hook_tool_input(arguments)

    tool_response = _call_optional_result_method(
        result,
        "post_tool_use_response",
        invocation.call_id,
        invocation.payload,
    )
    if tool_response is None:
        tool_response = _model_visible_tool_response(result, invocation)
    if tool_response is None:
        return None

    return PostToolUsePayload(
        tool_name=function_hook_tool_name(invocation),
        tool_use_id=_post_tool_use_id(result, invocation.call_id),
        tool_input=tool_input,
        tool_response=tool_response,
    )


def with_updated_hook_input(invocation: ToolInvocation, updated_input: JsonValue) -> ToolInvocation:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    if invocation.payload.type != "function":
        raise ValueError("hook input rewrite received unsupported function tool payload")
    try:
        arguments = json.dumps(updated_input, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as err:
        raise ValueError(f"failed to serialize rewritten {flat_tool_name(invocation.tool_name)} arguments: {err}") from err
    return replace(invocation, payload=ToolPayload.function(arguments))


def _call_optional_result_method(result: Any, name: str, *args: Any) -> JsonValue | None:
    method = getattr(result, name, None)
    if method is None:
        return None
    return method(*args)


def _post_tool_use_id(result: Any, call_id: str) -> str:
    method = getattr(result, "post_tool_use_id", None)
    if method is None:
        return call_id
    value = method(call_id)
    if not isinstance(value, str):
        raise TypeError("post_tool_use_id must return a string")
    return value


def _model_visible_tool_response(result: Any, invocation: ToolInvocation) -> JsonValue | None:
    method = getattr(result, "to_response_item", None)
    if method is None:
        return None
    response = method(invocation.call_id, invocation.payload)
    if not isinstance(response, ResponseInputItem) or response.type != "function_call_output":
        return None
    output = response.output
    if isinstance(output, FunctionCallOutputPayload):
        return output.to_json()
    return output


def override_tool_exposure(handler: Any, exposure: ToolExposure | str) -> Any:
    exposure = ToolExposure.from_value(exposure)
    if _runtime_exposure(handler) is exposure:
        return handler
    return ExposureOverride(handler=handler, exposure_value=exposure)


def unsupported_tool_call_message(payload: ToolPayload, tool_name: ToolName) -> str:
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    if not isinstance(tool_name, ToolName):
        raise TypeError("tool_name must be ToolName")
    if payload.type == "custom":
        return f"unsupported custom tool call: {tool_name}"
    return f"unsupported call: {tool_name}"


def _runtime_tool_name(handler: Any) -> ToolName:
    value = _call_or_get(handler, "tool_name", None)
    if value is None:
        value = _call_or_get(handler, "name", None)
    try:
        return ToolName.from_value(value)
    except TypeError as err:
        raise TypeError("registered tool must expose a ToolName via tool_name() or name") from err


def _runtime_handle(handler: Any, invocation: ToolInvocation) -> Any:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    method = _field_or_attr(handler, "handle", None)
    if method is None:
        raise TypeError("registered tool must expose handle(invocation)")
    if not callable(method):
        raise TypeError("registered tool must expose handle(invocation)")
    return method(invocation)


def _runtime_spec(handler: Any) -> JsonValue:
    return _call_or_get(handler, "spec", None)


def _runtime_exposure(handler: Any) -> ToolExposure:
    return ToolExposure.from_value(_call_or_get(handler, "exposure", ToolExposure.DIRECT))


def _runtime_supports_parallel_tool_calls(handler: Any) -> bool:
    value = _call_or_get(handler, "supports_parallel_tool_calls", False)
    if not isinstance(value, bool):
        raise TypeError("supports_parallel_tool_calls must return a bool")
    return value


def _runtime_waits_for_runtime_cancellation(handler: Any) -> bool:
    value = _call_or_get(handler, "waits_for_runtime_cancellation", False)
    if not isinstance(value, bool):
        raise TypeError("waits_for_runtime_cancellation must return a bool")
    return value


def _runtime_telemetry_tags(handler: Any, invocation: ToolInvocation) -> Any:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    method = _field_or_attr(handler, "telemetry_tags", None)
    if method is None:
        return ()
    if not callable(method):
        return ()
    return method(invocation)


def _runtime_matches_kind(handler: Any, payload: ToolPayload) -> bool:
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be ToolPayload")
    matches_kind = _field_or_attr(handler, "matches_kind", None)
    if matches_kind is None:
        return payload.type in {"function", "tool_search"}
    if not callable(matches_kind):
        raise TypeError("matches_kind must be callable")
    value = matches_kind(payload)
    if not isinstance(value, bool):
        raise TypeError("matches_kind must return a bool")
    return value


def _runtime_pre_tool_use_payload(handler: Any, invocation: ToolInvocation) -> PreToolUsePayload | None:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    method = _field_or_attr(handler, "pre_tool_use_payload", None)
    if method is None:
        return pre_tool_use_payload(invocation)
    if not callable(method):
        raise TypeError("pre_tool_use_payload must be callable")
    value = method(invocation)
    if value is not None and not isinstance(value, PreToolUsePayload):
        raise TypeError("pre_tool_use_payload must return PreToolUsePayload or None")
    return value


def _runtime_post_tool_use_payload(
    handler: Any,
    invocation: ToolInvocation,
    result: Any,
) -> PostToolUsePayload | None:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    method = _field_or_attr(handler, "post_tool_use_payload", None)
    if method is None:
        return post_tool_use_payload(invocation, result)
    if not callable(method):
        raise TypeError("post_tool_use_payload must be callable")
    value = method(invocation, result)
    if value is not None and not isinstance(value, PostToolUsePayload):
        raise TypeError("post_tool_use_payload must return PostToolUsePayload or None")
    return value


def _runtime_with_updated_hook_input(
    handler: Any,
    invocation: ToolInvocation,
    updated_input: JsonValue,
) -> ToolInvocation:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    method = _field_or_attr(handler, "with_updated_hook_input", None)
    if method is None:
        return with_updated_hook_input(invocation, updated_input)
    if not callable(method):
        raise TypeError("with_updated_hook_input must be callable")
    value = method(invocation, updated_input)
    if not isinstance(value, ToolInvocation):
        raise TypeError("with_updated_hook_input must return ToolInvocation")
    return value


def _runtime_search_info(handler: Any) -> Any:
    method = _field_or_attr(handler, "search_info", None)
    if method is None:
        return None
    if not callable(method):
        return method
    return method()


def _runtime_create_diff_consumer(handler: Any) -> Any:
    method = _field_or_attr(handler, "create_diff_consumer", None)
    if method is None:
        return None
    if not callable(method):
        return method
    return method()


def _call_or_get(handler: Any, name: str, default: Any) -> Any:
    value = _field_or_attr(handler, name, default)
    if callable(value):
        return value()
    return value


def _field_or_attr(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping) and name in value:
        return value[name]
    return getattr(value, name, default)


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be strings")
        result.append(item)
    return tuple(result)


__all__ = [
    "CoreToolRuntime",
    "ExposureOverride",
    "MULTI_AGENT_V1_NAMESPACE",
    "PostToolUsePayload",
    "PreToolUsePayload",
    "RegisteredTool",
    "ToolCallSource",
    "ToolExposure",
    "ToolInvocation",
    "ToolRegistry",
    "flat_tool_name",
    "function_hook_tool_input",
    "function_hook_tool_name",
    "override_tool_exposure",
    "post_tool_use_payload",
    "pre_tool_use_payload",
    "unsupported_tool_call_message",
    "with_updated_hook_input",
]
