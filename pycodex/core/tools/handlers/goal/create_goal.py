from __future__ import annotations

import inspect
from typing import Any

from pycodex.core.tools.context import FunctionToolOutput, ToolPayload
from pycodex.core.tools.handlers import goal_spec
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ToolName

from . import (
    CreateGoalRequest,
    GoalStore,
    InMemoryGoalStore,
    _await_create_goal_response,
    _checked_goal_result,
    _format_goal_error,
    _payload,
    goal_response,
    parse_create_goal_arguments,
)


class CreateGoalHandler:
    def __init__(self, store: GoalStore | None = None) -> None:
        self.store = store or InMemoryGoalStore()
        self._store_provided = store is not None

    def tool_name(self) -> ToolName:
        return ToolName.plain(goal_spec.CREATE_GOAL_TOOL_NAME)

    def spec(self) -> dict[str, Any]:
        return goal_spec.create_create_goal_tool()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        if not isinstance(payload, ToolPayload):
            raise TypeError("payload must be ToolPayload")
        return payload.type in {"function", "tool_search"}

    def handle(self, invocation_or_payload: Any) -> FunctionToolOutput | Any:
        payload = _payload(invocation_or_payload)
        if payload.type != "function" or payload.arguments is None:
            raise FunctionCallError.respond_to_model("goal handler received unsupported payload")
        args = parse_create_goal_arguments(payload.arguments)
        request = CreateGoalRequest(args.objective, args.token_budget)
        session = getattr(invocation_or_payload, "session", None)
        creator = getattr(session, "create_thread_goal", None)
        if callable(creator) and not self._store_provided:
            try:
                goal = creator(getattr(invocation_or_payload, "turn", None), request)
            except Exception as err:
                message = _format_goal_error(err)
                if "already has a goal" in message:
                    raise FunctionCallError.respond_to_model(
                        "cannot create a new goal because this thread already has a goal; use update_goal only when the existing goal is complete"
                    ) from err
                raise FunctionCallError.respond_to_model(message) from err
            if inspect.isawaitable(goal):
                return _await_create_goal_response(goal)
            return goal_response(_checked_goal_result(goal), include_completion_budget_report=False)
        try:
            goal = self.store.create_thread_goal(request)
        except Exception as err:
            message = _format_goal_error(err)
            if "already has a goal" in message:
                raise FunctionCallError.respond_to_model(
                    "cannot create a new goal because this thread already has a goal; use update_goal only when the existing goal is complete"
                ) from err
            raise FunctionCallError.respond_to_model(message) from err
        return goal_response(goal, include_completion_budget_report=False)


__all__ = ["CreateGoalHandler"]
