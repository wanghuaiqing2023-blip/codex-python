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
from pycodex.core.tools.handlers.multi_agents_common import DEFAULT_WAIT_TIMEOUT_MS, MAX_WAIT_TIMEOUT_MS, MIN_WAIT_TIMEOUT_MS, apply_requested_spawn_agent_model_overrides, apply_spawn_agent_runtime_overrides, apply_spawn_agent_service_tier, apply_spawn_agent_overrides, build_agent_spawn_config, collab_spawn_error, function_arguments, parse_collab_input, reject_full_fork_spawn_overrides, thread_spawn_source, tool_output_code_mode_result, tool_output_json_text, tool_output_response_item
from pycodex.core.tools.handlers.multi_agents_spec import MULTI_AGENT_V1_NAMESPACE, SpawnAgentToolOptions, WaitAgentTimeoutOptions, create_close_agent_tool_v2, create_followup_task_tool, create_list_agents_tool, create_resume_agent_tool, create_send_message_tool, create_spawn_agent_tool_v2, create_wait_agent_tool_v2
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.tools.tool_discovery import ToolSearchSourceInfo
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentPath, AgentStatus, InterAgentCommunication, Op, ResponseInputItem, SessionSource, ThreadId, ToolName, UserInput
from . import JsonValue, _agent_control_from_session, _deny_unknown, _json_mapping, _mapping, _optional_str, _required_str, _sync_await

class SpawnAgentForkMode(str, Enum):
    FULL_HISTORY = 'full_history'
    LAST_N_TURNS = 'last_n_turns'

@dataclass(frozen=True)
class SpawnAgentFork:
    mode: SpawnAgentForkMode
    last_n_turns: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, SpawnAgentForkMode):
            object.__setattr__(self, 'mode', SpawnAgentForkMode(str(self.mode)))
        if self.last_n_turns is not None and (isinstance(self.last_n_turns, bool) or not isinstance(self.last_n_turns, int)):
            raise TypeError('last_n_turns must be an integer')

    @classmethod
    def full_history(cls) -> 'SpawnAgentFork':
        return cls(SpawnAgentForkMode.FULL_HISTORY)

    @classmethod
    def last_n_turns_fork(cls, turns: int) -> 'SpawnAgentFork':
        if turns <= 0:
            raise ValueError('turns must be positive')
        return cls(SpawnAgentForkMode.LAST_N_TURNS, turns)

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.mode is SpawnAgentForkMode.FULL_HISTORY:
            return {'type': 'full_history'}
        return {'type': 'last_n_turns', 'turns': self.last_n_turns}

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
    def from_json(cls, arguments: str) -> 'SpawnAgentArgs':
        data = _json_mapping(arguments, 'spawn_agent arguments')
        _deny_unknown(data, {'message', 'task_name', 'agent_type', 'model', 'reasoning_effort', 'service_tier', 'fork_turns', 'fork_context'}, 'spawn_agent arguments')
        fork_context = data.get('fork_context')
        if fork_context is not None and (not isinstance(fork_context, bool)):
            raise TypeError('fork_context must be a bool')
        return cls(message=_required_str(data, 'message'), task_name=_required_str(data, 'task_name'), agent_type=_optional_str(data, 'agent_type'), model=_optional_str(data, 'model'), reasoning_effort=_optional_str(data, 'reasoning_effort'), service_tier=_optional_str(data, 'service_tier'), fork_turns=_optional_str(data, 'fork_turns'), fork_context=fork_context)

    def role_name(self) -> str | None:
        if self.agent_type is None:
            return None
        role = self.agent_type.strip()
        return role or None

    def fork_mode(self) -> SpawnAgentFork | None:
        if self.fork_context is not None:
            raise FunctionCallError.respond_to_model('fork_context is not supported in MultiAgentV2; use fork_turns instead')
        fork_turns = (self.fork_turns or 'all').strip() or 'all'
        if fork_turns.lower() == 'none':
            return None
        if fork_turns.lower() == 'all':
            return SpawnAgentFork.full_history()
        try:
            last_n_turns = int(fork_turns)
        except ValueError as err:
            raise FunctionCallError.respond_to_model('fork_turns must be `none`, `all`, or a positive integer string') from err
        if last_n_turns <= 0:
            raise FunctionCallError.respond_to_model('fork_turns must be `none`, `all`, or a positive integer string')
        return SpawnAgentFork.last_n_turns_fork(last_n_turns)

    def validate_for_spawn(self) -> None:
        parse_collab_input(self.message, None)
        if self.fork_mode() is not None and self.fork_mode().mode is SpawnAgentForkMode.FULL_HISTORY:
            reject_full_fork_spawn_overrides(self.role_name(), self.model, self.reasoning_effort)

