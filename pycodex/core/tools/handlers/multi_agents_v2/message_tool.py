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
from . import JsonValue, _deny_unknown, _json_mapping, _required_agent_metadata_path, _required_str, successful_empty_message_output

@dataclass(frozen=True)
class SendMessageArgs:
    target: str
    message: str

    @classmethod
    def from_json(cls, arguments: str) -> 'SendMessageArgs':
        data = _json_mapping(arguments, 'send_message arguments')
        _deny_unknown(data, {'target', 'message'}, 'send_message arguments')
        return cls(target=_required_str(data, 'target'), message=_required_str(data, 'message'))

@dataclass(frozen=True)
class FollowupTaskArgs:
    target: str
    message: str

    @classmethod
    def from_json(cls, arguments: str) -> 'FollowupTaskArgs':
        data = _json_mapping(arguments, 'followup_task arguments')
        _deny_unknown(data, {'target', 'message'}, 'followup_task arguments')
        return cls(target=_required_str(data, 'target'), message=_required_str(data, 'message'))

class MessageDeliveryMode(str, Enum):
    QUEUE_ONLY = 'queue_only'
    TRIGGER_TURN = 'trigger_turn'

    def apply(self, communication: dict[str, JsonValue] | InterAgentCommunication) -> dict[str, JsonValue] | InterAgentCommunication:
        if isinstance(communication, InterAgentCommunication):
            return replace(communication, trigger_turn=self is MessageDeliveryMode.TRIGGER_TURN)
        if not isinstance(communication, dict):
            raise TypeError('communication must be a mapping or InterAgentCommunication')
        output = dict(communication)
        output['trigger_turn'] = self is MessageDeliveryMode.TRIGGER_TURN
        return output

def message_content(message: str) -> str:
    if not isinstance(message, str):
        raise TypeError('message must be a string')
    if message.strip() == '':
        raise FunctionCallError.respond_to_model("Empty message can't be sent to an agent")
    return message

def handle_message_string_tool(*, mode: MessageDeliveryMode, target: str, message: str, send_message: Callable[[MessageDeliveryMode, str, str], FunctionToolOutput | None], get_agent_metadata: Callable[[str], Any] | None=None) -> FunctionToolOutput:
    prompt = message_content(message)
    if get_agent_metadata is not None:
        receiver_agent_path = _required_agent_metadata_path(get_agent_metadata(target))
        if mode is MessageDeliveryMode.TRIGGER_TURN and receiver_agent_path.is_root():
            raise FunctionCallError.respond_to_model("Tasks can't be assigned to the root agent")
    result = send_message(mode, target, prompt)
    if result is None:
        return successful_empty_message_output()
    if not isinstance(result, FunctionToolOutput):
        raise TypeError('send_message callback must return FunctionToolOutput or None')
    return result
__all__ = ['FollowupTaskArgs', 'MessageDeliveryMode', 'SendMessageArgs', 'handle_message_string_tool', 'message_content']
