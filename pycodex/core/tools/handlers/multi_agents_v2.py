"""Multi-agent v2 handler facades ported from Codex core.

The Rust handlers talk to ``agent_control`` and emit collaboration events. This
stdlib port mirrors the pure call boundary: strict argument parsing, message
validation, delivery-mode shaping, result serialization, and optional callback
hooks that let tests or lightweight integrations provide the agent-control
behavior.
"""

from __future__ import annotations

import asyncio
import json
import inspect
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Callable, Iterable

from pycodex.core.agent import next_thread_spawn_depth
from pycodex.core.agent.control import SpawnAgentForkMode as ControlSpawnAgentForkMode
from pycodex.core.agent.control import SpawnAgentOptions
from pycodex.core.tools.handlers.multi_agents_common import (
    DEFAULT_WAIT_TIMEOUT_MS,
    MAX_WAIT_TIMEOUT_MS,
    MIN_WAIT_TIMEOUT_MS,
    apply_requested_spawn_agent_model_overrides,
    apply_spawn_agent_runtime_overrides,
    apply_spawn_agent_service_tier,
    apply_spawn_agent_overrides,
    build_agent_spawn_config,
    collab_spawn_error,
    function_arguments,
    parse_collab_input,
    reject_full_fork_spawn_overrides,
    thread_spawn_source,
    tool_output_code_mode_result,
    tool_output_json_text,
    tool_output_response_item,
)
from pycodex.core.tools.handlers.multi_agents_spec import (
    MULTI_AGENT_V1_NAMESPACE,
    SpawnAgentToolOptions,
    WaitAgentTimeoutOptions,
    create_close_agent_tool_v2,
    create_followup_task_tool,
    create_list_agents_tool,
    create_resume_agent_tool,
    create_send_message_tool,
    create_spawn_agent_tool_v2,
    create_wait_agent_tool_v2,
)
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.tools.tool_discovery import ToolSearchSourceInfo
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentPath, AgentStatus, InterAgentCommunication, Op, ResponseInputItem, SessionSource, ThreadId, ToolName, UserInput

JsonValue = Any


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _json_mapping(arguments: str, label: str) -> dict[str, JsonValue]:
    return _mapping(json.loads(arguments), label)


def _deny_unknown(data: dict[str, JsonValue], allowed: set[str], label: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"unknown field in {label}: {sorted(unknown)[0]}")


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


@dataclass(frozen=True)
class ListAgentsArgs:
    path_prefix: str | None = None

    @classmethod
    def from_json(cls, arguments: str) -> "ListAgentsArgs":
        data = _json_mapping(arguments, "list_agents arguments")
        _deny_unknown(data, {"path_prefix"}, "list_agents arguments")
        return cls(path_prefix=_optional_str(data, "path_prefix"))


@dataclass(frozen=True)
class CloseAgentArgs:
    target: str

    @classmethod
    def from_json(cls, arguments: str) -> "CloseAgentArgs":
        data = _json_mapping(arguments, "close_agent arguments")
        _deny_unknown(data, {"target"}, "close_agent arguments")
        return cls(target=_required_str(data, "target"))


@dataclass(frozen=True)
class SendMessageArgs:
    target: str
    message: str

    @classmethod
    def from_json(cls, arguments: str) -> "SendMessageArgs":
        data = _json_mapping(arguments, "send_message arguments")
        _deny_unknown(data, {"target", "message"}, "send_message arguments")
        return cls(target=_required_str(data, "target"), message=_required_str(data, "message"))


@dataclass(frozen=True)
class FollowupTaskArgs:
    target: str
    message: str

    @classmethod
    def from_json(cls, arguments: str) -> "FollowupTaskArgs":
        data = _json_mapping(arguments, "followup_task arguments")
        _deny_unknown(data, {"target", "message"}, "followup_task arguments")
        return cls(target=_required_str(data, "target"), message=_required_str(data, "message"))


class SpawnAgentForkMode(str, Enum):
    FULL_HISTORY = "full_history"
    LAST_N_TURNS = "last_n_turns"


