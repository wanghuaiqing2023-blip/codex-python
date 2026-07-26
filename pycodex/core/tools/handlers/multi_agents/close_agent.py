"""V1 close handler owned by the Rust ``multi_agents::close_agent`` module."""

from __future__ import annotations

from collections.abc import Callable

from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers.multi_agents_common import function_arguments
from pycodex.core.tools.handlers.multi_agents_spec import MULTI_AGENT_V1_NAMESPACE
from pycodex.core.tools.handlers.multi_agents_spec import create_close_agent_tool_v1
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.protocol import AgentStatus, ThreadId, ToolName

from . import JsonValue
from . import V1CloseAgentArgs
from . import V1CloseAgentResult
from . import _close_agent_from_invocation
from . import multi_agent_tool_search_info


class Handler:
    def __init__(
        self,
        close_agent: Callable[
            [ThreadId], AgentStatus | str | dict[str, JsonValue]
        ]
        | None = None,
    ) -> None:
        self._close_agent = close_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "close_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_close_agent_tool_v1()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return multi_agent_tool_search_info(
            "close_agent close shutdown stop agent subagent thread status target",
            self.spec(),
        )

    def handle(self, invocation: ToolInvocation) -> V1CloseAgentResult:
        args = V1CloseAgentArgs.from_json(function_arguments(invocation.payload))
        if self._close_agent is None:
            return V1CloseAgentResult(
                _close_agent_from_invocation(invocation, args.agent_id())
            )
        return V1CloseAgentResult(
            AgentStatus.from_mapping(self._close_agent(args.agent_id()))
        )


__all__ = ["Handler"]
