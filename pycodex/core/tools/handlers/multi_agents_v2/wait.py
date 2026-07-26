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
from . import JsonValue, _deny_unknown, _json_mapping

@dataclass(frozen=True)
class WaitArgs:
    timeout_ms: int | None = None

    def __post_init__(self) -> None:
        if self.timeout_ms is not None and (isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int)):
            raise TypeError('timeout_ms must be an integer')

    @classmethod
    def from_json(cls, arguments: str) -> 'WaitArgs':
        data = _json_mapping(arguments, 'wait_agent arguments')
        _deny_unknown(data, {'timeout_ms'}, 'wait_agent arguments')
        value = data.get('timeout_ms')
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise TypeError('timeout_ms must be an integer')
        return cls(timeout_ms=value)

    def resolve_timeout_ms(self, min_timeout_ms: int=MIN_WAIT_TIMEOUT_MS, default_timeout_ms: int=DEFAULT_WAIT_TIMEOUT_MS, max_timeout_ms: int=MAX_WAIT_TIMEOUT_MS) -> int:
        value = default_timeout_ms if self.timeout_ms is None else self.timeout_ms
        if value < min_timeout_ms:
            raise FunctionCallError.respond_to_model(f'timeout_ms must be at least {min_timeout_ms}')
        if value > max_timeout_ms:
            raise FunctionCallError.respond_to_model(f'timeout_ms must be at most {max_timeout_ms}')
        return value

def _wait_timeout_bounds_from_turn(turn: Any, min_timeout_ms: int, default_timeout_ms: int, max_timeout_ms: int) -> tuple[int, int, int]:
    config = getattr(turn, 'config', None)
    multi_agent_v2 = getattr(config, 'multi_agent_v2', None)
    if multi_agent_v2 is None:
        return (min_timeout_ms, default_timeout_ms, max_timeout_ms)
    return (_timeout_bound(getattr(multi_agent_v2, 'min_wait_timeout_ms', None), min_timeout_ms, 'min_wait_timeout_ms'), _timeout_bound(getattr(multi_agent_v2, 'default_wait_timeout_ms', None), default_timeout_ms, 'default_wait_timeout_ms'), _timeout_bound(getattr(multi_agent_v2, 'max_wait_timeout_ms', None), max_timeout_ms, 'max_wait_timeout_ms'))

def _timeout_bound(value: Any, fallback: int, name: str) -> int:
    if value is None:
        return fallback
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{name} must be an integer')
    return value

@dataclass(frozen=True)
class WaitAgentResult:
    message: str
    timed_out: bool

    @classmethod
    def from_timed_out(cls, timed_out: bool) -> 'WaitAgentResult':
        return cls('Wait timed out.' if timed_out else 'Wait completed.', timed_out)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {'message': self.message, 'timed_out': self.timed_out}

    def log_preview(self) -> str:
        return tool_output_json_text(self, 'wait_agent')

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return tool_output_response_item(call_id, payload, self, None, 'wait_agent')

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return tool_output_code_mode_result(self, 'wait_agent')

class WaitAgentHandler:

    def __init__(self, options: WaitAgentTimeoutOptions | None=None, wait_for_change: Callable[[int], bool] | None=None) -> None:
        self.options = options or WaitAgentTimeoutOptions()
        self._wait_for_change = wait_for_change

    def tool_name(self) -> ToolName:
        return ToolName.plain('wait_agent')

    def spec(self) -> dict[str, JsonValue]:
        return create_wait_agent_tool_v2(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == 'function'

    def parse_args(self, payload: ToolPayload) -> WaitArgs:
        return WaitArgs.from_json(function_arguments(payload))

    def handle(self, invocation: ToolInvocation, min_timeout_ms: int=MIN_WAIT_TIMEOUT_MS, default_timeout_ms: int=DEFAULT_WAIT_TIMEOUT_MS, max_timeout_ms: int=MAX_WAIT_TIMEOUT_MS) -> WaitAgentResult:
        min_timeout_ms, default_timeout_ms, max_timeout_ms = _wait_timeout_bounds_from_turn(getattr(invocation, 'turn', None), min_timeout_ms, default_timeout_ms, max_timeout_ms)
        timeout_ms = self.parse_args(invocation.payload).resolve_timeout_ms(min_timeout_ms, default_timeout_ms, max_timeout_ms)
        if self._wait_for_change is None:
            raise FunctionCallError.respond_to_model('agent mailbox is unavailable in this session')
        completed = self._wait_for_change(timeout_ms)
        if not isinstance(completed, bool):
            raise TypeError('wait_for_change callback must return a bool')
        return WaitAgentResult.from_timed_out(not completed)
__all__ = ['WaitAgentHandler', 'WaitAgentResult', 'WaitArgs']