@dataclass(frozen=True)
class SpawnAgentFork:
    mode: SpawnAgentForkMode
    last_n_turns: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, SpawnAgentForkMode):
            object.__setattr__(self, "mode", SpawnAgentForkMode(str(self.mode)))
        if self.last_n_turns is not None and (
            isinstance(self.last_n_turns, bool) or not isinstance(self.last_n_turns, int)
        ):
            raise TypeError("last_n_turns must be an integer")

    @classmethod
    def full_history(cls) -> "SpawnAgentFork":
        return cls(SpawnAgentForkMode.FULL_HISTORY)

    @classmethod
    def last_n_turns_fork(cls, turns: int) -> "SpawnAgentFork":
        if turns <= 0:
            raise ValueError("turns must be positive")
        return cls(SpawnAgentForkMode.LAST_N_TURNS, turns)

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.mode is SpawnAgentForkMode.FULL_HISTORY:
            return {"type": "full_history"}
        return {"type": "last_n_turns", "turns": self.last_n_turns}


@dataclass(frozen=True)
class SpawnAgentArgs:
    message: str
    task_name: str
    agent_type: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    fork_turns: str | None = None
    fork_context: bool | None = None

    @classmethod
    def from_json(cls, arguments: str) -> "SpawnAgentArgs":
        data = _json_mapping(arguments, "spawn_agent arguments")
        _deny_unknown(
            data,
            {
                "message",
                "task_name",
                "agent_type",
                "model",
                "reasoning_effort",
                "service_tier",
                "fork_turns",
                "fork_context",
            },
            "spawn_agent arguments",
        )
        fork_context = data.get("fork_context")
        if fork_context is not None and not isinstance(fork_context, bool):
            raise TypeError("fork_context must be a bool")
        return cls(
            message=_required_str(data, "message"),
            task_name=_required_str(data, "task_name"),
            agent_type=_optional_str(data, "agent_type"),
            model=_optional_str(data, "model"),
            reasoning_effort=_optional_str(data, "reasoning_effort"),
            service_tier=_optional_str(data, "service_tier"),
            fork_turns=_optional_str(data, "fork_turns"),
            fork_context=fork_context,
        )

    def role_name(self) -> str | None:
        if self.agent_type is None:
            return None
        role = self.agent_type.strip()
        return role or None

    def fork_mode(self) -> SpawnAgentFork | None:
        if self.fork_context is not None:
            raise FunctionCallError.respond_to_model(
                "fork_context is not supported in MultiAgentV2; use fork_turns instead"
            )
        fork_turns = (self.fork_turns or "all").strip() or "all"
        if fork_turns.lower() == "none":
            return None
        if fork_turns.lower() == "all":
            return SpawnAgentFork.full_history()
        try:
            last_n_turns = int(fork_turns)
        except ValueError as err:
            raise FunctionCallError.respond_to_model(
                "fork_turns must be `none`, `all`, or a positive integer string"
            ) from err
        if last_n_turns <= 0:
            raise FunctionCallError.respond_to_model(
                "fork_turns must be `none`, `all`, or a positive integer string"
            )
        return SpawnAgentFork.last_n_turns_fork(last_n_turns)

    def validate_for_spawn(self) -> None:
        parse_collab_input(self.message, None)
        if self.fork_mode() is not None and self.fork_mode().mode is SpawnAgentForkMode.FULL_HISTORY:
            reject_full_fork_spawn_overrides(self.role_name(), self.model, self.reasoning_effort)


