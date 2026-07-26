"""V1 wait handler owned by the Rust ``multi_agents::wait`` module."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers.multi_agents_common import DEFAULT_WAIT_TIMEOUT_MS
from pycodex.core.tools.handlers.multi_agents_common import MAX_WAIT_TIMEOUT_MS
from pycodex.core.tools.handlers.multi_agents_common import MIN_WAIT_TIMEOUT_MS
from pycodex.core.tools.handlers.multi_agents_common import function_arguments
from pycodex.core.tools.handlers.multi_agents_spec import MULTI_AGENT_V1_NAMESPACE
from pycodex.core.tools.handlers.multi_agents_spec import WaitAgentTimeoutOptions
from pycodex.core.tools.handlers.multi_agents_spec import create_wait_agent_tool_v1
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.protocol import AgentStatus, ThreadId, ToolName

from . import JsonValue
from . import V1WaitAgentResult
from . import V1WaitArgs
from . import _wait_agent_from_invocation
from . import multi_agent_tool_search_info


class Handler:
    def __init__(
        self,
        options: WaitAgentTimeoutOptions | None = None,
        wait_agent: Callable[
            [tuple[ThreadId, ...], int],
            Mapping[str, AgentStatus | str | dict[str, JsonValue]],
        ]
        | None = None,
    ) -> None:
        self.options = options or WaitAgentTimeoutOptions()
        self._wait_agent = wait_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "wait_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_wait_agent_tool_v1(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return multi_agent_tool_search_info(
            "wait_agent wait agent subagent status final result complete timeout targets",
            self.spec(),
        )

    def handle(
        self,
        invocation: ToolInvocation,
        min_timeout_ms: int = MIN_WAIT_TIMEOUT_MS,
        default_timeout_ms: int = DEFAULT_WAIT_TIMEOUT_MS,
        max_timeout_ms: int = MAX_WAIT_TIMEOUT_MS,
    ) -> V1WaitAgentResult:
        args = V1WaitArgs.from_json(function_arguments(invocation.payload))
        targets = args.receiver_thread_ids()
        timeout_ms = args.resolve_timeout_ms(
            min_timeout_ms,
            default_timeout_ms,
            max_timeout_ms,
        )
        if self._wait_agent is None:
            status = _wait_agent_from_invocation(invocation, targets, timeout_ms)
        else:
            status = self._wait_agent(targets, timeout_ms)
        return V1WaitAgentResult(status, len(status) == 0)


__all__ = ["Handler"]
