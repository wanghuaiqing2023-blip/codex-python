from __future__ import annotations

from typing import Any

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.handlers import goal_spec
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ThreadGoalStatus, ToolName

from . import (
    GoalStore,
    InMemoryGoalStore,
    SetGoalRequest,
    UPDATE_GOAL_STATUS_ERROR,
    _format_goal_error,
    _handle_update_goal_with_session,
    _payload,
    goal_response,
    parse_update_goal_arguments,
)


class UpdateGoalHandler:
    def __init__(self, store: GoalStore | None = None) -> None:
        self.store = store or InMemoryGoalStore()
        self._store_provided = store is not None

    def tool_name(self) -> ToolName:
        return ToolName.plain(goal_spec.UPDATE_GOAL_TOOL_NAME)

    def spec(self) -> dict[str, Any]:
        return goal_spec.create_update_goal_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | Any:
        payload = _payload(invocation_or_payload)
        if payload.type != "function" or payload.arguments is None:
            raise FunctionCallError.respond_to_model("update_goal handler received unsupported payload")
        args = parse_update_goal_arguments(payload.arguments)
        if args.status not in (ThreadGoalStatus.COMPLETE, ThreadGoalStatus.BLOCKED):
            raise FunctionCallError.respond_to_model(UPDATE_GOAL_STATUS_ERROR)
        request = SetGoalRequest(status=args.status)
        session = getattr(invocation_or_payload, "session", None)
        if not self._store_provided and callable(getattr(session, "set_thread_goal", None)):
            return _handle_update_goal_with_session(invocation_or_payload, session, request, args.status)
        try:
            self.store.goal_runtime_tool_completed_goal()
            goal = self.store.set_thread_goal(request)
        except Exception as err:
            raise FunctionCallError.respond_to_model(_format_goal_error(err)) from err
        return goal_response(goal, include_completion_budget_report=args.status is ThreadGoalStatus.COMPLETE)


__all__ = ["UpdateGoalHandler"]