@dataclass(frozen=True)
class WaitArgs:
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        if self.timeout_ms is not None and (isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int)):
            raise TypeError("timeout_ms must be an integer")

    @classmethod
    def from_json(cls, arguments: str) -> "WaitArgs":
        data = _json_mapping(arguments, "wait_agent arguments")
        _deny_unknown(data, {"timeout_ms"}, "wait_agent arguments")
        value = data.get("timeout_ms")
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise TypeError("timeout_ms must be an integer")
        return cls(timeout_ms=value)

    def resolve_timeout_ms(
        self,
        min_timeout_ms: int = MIN_WAIT_TIMEOUT_MS,
        default_timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        max_timeout_ms: int = MAX_WAIT_TIMEOUT_MS,
    ) -> int:
        value = default_timeout_ms if self.timeout_ms is None else self.timeout_ms
        if value < min_timeout_ms:
            raise FunctionCallError.respond_to_model(f"timeout_ms must be at least {min_timeout_ms}")
        if value > max_timeout_ms:
            raise FunctionCallError.respond_to_model(f"timeout_ms must be at most {max_timeout_ms}")
        return value


@dataclass(frozen=True)
class ResumeAgentArgs:
    id: str

    @classmethod
    def from_json(cls, arguments: str) -> "ResumeAgentArgs":
        data = _json_mapping(arguments, "resume_agent arguments")
        return cls(id=_required_str(data, "id"))

    def thread_id(self) -> ThreadId:
        try:
            return ThreadId.from_string(self.id)
        except Exception as err:
            raise FunctionCallError.respond_to_model(f"invalid agent id {self.id}: {err!r}") from err


class MessageDeliveryMode(str, Enum):
    QUEUE_ONLY = "queue_only"
    TRIGGER_TURN = "trigger_turn"

    def apply(self, communication: dict[str, JsonValue] | InterAgentCommunication) -> dict[str, JsonValue] | InterAgentCommunication:
        if isinstance(communication, InterAgentCommunication):
            return replace(communication, trigger_turn=self is MessageDeliveryMode.TRIGGER_TURN)
        if not isinstance(communication, dict):
            raise TypeError("communication must be a mapping or InterAgentCommunication")
        output = dict(communication)
        output["trigger_turn"] = self is MessageDeliveryMode.TRIGGER_TURN
        return output


def message_content(message: str) -> str:
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    if message.strip() == "":
        raise FunctionCallError.respond_to_model("Empty message can't be sent to an agent")
    return message


def _call_list_agents(callback: Callable[..., Iterable[JsonValue]], session_source: Any, path_prefix: str | None) -> Iterable[JsonValue]:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(session_source, path_prefix)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
    ]
    has_varargs = any(parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in signature.parameters.values())
    if has_varargs or len(positional) >= 2:
        return callback(session_source, path_prefix)
    return callback(path_prefix)


def _agent_metadata_path(metadata: Any) -> AgentPath | None:
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        value = metadata.get("agent_path")
    else:
        value = getattr(metadata, "agent_path", None)
    if value is None:
        return None
    if isinstance(value, AgentPath):
        return value
    return AgentPath.from_string(str(value))


def _required_agent_metadata_path(metadata: Any) -> AgentPath:
    agent_path = _agent_metadata_path(metadata)
    if agent_path is None:
        raise FunctionCallError.respond_to_model("target agent is missing an agent_path")
    return agent_path


def handle_message_string_tool(
    *,
    mode: MessageDeliveryMode,
    target: str,
    message: str,
    send_message: Callable[[MessageDeliveryMode, str, str], FunctionToolOutput | None],
    get_agent_metadata: Callable[[str], Any] | None = None,
) -> FunctionToolOutput:
    prompt = message_content(message)
    if get_agent_metadata is not None:
        receiver_agent_path = _required_agent_metadata_path(get_agent_metadata(target))
        if mode is MessageDeliveryMode.TRIGGER_TURN and receiver_agent_path.is_root():
            raise FunctionCallError.respond_to_model("Tasks can't be assigned to the root agent")
    result = send_message(mode, target, prompt)
    if result is None:
        return successful_empty_message_output()
    if not isinstance(result, FunctionToolOutput):
        raise TypeError("send_message callback must return FunctionToolOutput or None")
    return result


