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
from . import _agent_control, _json_mapping, _sync_await
from . import JsonValue, _required_str

@dataclass(frozen=True)
class ResumeAgentArgs:
    id: str

    @classmethod
    def from_json(cls, arguments: str) -> 'ResumeAgentArgs':
        data = _json_mapping(arguments, 'resume_agent arguments')
        return cls(id=_required_str(data, 'id'))

    def thread_id(self) -> ThreadId:
        try:
            return ThreadId.from_string(self.id)
        except Exception as err:
            raise FunctionCallError.respond_to_model(f'invalid agent id {self.id}: {err!r}') from err

@dataclass(frozen=True)
class ResumeAgentResult:
    status: AgentStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, AgentStatus):
            object.__setattr__(self, 'status', AgentStatus.from_mapping(self.status))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {'status': self.status.to_mapping()}

    def log_preview(self) -> str:
        return tool_output_json_text(self, 'resume_agent')

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, True, 'resume_agent')

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, 'resume_agent')

class ResumeAgentHandler:

    def __init__(self, resume_agent: Callable[[ThreadId], AgentStatus | str | dict[str, JsonValue]] | None=None) -> None:
        self._resume_agent = resume_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, 'resume_agent')

    def spec(self) -> dict[str, JsonValue]:
        return create_resume_agent_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == 'function'

    def search_info(self) -> ToolSearchInfo | None:
        return ToolSearchInfo.from_spec('resume_agent resume reopen closed agent subagent thread id target', self.spec(), ToolSearchSourceInfo('Multi-agent tools', 'Spawn and manage sub-agents.'))

    def parse_args(self, payload: ToolPayload) -> ResumeAgentArgs:
        return ResumeAgentArgs.from_json(function_arguments(payload))

    def handle(self, invocation: ToolInvocation) -> ResumeAgentResult:
        args = self.parse_args(invocation.payload)
        thread_id = args.thread_id()
        if self._resume_agent is not None:
            return ResumeAgentResult(AgentStatus.from_mapping(self._resume_agent(thread_id)))
        session = getattr(invocation, 'session', None)
        turn = getattr(invocation, 'turn', None)
        agent_control = _agent_control(session)
        try:
            status = _sync_await(agent_control.get_status(thread_id))
            if AgentStatus.from_mapping(status).type == 'not_found':
                config = getattr(turn, 'config', None)
                session_source = getattr(turn, 'session_source', None)
                _sync_await(agent_control.resume_agent_from_rollout(config, thread_id, session_source))
                status = _sync_await(agent_control.get_status(thread_id))
            return ResumeAgentResult(AgentStatus.from_mapping(status))
        except Exception as err:
            raise FunctionCallError.respond_to_model(f'collab tool failed: {err}') from err
__all__ = ['ResumeAgentArgs', 'ResumeAgentHandler', 'ResumeAgentResult']
