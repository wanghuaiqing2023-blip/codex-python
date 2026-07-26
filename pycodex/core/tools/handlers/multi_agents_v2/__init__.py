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
from pycodex.core.tools.handlers.multi_agents_common import DEFAULT_WAIT_TIMEOUT_MS, MAX_WAIT_TIMEOUT_MS, MIN_WAIT_TIMEOUT_MS, apply_requested_spawn_agent_model_overrides, apply_spawn_agent_runtime_overrides, apply_spawn_agent_service_tier, apply_spawn_agent_overrides, build_agent_spawn_config, collab_spawn_error, function_arguments, parse_collab_input, reject_full_fork_spawn_overrides, thread_spawn_source, tool_output_code_mode_result, tool_output_json_text, tool_output_response_item
from pycodex.core.tools.handlers.multi_agents_spec import MULTI_AGENT_V1_NAMESPACE, SpawnAgentToolOptions, WaitAgentTimeoutOptions, create_close_agent_tool_v2, create_followup_task_tool, create_list_agents_tool, create_resume_agent_tool, create_send_message_tool, create_spawn_agent_tool_v2, create_wait_agent_tool_v2
from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.tools.tool_discovery import ToolSearchSourceInfo
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentPath, AgentStatus, InterAgentCommunication, Op, ResponseInputItem, SessionSource, ThreadId, ToolName, UserInput
JsonValue = Any

def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f'{label} must be a mapping')
    return value

def _json_mapping(arguments: str, label: str) -> dict[str, JsonValue]:
    return _mapping(json.loads(arguments), label)

def _deny_unknown(data: dict[str, JsonValue], allowed: set[str], label: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f'unknown field in {label}: {sorted(unknown)[0]}')

def _required_str(data: dict[str, JsonValue], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise TypeError(f'{key} must be a string')
    return value

def _optional_str(data: dict[str, JsonValue], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f'{key} must be a string')
    return value

def _agent_metadata_path(metadata: Any) -> AgentPath | None:
    if metadata is None:
        return None
    value = metadata.get('agent_path') if isinstance(metadata, dict) else getattr(metadata, 'agent_path', None)
    if value is None:
        return None
    return value if isinstance(value, AgentPath) else AgentPath.from_string(str(value))

def _required_agent_metadata_path(metadata: Any) -> AgentPath:
    agent_path = _agent_metadata_path(metadata)
    if agent_path is None:
        raise FunctionCallError.respond_to_model('target agent is missing an agent_path')
    return agent_path

def successful_empty_message_output() -> FunctionToolOutput:
    return FunctionToolOutput.from_text('', True)

def _agent_control_from_session(session: Any) -> Any:
    services = getattr(session, 'services', None)
    agent_control = getattr(services, 'agent_control', None)
    if agent_control is None:
        agent_control = getattr(session, 'agent_control', None)
    if agent_control is None:
        raise FunctionCallError.respond_to_model('agent control is unavailable in this session')
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
            result['value'] = asyncio.run(value)
        except BaseException as err:
            result['error'] = err
    import threading
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join()
    if 'error' in result:
        raise result['error']
    return result.get('value')
__all__ = ['CloseAgentArgs', 'CloseAgentHandler', 'CloseAgentResult', 'FollowupTaskArgs', 'FollowupTaskHandler', 'ListAgentsArgs', 'ListAgentsHandler', 'ListAgentsResult', 'MessageDeliveryMode', 'SendMessageArgs', 'SendMessageHandler', 'SpawnAgentArgs', 'SpawnAgentFork', 'SpawnAgentForkMode', 'SpawnAgentHandler', 'SpawnAgentResult', 'WaitAgentHandler', 'WaitAgentResult', 'WaitArgs', 'handle_message_string_tool', 'message_content', 'successful_empty_message_output']

from .close_agent import CloseAgentArgs, CloseAgentHandler, CloseAgentResult
from .followup_task import FollowupTaskHandler
from .list_agents import ListAgentsArgs, ListAgentsHandler, ListAgentsResult
from .message_tool import FollowupTaskArgs, MessageDeliveryMode, SendMessageArgs, handle_message_string_tool, message_content
from .send_message import SendMessageHandler
from .spawn import SpawnAgentArgs, SpawnAgentFork, SpawnAgentForkMode, SpawnAgentHandler, SpawnAgentResult
from .wait import WaitAgentHandler, WaitAgentResult, WaitArgs