def _spawn_hide_metadata_from_turn(turn: Any) -> bool:
    config = getattr(turn, 'config', None)
    multi_agent_v2 = getattr(config, 'multi_agent_v2', None)
    return bool(getattr(multi_agent_v2, 'hide_spawn_agent_metadata', False))

def _coerce_spawn_agent_result(result: SpawnAgentResult | dict[str, JsonValue]) -> SpawnAgentResult:
    if isinstance(result, SpawnAgentResult):
        return result
    data = _mapping(result, 'spawn_agent result')
    task_name = data.get('task_name')
    if not isinstance(task_name, str):
        raise FunctionCallError.respond_to_model('spawned agent is missing a canonical task name')
    hide_metadata = 'nickname' not in data
    return SpawnAgentResult(task_name=task_name, nickname=_optional_str(data, 'nickname'), hide_metadata=hide_metadata)

def _spawn_agent_from_invocation(invocation: ToolInvocation, args: SpawnAgentArgs) -> SpawnAgentResult:
    session = getattr(invocation, 'session', None)
    turn = getattr(invocation, 'turn', None)
    if session is None or turn is None:
        raise FunctionCallError.respond_to_model('agent control is unavailable in this session')
    agent_control = _agent_control_from_session(session)
    session_source = getattr(turn, 'session_source', None)
    if not isinstance(session_source, SessionSource):
        session_source = SessionSource.default()
    child_depth = next_thread_spawn_depth(session_source)
    role_name = args.role_name()
    input_items = parse_collab_input(args.message, None)
    prompt = _render_input_preview(input_items)
    config = _apply_spawn_config_overrides(session, turn, build_agent_spawn_config(None, turn), args, child_depth)
    spawn_source = thread_spawn_source(getattr(session, 'conversation_id'), session_source, child_depth, role_name, args.task_name)
    operation = _spawn_initial_operation(session_source, spawn_source, input_items, prompt)
    try:
        spawned = _sync_await(agent_control.spawn_agent_with_metadata(config, operation, spawn_source, SpawnAgentOptions(fork_parent_spawn_call_id=getattr(invocation, 'call_id', None) if args.fork_mode() is not None else None, fork_mode=_control_fork_mode(args.fork_mode()), environments=_turn_environment_selections(turn))))
    except Exception as err:
        raise collab_spawn_error(err) from err
    metadata = getattr(spawned, 'metadata', None)
    snapshot = None
    get_snapshot = getattr(agent_control, 'get_agent_config_snapshot', None)
    if callable(get_snapshot):
        try:
            snapshot = _sync_await(get_snapshot(getattr(spawned, 'thread_id')))
        except Exception:
            snapshot = None
    task_name = _spawned_task_name(snapshot, metadata)
    if task_name is None:
        raise FunctionCallError.respond_to_model('spawned agent is missing a canonical task name')
    nickname = _spawned_nickname(snapshot, metadata)
    if _spawn_hide_metadata_from_turn(turn):
        return SpawnAgentResult.hidden_metadata(task_name)
    return SpawnAgentResult.with_nickname(task_name, nickname)

def _spawn_initial_operation(parent_session_source: SessionSource, spawn_source: SessionSource, input_items: tuple[UserInput, ...], prompt: str) -> Op:
    recipient = spawn_source.get_agent_path()
    if recipient is not None and all((item.type == 'text' for item in input_items)):
        return Op.inter_agent_communication(InterAgentCommunication(author=parent_session_source.get_agent_path() or AgentPath.root(), recipient=recipient, content=prompt, trigger_turn=True))
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
            setattr(config, 'service_tier', args.service_tier)
        except Exception:
            pass
    return config