def _wait_timeout_bounds_from_turn(
    turn: Any,
    min_timeout_ms: int,
    default_timeout_ms: int,
    max_timeout_ms: int,
) -> tuple[int, int, int]:
    config = getattr(turn, "config", None)
    multi_agent_v2 = getattr(config, "multi_agent_v2", None)
    if multi_agent_v2 is None:
        return min_timeout_ms, default_timeout_ms, max_timeout_ms
    return (
        _timeout_bound(getattr(multi_agent_v2, "min_wait_timeout_ms", None), min_timeout_ms, "min_wait_timeout_ms"),
        _timeout_bound(getattr(multi_agent_v2, "default_wait_timeout_ms", None), default_timeout_ms, "default_wait_timeout_ms"),
        _timeout_bound(getattr(multi_agent_v2, "max_wait_timeout_ms", None), max_timeout_ms, "max_wait_timeout_ms"),
    )


def _timeout_bound(value: Any, fallback: int, name: str) -> int:
    if value is None:
        return fallback
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


def _spawn_hide_metadata_from_turn(turn: Any) -> bool:
    config = getattr(turn, "config", None)
    multi_agent_v2 = getattr(config, "multi_agent_v2", None)
    return bool(getattr(multi_agent_v2, "hide_spawn_agent_metadata", False))


def _coerce_spawn_agent_result(result: SpawnAgentResult | dict[str, JsonValue]) -> SpawnAgentResult:
    if isinstance(result, SpawnAgentResult):
        return result
    data = _mapping(result, "spawn_agent result")
    task_name = data.get("task_name")
    if not isinstance(task_name, str):
        raise FunctionCallError.respond_to_model("spawned agent is missing a canonical task name")
    hide_metadata = "nickname" not in data
    return SpawnAgentResult(
        task_name=task_name,
        nickname=_optional_str(data, "nickname"),
        hide_metadata=hide_metadata,
    )


def _spawn_agent_from_invocation(invocation: ToolInvocation, args: SpawnAgentArgs) -> SpawnAgentResult:
    session = getattr(invocation, "session", None)
    turn = getattr(invocation, "turn", None)
    if session is None or turn is None:
        raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
    agent_control = _agent_control_from_session(session)
    session_source = getattr(turn, "session_source", None)
    if not isinstance(session_source, SessionSource):
        session_source = SessionSource.default()
    child_depth = next_thread_spawn_depth(session_source)
    role_name = args.role_name()
    input_items = parse_collab_input(args.message, None)
    prompt = _render_input_preview(input_items)
    config = _apply_spawn_config_overrides(
        session,
        turn,
        build_agent_spawn_config(None, turn),
        args,
        child_depth,
    )
    spawn_source = thread_spawn_source(
        getattr(session, "conversation_id"),
        session_source,
        child_depth,
        role_name,
        args.task_name,
    )
    operation = _spawn_initial_operation(session_source, spawn_source, input_items, prompt)
    try:
        spawned = _sync_await(agent_control.spawn_agent_with_metadata(
            config,
            operation,
            spawn_source,
            SpawnAgentOptions(
                fork_parent_spawn_call_id=getattr(invocation, "call_id", None) if args.fork_mode() is not None else None,
                fork_mode=_control_fork_mode(args.fork_mode()),
                environments=_turn_environment_selections(turn),
            ),
        ))
    except Exception as err:
        raise collab_spawn_error(err) from err
    metadata = getattr(spawned, "metadata", None)
    snapshot = None
    get_snapshot = getattr(agent_control, "get_agent_config_snapshot", None)
    if callable(get_snapshot):
        try:
            snapshot = _sync_await(get_snapshot(getattr(spawned, "thread_id")))
        except Exception:
            snapshot = None
    task_name = _spawned_task_name(snapshot, metadata)
    if task_name is None:
        raise FunctionCallError.respond_to_model("spawned agent is missing a canonical task name")
    nickname = _spawned_nickname(snapshot, metadata)
    if _spawn_hide_metadata_from_turn(turn):
        return SpawnAgentResult.hidden_metadata(task_name)
    return SpawnAgentResult.with_nickname(task_name, nickname)


