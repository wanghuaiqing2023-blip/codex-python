"""V1 spawn handler owned by the Rust ``multi_agents::spawn`` module."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers.multi_agents_common import function_arguments
from pycodex.core.tools.handlers.multi_agents_spec import MULTI_AGENT_V1_NAMESPACE
from pycodex.core.tools.handlers.multi_agents_spec import SpawnAgentToolOptions
from pycodex.core.tools.handlers.multi_agents_spec import create_spawn_agent_tool_v1
from pycodex.core.tools.registry import ToolInvocation
from pycodex.core.tools.tool_search_entry import ToolSearchInfo
from pycodex.protocol import ToolName

from . import JsonValue
from . import V1SpawnAgentArgs
from . import V1SpawnAgentResult
from . import _mapping
from . import _optional_str
from . import _required_str
from . import _spawn_agent_from_invocation
from . import multi_agent_tool_search_info


class Handler:
    def __init__(
        self,
        options: SpawnAgentToolOptions | None = None,
        spawn_agent: Callable[
            [V1SpawnAgentArgs],
            V1SpawnAgentResult | Mapping[str, JsonValue],
        ]
        | None = None,
    ) -> None:
        self.options = options or SpawnAgentToolOptions()
        self._spawn_agent = spawn_agent

    def tool_name(self) -> ToolName:
        return ToolName.namespaced(MULTI_AGENT_V1_NAMESPACE, "spawn_agent")

    def spec(self) -> dict[str, JsonValue]:
        return create_spawn_agent_tool_v1(self.options)

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def search_info(self) -> ToolSearchInfo | None:
        return multi_agent_tool_search_info(
            "spawn_agent spawn agent subagent sub-agent delegate delegation parallel work worker explorer no-apps fork model reasoning",
            self.spec(),
        )

    def parse_args(self, payload: ToolPayload) -> V1SpawnAgentArgs:
        args = V1SpawnAgentArgs.from_json(function_arguments(payload))
        args.validate_for_spawn()
        return args

    def handle(self, invocation: ToolInvocation) -> V1SpawnAgentResult:
        args = self.parse_args(invocation.payload)
        if self._spawn_agent is None:
            result = _spawn_agent_from_invocation(invocation, args)
        else:
            result = self._spawn_agent(args)
        if isinstance(result, V1SpawnAgentResult):
            return result
        data = _mapping(result, "spawn_agent result")
        return V1SpawnAgentResult(
            agent_id=_required_str(data, "agent_id"),
            nickname=_optional_str(data, "nickname"),
        )


__all__ = ["Handler"]
