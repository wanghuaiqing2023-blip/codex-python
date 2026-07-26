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
from . import JsonValue, _deny_unknown, _json_mapping, _optional_str

@dataclass(frozen=True)
class ListAgentsArgs:
    path_prefix: str | None = None

    @classmethod
    def from_json(cls, arguments: str) -> 'ListAgentsArgs':
        data = _json_mapping(arguments, 'list_agents arguments')
        _deny_unknown(data, {'path_prefix'}, 'list_agents arguments')
        return cls(path_prefix=_optional_str(data, 'path_prefix'))

def _call_list_agents(callback: Callable[..., Iterable[JsonValue]], session_source: Any, path_prefix: str | None) -> Iterable[JsonValue]:
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(session_source, path_prefix)
    positional = [parameter for parameter in signature.parameters.values() if parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}]
    has_varargs = any((parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in signature.parameters.values()))
    if has_varargs or len(positional) >= 2:
        return callback(session_source, path_prefix)
    return callback(path_prefix)

@dataclass(frozen=True)
class ListAgentsResult:
    agents: tuple[JsonValue, ...]

    def __post_init__(self) -> None:
        if isinstance(self.agents, (str, bytes)):
            raise TypeError('agents must be an iterable')
        object.__setattr__(self, 'agents', tuple(self.agents))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {'agents': list(self.agents)}

    def log_preview(self) -> str:
        return tool_output_json_text(self, 'list_agents')

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, 'list_agents')

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, 'list_agents')

class ListAgentsHandler:

    def __init__(self, list_agents: Callable[..., Iterable[JsonValue]] | None=None, register_session_root: Callable[[Any, Any], None] | None=None) -> None:
        self._list_agents = list_agents
        self._register_session_root = register_session_root

    def tool_name(self) -> ToolName:
        return ToolName.plain('list_agents')

    def spec(self) -> dict[str, JsonValue]:
        return create_list_agents_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == 'function'

    def handle(self, invocation: ToolInvocation) -> ListAgentsResult:
        args = ListAgentsArgs.from_json(function_arguments(invocation.payload))
        if self._list_agents is None:
            raise FunctionCallError.respond_to_model('agent control is unavailable in this session')
        session_source = getattr(getattr(invocation, 'turn', None), 'session_source', None)
        if self._register_session_root is not None:
            conversation_id = getattr(getattr(invocation, 'session', None), 'conversation_id', None)
            if conversation_id is None:
                conversation_id = getattr(getattr(invocation, 'session', None), 'thread_id', None)
            self._register_session_root(conversation_id, session_source)
        return ListAgentsResult(tuple(_call_list_agents(self._list_agents, session_source, args.path_prefix)))
__all__ = ['ListAgentsArgs', 'ListAgentsHandler', 'ListAgentsResult']