def _spawn_initial_operation(
    parent_session_source: SessionSource,
    spawn_source: SessionSource,
    input_items: tuple[UserInput, ...],
    prompt: str,
) -> Op:
    recipient = spawn_source.get_agent_path()
    if recipient is not None and all(item.type == "text" for item in input_items):
        return Op.inter_agent_communication(
            InterAgentCommunication(
                author=parent_session_source.get_agent_path() or AgentPath.root(),
                recipient=recipient,
                content=prompt,
                trigger_turn=True,
            )
        )
    return Op.user_input(input_items)


def _control_fork_mode(fork: SpawnAgentFork | None) -> Any:
    if fork is None:
        return None
    if fork.mode is SpawnAgentForkMode.FULL_HISTORY:
        return ControlSpawnAgentForkMode.FULL_HISTORY
    return (ControlSpawnAgentForkMode.LAST_N_TURNS, int(fork.last_n_turns or 0))


def _spawn_config_from_turn(turn: Any, args: SpawnAgentArgs) -> Any:
    config = build_agent_spawn_config(None, turn)
    if args.service_tier is not None and config is not None:
        try:
            setattr(config, "service_tier", args.service_tier)
        except Exception:
            pass
    return config


def _apply_spawn_config_overrides(
    session: Any,
    turn: Any,
    config: Any,
    args: SpawnAgentArgs,
    child_depth: int,
) -> Any:
    if args.service_tier is not None:
        _set_config_attr(config, "service_tier", args.service_tier)
    if args.fork_mode() is None or args.fork_mode().mode is not SpawnAgentForkMode.FULL_HISTORY:
        apply_requested_spawn_agent_model_overrides(
            session,
            turn,
            config,
            args.model,
            args.reasoning_effort,
        )
    parent_service_tier = getattr(getattr(turn, "config", None), "service_tier", None)
    apply_spawn_agent_service_tier(session, config, parent_service_tier, args.service_tier)
    apply_spawn_agent_runtime_overrides(config, turn)
    apply_spawn_agent_overrides(config, child_depth)
    return config


def _set_config_attr(config: Any, key: str, value: Any) -> None:
    if isinstance(config, dict):
        config[key] = value
    else:
        setattr(config, key, value)


def _turn_environment_selections(turn: Any) -> tuple[Any, ...] | None:
    environments = getattr(turn, "environments", None)
    to_selections = getattr(environments, "to_selections", None)
    if callable(to_selections):
        selections = to_selections()
        return tuple(selections) if selections is not None else None
    return None


def _spawned_task_name(snapshot: Any, metadata: Any) -> str | None:
    for source in (snapshot, metadata):
        path = _agent_metadata_path(source)
        if path is not None:
            return path.as_str()
        session_source = getattr(source, "session_source", None)
        if isinstance(session_source, SessionSource):
            path = session_source.get_agent_path()
            if path is not None:
                return path.as_str()
    return None


def _spawned_nickname(snapshot: Any, metadata: Any) -> str | None:
    for source in (snapshot, metadata):
        session_source = getattr(source, "session_source", None)
        getter = getattr(session_source, "get_nickname", None)
        if callable(getter):
            value = getter()
            if isinstance(value, str):
                return value
        value = getattr(source, "agent_nickname", None)
        if isinstance(value, str):
            return value
        if isinstance(source, dict):
            value = source.get("agent_nickname")
            if isinstance(value, str):
                return value
    return None


def _render_input_preview(input_items: tuple[UserInput, ...]) -> str:
    return "\n".join(item.text or "" if item.type == "text" else "[input]" for item in input_items)


@dataclass(frozen=True)
class ListAgentsResult:
    agents: tuple[JsonValue, ...]

    def __post_init__(self) -> None:
        if isinstance(self.agents, (str, bytes)):
            raise TypeError("agents must be an iterable")
        object.__setattr__(self, "agents", tuple(self.agents))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"agents": list(self.agents)}

    def log_preview(self) -> str:
        return tool_output_json_text(self, "list_agents")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, "list_agents")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "list_agents")


