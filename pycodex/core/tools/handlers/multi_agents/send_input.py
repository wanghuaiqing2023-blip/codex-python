"""Multi-agent v1 handler facades ported from Codex core.

These helpers mirror the pure boundary layer from
``core/src/tools/handlers/multi_agents``: namespaced tool names, argument
parsing, target id validation, v1 wait timeout semantics, result serialization,
and tool-search metadata. Real ``agent_control`` operations are represented by
small callbacks so this port stays stdlib-only.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Callable

from pycodex.core.agent import exceeds_thread_spawn_depth_limit, next_thread_spawn_depth
from pycodex.core.agent.control import SpawnAgentForkMode, SpawnAgentOptions
from pycodex.core.agent.status import is_final
from pycodex.core.tools.handlers.multi_agents_common import (
    DEFAULT_WAIT_TIMEOUT_MS,
    MAX_WAIT_TIMEOUT_MS,
    MIN_WAIT_TIMEOUT_MS,
    apply_requested_spawn_agent_model_overrides,
    apply_spawn_agent_runtime_overrides,
    apply_spawn_agent_service_tier,
    apply_spawn_agent_overrides,
    collab_agent_error,
    collab_spawn_error,
    build_agent_spawn_config,
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
    create_close_agent_tool_v1,
    create_send_input_tool_v1,
    create_spawn_agent_tool_v1,
    create_wait_agent_tool_v1,
)
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.tools.tool_discovery import ToolSearchSourceInfo
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import AgentStatus, Op, ResponseInputItem, SessionSource, ThreadId, ToolName, UserInput

JsonValue = Any
MULTI_AGENT_TOOL_SEARCH_SOURCE_NAME = "Multi-agent tools"
MULTI_AGENT_TOOL_SEARCH_SOURCE_DESCRIPTION = "Spawn and manage sub-agents."



from . import (
    _coerce_v1_user_inputs,
    _json_mapping,
    _optional_bool,
    _optional_str,
    _required_str,
    parse_agent_id_target,
)
from . import _send_input_from_invocation

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
        return _coerce_v1_user_inputs(parse_collab_input(self.message, self.items))

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


class Handler:
    def __init__(
        self,
        send_input: Callable[[ThreadId, tuple[UserInput, ...], bool], str] | None = None,
    ) -> None:
        self._send_input = send_input

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "send_input")

    def spec(self) -> dict[str, JsonValue]:
        return create_send_input_tool_v1()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return ToolSearchInfo.from_spec(
            "send_input send message existing agent subagent follow up interrupt redirect queue target",
            self.spec(),
            ToolSearchSourceInfo(
                MULTI_AGENT_TOOL_SEARCH_SOURCE_NAME,
                MULTI_AGENT_TOOL_SEARCH_SOURCE_DESCRIPTION,
            ),
        )

    def parse_args(self, payload: ToolPayload) -> SendInputArgs:
        return SendInputArgs.from_json(function_arguments(payload))

    def handle(self, invocation: ToolInvocation) -> SendInputResult:
        args = self.parse_args(invocation.payload)
        if self._send_input is None:
            submission_id = _send_input_from_invocation(invocation, args)
        else:
            submission_id = self._send_input(
                args.receiver_thread_id(),
                args.input_items(),
                args.interrupt,
            )
        return SendInputResult(submission_id)


__all__ = ["Handler", "SendInputArgs", "SendInputResult"]

