from __future__ import annotations

import inspect
from typing import Any

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.handlers import goal_spec
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ToolName

from . import (
    GoalStore,
    InMemoryGoalStore,
    _await_goal_response,
    _call_goal_store,
    _checked_goal_result,
    _format_goal_error,
    _payload,
    goal_response,
)


class GetGoalHandler:
    def __init__(self, store: GoalStore | None = None) -> None:
        self.store = store or InMemoryGoalStore()
        self._store_provided = store is not None

    def tool_name(self) -> ToolName:
        return ToolName.plain(goal_spec.GET_GOAL_TOOL_NAME)

    def spec(self) -> dict[str, Any]:
        return goal_spec.create_get_goal_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | Any:
        payload = _payload(invocation_or_payload)
        if payload.type != "function":
            raise FunctionCallError.respond_to_model("get_goal handler received unsupported payload")
        session = getattr(invocation_or_payload, "session", None)
        getter = getattr(session, "get_thread_goal", None)
        if callable(getter) and not self._store_provided:
            try:
                goal = getter()
            except Exception as err:
                raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
            if inspect.isawaitable(goal):
                return _await_goal_response(goal, include_completion_budget_report=False)
            goal = _checked_goal_result(goal)
        else:
            goal = _call_goal_store(self.store.get_thread_goal)
        return goal_response(goal, include_completion_budget_report=False)


__all__ = ["GetGoalHandler"]