@dataclass(frozen=True)
class SpawnAgentResult:
    task_name: str
    nickname: str | None = None
    hide_metadata: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.task_name, str):
            raise TypeError("task_name must be a string")
        if self.nickname is not None and not isinstance(self.nickname, str):
            raise TypeError("nickname must be a string")
        if not isinstance(self.hide_metadata, bool):
            raise TypeError("hide_metadata must be a bool")

    @classmethod
    def with_nickname(cls, task_name: str, nickname: str | None = None) -> "SpawnAgentResult":
        return cls(task_name=task_name, nickname=nickname, hide_metadata=False)

    @classmethod
    def hidden_metadata(cls, task_name: str) -> "SpawnAgentResult":
        return cls(task_name=task_name, hide_metadata=True)

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"task_name": self.task_name}
        if not self.hide_metadata:
            data["nickname"] = self.nickname
        return data

    def log_preview(self) -> str:
        return tool_output_json_text(self, "spawn_agent")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, "spawn_agent")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "spawn_agent")


@dataclass(frozen=True)
class CloseAgentResult:
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
class WaitAgentResult:
    message: str
    timed_out: bool

    @classmethod
    def from_timed_out(cls, timed_out: bool) -> "WaitAgentResult":
        return cls("Wait timed out." if timed_out else "Wait completed.", timed_out)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"message": self.message, "timed_out": self.timed_out}

    def log_preview(self) -> str:
        return tool_output_json_text(self, "wait_agent")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, None, "wait_agent")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "wait_agent")


@dataclass(frozen=True)
class ResumeAgentResult:
    status: AgentStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, AgentStatus):
            object.__setattr__(self, "status", AgentStatus.from_mapping(self.status))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"status": self.status.to_mapping()}

    def log_preview(self) -> str:
        return tool_output_json_text(self, "resume_agent")

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, "resume_agent")

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, "resume_agent")


