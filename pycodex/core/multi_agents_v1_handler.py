"""Multi-agent v1 handler facades ported from Codex core.

These helpers mirror the pure boundary layer from
``core/src/tools/handlers/multi_agents``: namespaced tool names, argument
parsing, target id validation, v1 wait timeout semantics, result serialization,
and tool-search metadata. Real ``agent_control`` operations are represented by
small callbacks so this port stays stdlib-only.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Callable

from pycodex.core.multi_agents_common import (
    DEFAULT_WAIT_TIMEOUT_MS,
    MAX_WAIT_TIMEOUT_MS,
    MIN_WAIT_TIMEOUT_MS,
    function_arguments,
    parse_collab_input,
    reject_full_fork_spawn_overrides,
    tool_output_code_mode_result,
    tool_output_json_text,
    tool_output_response_item,
)
from pycodex.core.multi_agents_spec import (
    MULTI_AGENT_V1_NAMESPACE,
    SpawnAgentToolOptions,
    WaitAgentTimeoutOptions,
    create_close_agent_tool_v1,
    create_send_input_tool_v1,
    create_spawn_agent_tool_v1,
    create_wait_agent_tool_v1,
)
from pycodex.core.tool_context import ToolPayload
from pycodex.core.tool_registry import ToolInvocation
from pycodex.core.tool_search_entry import ToolSearchInfo, ToolSearchSourceInfo
from pycodex.core.tool_router import FunctionCallError
from pycodex.protocol import AgentStatus, ResponseInputItem, ThreadId, ToolName, UserInput

JsonValue = Any
MULTI_AGENT_TOOL_SEARCH_SOURCE_NAME = "Multi-agent tools"
MULTI_AGENT_TOOL_SEARCH_SOURCE_DESCRIPTION = "Spawn and manage sub-agents."


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _json_mapping(arguments: str, label: str) -> dict[str, JsonValue]:
    return _mapping(json.loads(arguments), label)


def _required_str(data: dict[str, JsonValue], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _optional_str(data: dict[str, JsonValue], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _optional_int(data: dict[str, JsonValue], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _optional_bool(data: dict[str, JsonValue], key: str, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a bool")
    return value


def _optional_items(data: dict[str, JsonValue], key: str) -> tuple[UserInput, ...] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError(f"{key} must be a list")
    return tuple(UserInput.from_mapping(item) for item in value)


def parse_agent_id_target(target: str) -> ThreadId:
    if not isinstance(target, str):
        raise TypeError("target must be a string")
    try:
        return ThreadId.from_string(target)
    except Exception as err:
        raise FunctionCallError.respond_to_model(f"invalid agent id {target}: {err!r}") from err


def parse_agent_id_targets(targets: Iterable[str]) -> tuple[ThreadId, ...]:
    if isinstance(targets, (str, bytes)):
        raise TypeError("targets must be an iterable of strings")
    parsed_targets = tuple(targets)
    if not parsed_targets:
        raise FunctionCallError.respond_to_model("agent ids must be non-empty")
    return tuple(parse_agent_id_target(target) for target in parsed_targets)


def multi_agent_tool_search_info(search_text: str, spec: JsonValue) -> ToolSearchInfo | None:
    return ToolSearchInfo.from_spec(
        search_text,
        spec,
        ToolSearchSourceInfo(
            MULTI_AGENT_TOOL_SEARCH_SOURCE_NAME,
            MULTI_AGENT_TOOL_SEARCH_SOURCE_DESCRIPTION,
        ),
    )


@dataclass(frozen=True)
class V1SpawnAgentArgs:
    message: str | None = None
    items: tuple[UserInput, ...] | None = None
    agent_type: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    fork_context: bool = False

    @classmethod
    def from_json(cls, arguments: str) -> "V1SpawnAgentArgs":
        data = _json_mapping(arguments, "spawn_agent arguments")
        return cls(
            message=_optional_str(data, "message"),
            items=_optional_items(data, "items"),
            agent_type=_optional_str(data, "agent_type"),
            model=_optional_str(data, "model"),
            reasoning_effort=_optional_str(data, "reasoning_effort"),
            service_tier=_optional_str(data, "service_tier"),
            fork_context=_optional_bool(data, "fork_context", False),
        )

    def role_name(self) -> str | None:
        if self.agent_type is None:
            return None
        role = self.agent_type.strip()
        return role or None

    def input_items(self) -> tuple[UserInput, ...]:
        return parse_collab_input(self.message, self.items)

    def validate_for_spawn(self) -> None:
        self.input_items()
        if self.fork_context:
            reject_full_fork_spawn_overrides(self.role_name(), self.model, self.reasoning_effort)


@dataclass(frozen=True)
class V1SpawnAgentResult:
    agent_id: str
    nickname: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str):
            raise TypeError("agent_id must be a string")
        if self.nickname is not None and not isinstance(self.nickname, str):
            raise TypeError("nickname must be a string")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"agent_id": self.agent_id, "nickname": self.nickname}

    def log_preview(self) -> str:
        return tool_output_json_text(self, "spawn_agent")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, "spawn_agent")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "spawn_agent")


@dataclass(frozen=True)
class SendInputArgs:
    target: str
    message: str | None = None
    items: tuple[UserInput, ...] | None = None
    interrupt: bool = False

    @classmethod
    def from_json(cls, arguments: str) -> "SendInputArgs":
        data = _json_mapping(arguments, "send_input arguments")
        items = data.get("items")
        return cls(
            target=_required_str(data, "target"),
            message=_optional_str(data, "message"),
            items=tuple(UserInput.from_mapping(item) for item in items) if items is not None else None,
            interrupt=_optional_bool(data, "interrupt", False),
        )

    def receiver_thread_id(self) -> ThreadId:
        return parse_agent_id_target(self.target)

    def input_items(self) -> tuple[UserInput, ...]:
        return parse_collab_input(self.message, self.items)


@dataclass(frozen=True)
class SendInputResult:
    submission_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.submission_id, str):
            raise TypeError("submission_id must be a string")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"submission_id": self.submission_id}

    def log_preview(self) -> str:
        return tool_output_json_text(self, "send_input")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, "send_input")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "send_input")


@dataclass(frozen=True)
class V1CloseAgentArgs:
    target: str

    @classmethod
    def from_json(cls, arguments: str) -> "V1CloseAgentArgs":
        data = _json_mapping(arguments, "close_agent arguments")
        return cls(target=_required_str(data, "target"))

    def agent_id(self) -> ThreadId:
        return parse_agent_id_target(self.target)


@dataclass(frozen=True)
class V1CloseAgentResult:
    previous_status: AgentStatus

    def __post_init__(self) -> None:
        if not isinstance(self.previous_status, AgentStatus):
            object.__setattr__(self, "previous_status", AgentStatus.from_mapping(self.previous_status))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"previous_status": self.previous_status.to_mapping()}

    def log_preview(self) -> str:
        return tool_output_json_text(self, "close_agent")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, "close_agent")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "close_agent")


@dataclass(frozen=True)
class V1WaitArgs:
    targets: tuple[str, ...] = ()
    timeout_ms: int | None = None

    @classmethod
    def from_json(cls, arguments: str) -> "V1WaitArgs":
        data = _json_mapping(arguments, "wait_agent arguments")
        targets = data.get("targets", [])
        if not isinstance(targets, list) or not all(isinstance(target, str) for target in targets):
            raise TypeError("targets must be a list of strings")
        return cls(targets=tuple(targets), timeout_ms=_optional_int(data, "timeout_ms"))

    def receiver_thread_ids(self) -> tuple[ThreadId, ...]:
        return parse_agent_id_targets(self.targets)

    def resolve_timeout_ms(
        self,
        min_timeout_ms: int = MIN_WAIT_TIMEOUT_MS,
        default_timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        max_timeout_ms: int = MAX_WAIT_TIMEOUT_MS,
    ) -> int:
        value = default_timeout_ms if self.timeout_ms is None else self.timeout_ms
        if value <= 0:
            raise FunctionCallError.respond_to_model("timeout_ms must be greater than zero")
        return max(min_timeout_ms, min(value, max_timeout_ms))


@dataclass(frozen=True)
class V1WaitAgentResult:
    status: Mapping[str, AgentStatus | str | dict[str, JsonValue]]
    timed_out: bool

    def __post_init__(self) -> None:
        if not isinstance(self.status, Mapping):
            raise TypeError("status must be a mapping")
        if not isinstance(self.timed_out, bool):
            raise TypeError("timed_out must be a bool")
        object.__setattr__(
            self,
            "status",
            {str(target): AgentStatus.from_mapping(status) for target, status in self.status.items()},
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "status": {target: status.to_mapping() for target, status in self.status.items()},
            "timed_out": self.timed_out,
        }

    def log_preview(self) -> str:
        return tool_output_json_text(self, "wait_agent")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, None, "wait_agent")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "wait_agent")


class V1SpawnAgentHandler:
    def __init__(
        self,
        options: SpawnAgentToolOptions | None = None,
        spawn_agent: Callable[[V1SpawnAgentArgs], V1SpawnAgentResult | Mapping[str, JsonValue]] | None = None,
    ) -> None:
        self.options = options or SpawnAgentToolOptions()
        self._spawn_agent = spawn_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "spawn_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_spawn_agent_tool_v1(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return multi_agent_tool_search_info(
            "spawn_agent spawn agent subagent sub-agent delegate delegation parallel work worker explorer no-apps fork model reasoning",
            self.spec(),
        )

    def parse_args(self, payload: ToolPayload) -> V1SpawnAgentArgs:
        args = V1SpawnAgentArgs.from_json(function_arguments(payload))
        args.validate_for_spawn()
        return args

    def handle(self, invocation: ToolInvocation) -> V1SpawnAgentResult:
        args = self.parse_args(invocation.payload)
        if self._spawn_agent is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        result = self._spawn_agent(args)
        if isinstance(result, V1SpawnAgentResult):
            return result
        data = _mapping(result, "spawn_agent result")
        return V1SpawnAgentResult(
            agent_id=_required_str(data, "agent_id"),
            nickname=_optional_str(data, "nickname"),
        )


class SendInputHandler:
    def __init__(self, send_input: Callable[[ThreadId, tuple[UserInput, ...], bool], str] | None = None) -> None:
        self._send_input = send_input

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "send_input")

    def spec(self) -> dict[str, JsonValue]:
        return create_send_input_tool_v1()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return multi_agent_tool_search_info(
            "send_input send message existing agent subagent follow up interrupt redirect queue target",
            self.spec(),
        )

    def parse_args(self, payload: ToolPayload) -> SendInputArgs:
        return SendInputArgs.from_json(function_arguments(payload))

    def handle(self, invocation: ToolInvocation) -> SendInputResult:
        args = self.parse_args(invocation.payload)
        if self._send_input is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        submission_id = self._send_input(args.receiver_thread_id(), args.input_items(), args.interrupt)
        return SendInputResult(submission_id)


class V1CloseAgentHandler:
    def __init__(self, close_agent: Callable[[ThreadId], AgentStatus | str | dict[str, JsonValue]] | None = None) -> None:
        self._close_agent = close_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "close_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_close_agent_tool_v1()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return multi_agent_tool_search_info(
            "close_agent close shutdown stop agent subagent thread status target",
            self.spec(),
        )

    def handle(self, invocation: ToolInvocation) -> V1CloseAgentResult:
        args = V1CloseAgentArgs.from_json(function_arguments(invocation.payload))
        if self._close_agent is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        return V1CloseAgentResult(AgentStatus.from_mapping(self._close_agent(args.agent_id())))


class V1WaitAgentHandler:
    def __init__(
        self,
        options: WaitAgentTimeoutOptions | None = None,
        wait_agent: Callable[[tuple[ThreadId, ...], int], Mapping[str, AgentStatus | str | dict[str, JsonValue]]] | None = None,
    ) -> None:
        self.options = options or WaitAgentTimeoutOptions()
        self._wait_agent = wait_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "wait_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_wait_agent_tool_v1(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return multi_agent_tool_search_info(
            "wait_agent wait agent subagent status final result complete timeout targets",
            self.spec(),
        )

    def handle(
        self,
        invocation: ToolInvocation,
        min_timeout_ms: int = MIN_WAIT_TIMEOUT_MS,
        default_timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        max_timeout_ms: int = MAX_WAIT_TIMEOUT_MS,
    ) -> V1WaitAgentResult:
        args = V1WaitArgs.from_json(function_arguments(invocation.payload))
        targets = args.receiver_thread_ids()
        timeout_ms = args.resolve_timeout_ms(min_timeout_ms, default_timeout_ms, max_timeout_ms)
        if self._wait_agent is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        status = self._wait_agent(targets, timeout_ms)
        timed_out = len(status) == 0
        return V1WaitAgentResult(status, timed_out)


__all__ = [
    "MULTI_AGENT_TOOL_SEARCH_SOURCE_DESCRIPTION",
    "MULTI_AGENT_TOOL_SEARCH_SOURCE_NAME",
    "SendInputArgs",
    "SendInputHandler",
    "SendInputResult",
    "V1CloseAgentArgs",
    "V1CloseAgentHandler",
    "V1CloseAgentResult",
    "V1SpawnAgentArgs",
    "V1SpawnAgentHandler",
    "V1SpawnAgentResult",
    "V1WaitAgentHandler",
    "V1WaitAgentResult",
    "V1WaitArgs",
    "multi_agent_tool_search_info",
    "parse_agent_id_target",
    "parse_agent_id_targets",
]