def _apply_spawn_config_overrides(session: Any, turn: Any, config: Any, args: SpawnAgentArgs, child_depth: int) -> Any:
    if args.service_tier is not None:
        _set_config_attr(config, 'service_tier', args.service_tier)
    if args.fork_mode() is None or args.fork_mode().mode is not SpawnAgentForkMode.FULL_HISTORY:
        apply_requested_spawn_agent_model_overrides(session, turn, config, args.model, args.reasoning_effort)
    parent_service_tier = getattr(getattr(turn, 'config', None), 'service_tier', None)
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
    environments = getattr(turn, 'environments', None)
    to_selections = getattr(environments, 'to_selections', None)
    if callable(to_selections):
        selections = to_selections()
        return tuple(selections) if selections is not None else None
    return None

def _spawned_task_name(snapshot: Any, metadata: Any) -> str | None:
    for source in (snapshot, metadata):
        path = _agent_metadata_path(source)
        if path is not None:
            return path.as_str()
        session_source = getattr(source, 'session_source', None)
        if isinstance(session_source, SessionSource):
            path = session_source.get_agent_path()
            if path is not None:
                return path.as_str()
    return None

def _spawned_nickname(snapshot: Any, metadata: Any) -> str | None:
    for source in (snapshot, metadata):
        session_source = getattr(source, 'session_source', None)
        getter = getattr(session_source, 'get_nickname', None)
        if callable(getter):
            value = getter()
            if isinstance(value, str):
                return value
        value = getattr(source, 'agent_nickname', None)
        if isinstance(value, str):
            return value
        if isinstance(source, dict):
            value = source.get('agent_nickname')
            if isinstance(value, str):
                return value
    return None

def _render_input_preview(input_items: tuple[UserInput, ...]) -> str:
    return '\n'.join((item.text or '' if item.type == 'text' else '[input]' for item in input_items))

@dataclass(frozen=True)
class SpawnAgentResult:
    task_name: str
    nickname: str | None = None
    hide_metadata: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.task_name, str):
            raise TypeError('task_name must be a string')
        if self.nickname is not None and (not isinstance(self.nickname, str)):
            raise TypeError('nickname must be a string')
        if not isinstance(self.hide_metadata, bool):
            raise TypeError('hide_metadata must be a bool')

    @classmethod
    def with_nickname(cls, task_name: str, nickname: str | None=None) -> 'SpawnAgentResult':
        return cls(task_name=task_name, nickname=nickname, hide_metadata=False)

    @classmethod
    def hidden_metadata(cls, task_name: str) -> 'SpawnAgentResult':
        return cls(task_name=task_name, hide_metadata=True)

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {'task_name': self.task_name}
        if not self.hide_metadata:
            data['nickname'] = self.nickname
        return data

    def log_preview(self) -> str:
        return tool_output_json_text(self, 'spawn_agent')

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, 'spawn_agent')

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, 'spawn_agent')

class SpawnAgentHandler:

    def __init__(self, options: SpawnAgentToolOptions | None=None, spawn_agent: Callable[[SpawnAgentArgs], SpawnAgentResult | dict[str, JsonValue]] | None=None) -> None:
        self.options = options or SpawnAgentToolOptions()
        self._spawn_agent = spawn_agent

    def tool_name(self) -> ToolName:
        return ToolName.plain('spawn_agent')

    def spec(self) -> dict[str, JsonValue]:
        return create_spawn_agent_tool_v2(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == 'function'

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
        if _spawn_hide_metadata_from_turn(getattr(invocation, 'turn', None)):
            return SpawnAgentResult.hidden_metadata(coerced.task_name)
        return coerced
__all__ = ['SpawnAgentArgs', 'SpawnAgentFork', 'SpawnAgentForkMode', 'SpawnAgentHandler', 'SpawnAgentResult']