class SpawnAgentHandler:
    def __init__(
        self,
        options: SpawnAgentToolOptions | None = None,
        spawn_agent: Callable[[SpawnAgentArgs], SpawnAgentResult | dict[str, JsonValue]] | None = None,
    ) -> None:
        self.options = options or SpawnAgentToolOptions()
        self._spawn_agent = spawn_agent

    def tool_name(self) -> ToolName:
        return ToolName.plain("spawn_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_spawn_agent_tool_v2(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def parse_args(self, payload: ToolPayload) -> SpawnAgentArgs:
        args = SpawnAgentArgs.from_json(function_arguments(payload))
        args.validate_for_spawn()
        return args

    def handle(self, invocation: ToolInvocation) -> SpawnAgentResult:
        args = self.parse_args(invocation.payload)
        if self._spawn_agent is None:
            result = _spawn_agent_from_invocation(invocation, args)
        else:
            result = self._spawn_agent(args)
        coerced = _coerce_spawn_agent_result(result)
        if _spawn_hide_metadata_from_turn(getattr(invocation, "turn", None)):
            return SpawnAgentResult.hidden_metadata(coerced.task_name)
        return coerced


class ListAgentsHandler:
    def __init__(
        self,
        list_agents: Callable[..., Iterable[JsonValue]] | None = None,
        register_session_root: Callable[[Any, Any], None] | None = None,
    ) -> None:
        self._list_agents = list_agents
        self._register_session_root = register_session_root

    def tool_name(self) -> ToolName:
        return ToolName.plain("list_agents")

    def spec(self) -> dict[str, JsonValue]:
        return create_list_agents_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def handle(self, invocation: ToolInvocation) -> ListAgentsResult:
        args = ListAgentsArgs.from_json(function_arguments(invocation.payload))
        if self._list_agents is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        session_source = getattr(getattr(invocation, "turn", None), "session_source", None)
        if self._register_session_root is not None:
            conversation_id = getattr(getattr(invocation, "session", None), "conversation_id", None)
            if conversation_id is None:
                conversation_id = getattr(getattr(invocation, "session", None), "thread_id", None)
            self._register_session_root(conversation_id, session_source)
        return ListAgentsResult(tuple(_call_list_agents(self._list_agents, session_source, args.path_prefix)))


class CloseAgentHandler:
    def __init__(
        self,
        close_agent: Callable[[str], AgentStatus | str | dict[str, JsonValue]] | None = None,
        get_agent_metadata: Callable[[str], Any] | None = None,
    ) -> None:
        self._close_agent = close_agent
        self._get_agent_metadata = get_agent_metadata

    def tool_name(self) -> ToolName:
        return ToolName.plain("close_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_close_agent_tool_v2()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def handle(self, invocation: ToolInvocation) -> CloseAgentResult:
        args = CloseAgentArgs.from_json(function_arguments(invocation.payload))
        if self._close_agent is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        if self._get_agent_metadata is not None:
            agent_path = _agent_metadata_path(self._get_agent_metadata(args.target))
            if agent_path is not None and agent_path.is_root():
                raise FunctionCallError.respond_to_model("root is not a spawned agent")
        return CloseAgentResult(AgentStatus.from_mapping(self._close_agent(args.target)))


class SendMessageHandler:
    def __init__(
        self,
        send_message: Callable[[MessageDeliveryMode, str, str], FunctionToolOutput | None] | None = None,
        get_agent_metadata: Callable[[str], Any] | None = None,
    ) -> None:
        self._send_message = send_message
        self._get_agent_metadata = get_agent_metadata

    def tool_name(self) -> ToolName:
        return ToolName.plain("send_message")

    def spec(self) -> dict[str, JsonValue]:
        return create_send_message_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def parse_args(self, payload: ToolPayload) -> SendMessageArgs:
        args = SendMessageArgs.from_json(function_arguments(payload))
        message_content(args.message)
        return args

    def handle(self, invocation: ToolInvocation) -> FunctionToolOutput:
        args = self.parse_args(invocation.payload)
        if self._send_message is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        return handle_message_string_tool(
            mode=MessageDeliveryMode.QUEUE_ONLY,
            target=args.target,
            message=args.message,
            send_message=self._send_message,
            get_agent_metadata=self._get_agent_metadata,
        )


class FollowupTaskHandler:
    def __init__(
        self,
        send_message: Callable[[MessageDeliveryMode, str, str], FunctionToolOutput | None] | None = None,
        get_agent_metadata: Callable[[str], Any] | None = None,
    ) -> None:
        self._send_message = send_message
        self._get_agent_metadata = get_agent_metadata

    def tool_name(self) -> ToolName:
        return ToolName.plain("followup_task")

    def spec(self) -> dict[str, JsonValue]:
        return create_followup_task_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def parse_args(self, payload: ToolPayload) -> FollowupTaskArgs:
        args = FollowupTaskArgs.from_json(function_arguments(payload))
        message_content(args.message)
        return args

    def handle(self, invocation: ToolInvocation) -> FunctionToolOutput:
        args = self.parse_args(invocation.payload)
        if self._send_message is None:
            raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
        return handle_message_string_tool(
            mode=MessageDeliveryMode.TRIGGER_TURN,
            target=args.target,
            message=args.message,
            send_message=self._send_message,
            get_agent_metadata=self._get_agent_metadata,
        )


class WaitAgentHandler:
    def __init__(
        self,
        options: WaitAgentTimeoutOptions | None = None,
        wait_for_change: Callable[[int], bool] | None = None,
    ) -> None:
        self.options = options or WaitAgentTimeoutOptions()
        self._wait_for_change = wait_for_change

    def tool_name(self) -> ToolName:
        return ToolName.plain("wait_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_wait_agent_tool_v2(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def parse_args(self, payload: ToolPayload) -> WaitArgs:
        return WaitArgs.from_json(function_arguments(payload))

    def handle(
        self,
        invocation: ToolInvocation,
        min_timeout_ms: int = MIN_WAIT_TIMEOUT_MS,
        default_timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        max_timeout_ms: int = MAX_WAIT_TIMEOUT_MS,
    ) -> WaitAgentResult:
        min_timeout_ms, default_timeout_ms, max_timeout_ms = _wait_timeout_bounds_from_turn(
            getattr(invocation, "turn", None),
            min_timeout_ms,
            default_timeout_ms,
            max_timeout_ms,
        )
        timeout_ms = self.parse_args(invocation.payload).resolve_timeout_ms(
            min_timeout_ms,
            default_timeout_ms,
            max_timeout_ms,
        )
        if self._wait_for_change is None:
            raise FunctionCallError.respond_to_model("agent mailbox is unavailable in this session")
        completed = self._wait_for_change(timeout_ms)
        if not isinstance(completed, bool):
            raise TypeError("wait_for_change callback must return a bool")
        return WaitAgentResult.from_timed_out(not completed)


class ResumeAgentHandler:
    def __init__(
        self,
        resume_agent: Callable[[ThreadId], AgentStatus | str | dict[str, JsonValue]] | None = None,
    ) -> None:
        self._resume_agent = resume_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "resume_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_resume_agent_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return ToolSearchInfo.from_spec(
            "resume_agent resume reopen closed agent subagent thread id target",
            self.spec(),
            ToolSearchSourceInfo("Multi-agent tools", "Spawn and manage sub-agents."),
        )

    def parse_args(self, payload: ToolPayload) -> ResumeAgentArgs:
        return ResumeAgentArgs.from_json(function_arguments(payload))

    def handle(self, invocation: ToolInvocation) -> ResumeAgentResult:
        args = self.parse_args(invocation.payload)
        thread_id = args.thread_id()
        if self._resume_agent is not None:
            return ResumeAgentResult(AgentStatus.from_mapping(self._resume_agent(thread_id)))
        session = getattr(invocation, "session", None)
        turn = getattr(invocation, "turn", None)
        agent_control = _agent_control_from_session(session)
        try:
            status = _sync_await(agent_control.get_status(thread_id))
            if AgentStatus.from_mapping(status).type == "not_found":
                config = getattr(turn, "config", None)
                session_source = getattr(turn, "session_source", None)
                _sync_await(agent_control.resume_agent_from_rollout(config, thread_id, session_source))
                status = _sync_await(agent_control.get_status(thread_id))
            return ResumeAgentResult(AgentStatus.from_mapping(status))
        except Exception as err:
            raise FunctionCallError.respond_to_model(f"collab tool failed: {err}") from err


def successful_empty_message_output() -> FunctionToolOutput:
    return FunctionToolOutput.from_text("", True)


def _agent_control_from_session(session: Any) -> Any:
    services = getattr(session, "services", None)
    agent_control = getattr(services, "agent_control", None)
    if agent_control is None:
        agent_control = getattr(session, "agent_control", None)
    if agent_control is None:
        raise FunctionCallError.respond_to_model("agent control is unavailable in this session")
    return agent_control


def _sync_await(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(value)

    result: dict[str, Any] = {}

    def run() -> None:
        try:
            result["value"] = asyncio.run(value)
        except BaseException as err:
            result["error"] = err

    import threading

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


__all__ = [
    "CloseAgentArgs",
    "CloseAgentHandler",
    "CloseAgentResult",
    "FollowupTaskArgs",
    "FollowupTaskHandler",
    "ListAgentsArgs",
    "ListAgentsHandler",
    "ListAgentsResult",
    "MessageDeliveryMode",
    "ResumeAgentArgs",
    "ResumeAgentHandler",
    "ResumeAgentResult",
    "SendMessageArgs",
    "SendMessageHandler",
    "SpawnAgentArgs",
    "SpawnAgentFork",
    "SpawnAgentForkMode",
    "SpawnAgentHandler",
    "SpawnAgentResult",
    "WaitAgentHandler",
    "WaitAgentResult",
    "WaitArgs",
    "handle_message_string_tool",
    "message_content",
    "successful_empty_message_output",
]
