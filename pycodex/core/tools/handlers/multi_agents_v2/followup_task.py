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
from . import JsonValue
from .message_tool import FollowupTaskArgs, MessageDeliveryMode, handle_message_string_tool, message_content

class FollowupTaskHandler:

    def __init__(self, send_message: Callable[[MessageDeliveryMode, str, str], FunctionToolOutput | None] | None=None, get_agent_metadata: Callable[[str], Any] | None=None) -> None:
        self._send_message = send_message
        self._get_agent_metadata = get_agent_metadata

    def tool_name(self) -> ToolName:
        return ToolName.plain('followup_task')

    def spec(self) -> dict[str, JsonValue]:
        return create_followup_task_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == 'function'

    def parse_args(self, payload: ToolPayload) -> FollowupTaskArgs:
        args = FollowupTaskArgs.from_json(function_arguments(payload))
        message_content(args.message)
        return args

    def handle(self, invocation: ToolInvocation) -> FunctionToolOutput:
        args = self.parse_args(invocation.payload)
        if self._send_message is None:
            raise FunctionCallError.respond_to_model('agent control is unavailable in this session')
        return handle_message_string_tool(mode=MessageDeliveryMode.TRIGGER_TURN, target=args.target, message=args.message, send_message=self._send_message, get_agent_metadata=self._get_agent_metadata)
__all__ = ['FollowupTaskHandler']
