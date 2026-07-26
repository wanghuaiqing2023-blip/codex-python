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
from . import JsonValue, _agent_metadata_path, _deny_unknown, _json_mapping, _required_str

@dataclass(frozen=True)
class CloseAgentArgs:
    target: str

    @classmethod
    def from_json(cls, arguments: str) -> 'CloseAgentArgs':
        data = _json_mapping(arguments, 'close_agent arguments')
        _deny_unknown(data, {'target'}, 'close_agent arguments')
        return cls(target=_required_str(data, 'target'))

@dataclass(frozen=True)
class CloseAgentResult:
    previous_status: AgentStatus

    def __post_init__(self) -> None:
        if not isinstance(self.previous_status, AgentStatus):
            object.__setattr__(self, 'previous_status', AgentStatus.from_mapping(self.previous_status))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {'previous_status': self.previous_status.to_mapping()}

    def log_preview(self) -> str:
        return tool_output_json_text(self, 'close_agent')

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, 'close_agent')

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, 'close_agent')

class CloseAgentHandler:

    def __init__(self, close_agent: Callable[[str], AgentStatus | str | dict[str, JsonValue]] | None=None, get_agent_metadata: Callable[[str], Any] | None=None) -> None:
        self._close_agent = close_agent
        self._get_agent_metadata = get_agent_metadata

    def tool_name(self) -> ToolName:
        return ToolName.plain('close_agent')

    def spec(self) -> dict[str, JsonValue]:
        return create_close_agent_tool_v2()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == 'function'

    def handle(self, invocation: ToolInvocation) -> CloseAgentResult:
        args = CloseAgentArgs.from_json(function_arguments(invocation.payload))
        if self._close_agent is None:
            raise FunctionCallError.respond_to_model('agent control is unavailable in this session')
        if self._get_agent_metadata is not None:
            agent_path = _agent_metadata_path(self._get_agent_metadata(args.target))
            if agent_path is not None and agent_path.is_root():
                raise FunctionCallError.respond_to_model('root is not a spawned agent')
        return CloseAgentResult(AgentStatus.from_mapping(self._close_agent(args.target)))
__all__ = ['CloseAgentArgs', 'CloseAgentHandler', 'CloseAgentResult']
