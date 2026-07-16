"""Goal tool executors aligned with ``codex-goal-extension::tool``."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.handlers.goal import (
    CreateGoalRequest,
    goal_response,
    parse_create_goal_arguments,
    parse_update_goal_arguments,
)
from pycodex.core.tools.router import FunctionCallError
from pycodex.protocol import ThreadGoal, ThreadGoalStatus, ToolName, validate_thread_goal_objective
from pycodex.state import GoalAccountingMode, GoalUpdate, ThreadGoalStatus as StateGoalStatus

from .accounting import BudgetLimitedGoalDisposition, GoalAccountingState
from .events import GoalEventEmitter
from .spec import (
    CREATE_GOAL_TOOL_NAME,
    GET_GOAL_TOOL_NAME,
    UPDATE_GOAL_TOOL_NAME,
    create_create_goal_tool,
    create_get_goal_tool,
    create_update_goal_tool,
)


class GoalToolKind(str, Enum):
    GET = "get"
    CREATE = "create"
    UPDATE = "update"


class GoalToolExecutor:
    def __init__(
        self,
        kind: GoalToolKind,
        thread_id: Any,
        state_dbs: Any,
        accounting_state: GoalAccountingState,
        event_emitter: GoalEventEmitter,
    ) -> None:
        self.kind = GoalToolKind(kind)
        self.thread_id = thread_id
        self.state_dbs = state_dbs
        self.accounting_state = accounting_state
        self.event_emitter = event_emitter

    @classmethod
    def get(cls, *args: Any) -> "GoalToolExecutor":
        return cls(GoalToolKind.GET, *args)

    @classmethod
    def create(cls, *args: Any) -> "GoalToolExecutor":
        return cls(GoalToolKind.CREATE, *args)

    @classmethod
    def update(cls, *args: Any) -> "GoalToolExecutor":
        return cls(GoalToolKind.UPDATE, *args)

    def tool_name(self) -> ToolName:
        return ToolName.plain(
            {
                GoalToolKind.GET: GET_GOAL_TOOL_NAME,
                GoalToolKind.CREATE: CREATE_GOAL_TOOL_NAME,
                GoalToolKind.UPDATE: UPDATE_GOAL_TOOL_NAME,
            }[self.kind]
        )

    def spec(self) -> dict[str, Any]:
        return {
            GoalToolKind.GET: create_get_goal_tool,
            GoalToolKind.CREATE: create_create_goal_tool,
            GoalToolKind.UPDATE: create_update_goal_tool,
        }[self.kind]()

    def supports_parallel_tool_calls(self) -> bool:
        return False

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type in {"function", "tool_search"}

    async def handle(self, invocation: Any) -> Any:
        payload = getattr(invocation, "payload", invocation)
        if not isinstance(payload, ToolPayload) or payload.type != "function":
            raise FunctionCallError.respond_to_model("goal handler received unsupported payload")
        if self.kind is GoalToolKind.GET:
            return await self._handle_get()
        if payload.arguments is None:
            raise FunctionCallError.respond_to_model("goal handler received unsupported payload")
        if self.kind is GoalToolKind.CREATE:
            return await self._handle_create(invocation, payload.arguments)
        return await self._handle_update(invocation, payload.arguments)

    async def _handle_get(self) -> Any:
        try:
            state_goal = await _maybe_await(self._thread_goals().get_thread_goal(self.thread_id))
        except Exception as err:
            raise FunctionCallError.respond_to_model(f"failed to read goal: {err}") from err
        goal = None if state_goal is None else protocol_goal_from_state(state_goal)
        return goal_response(goal, include_completion_budget_report=False)

    async def _handle_create(self, invocation: Any, arguments: str) -> Any:
        args = parse_create_goal_arguments(arguments)
        objective = args.objective.strip()
        try:
            validate_thread_goal_objective(objective)
            if args.token_budget is not None and args.token_budget <= 0:
                raise ValueError("goal budgets must be positive when provided")
            state_goal = await _maybe_await(
                self._thread_goals().insert_thread_goal(
                    self.thread_id,
                    objective,
                    StateGoalStatus.ACTIVE,
                    args.token_budget,
                )
            )
        except Exception as err:
            raise FunctionCallError.respond_to_model(f"failed to create goal: {err}") from err
        if state_goal is None:
            raise FunctionCallError.respond_to_model(
                "cannot create a new goal because this thread already has a goal; "
                "use update_goal only when the existing goal is complete"
            )
        await self._fill_empty_thread_preview(state_goal.objective)
        turn_id = self.accounting_state.mark_current_turn_goal_active(state_goal.goal_id)
        goal = protocol_goal_from_state(state_goal)
        await self.event_emitter.thread_goal_updated(invocation.call_id, turn_id, goal)
        return goal_response(goal, include_completion_budget_report=False)

    async def _handle_update(self, invocation: Any, arguments: str) -> Any:
        args = parse_update_goal_arguments(arguments)
        if args.status not in {ThreadGoalStatus.COMPLETE, ThreadGoalStatus.BLOCKED}:
            raise FunctionCallError.respond_to_model(
                "update_goal can only mark the existing goal complete or blocked; pause, resume, "
                "budget-limited, and usage-limited status changes are controlled by the user or system"
            )
        mode = (
            GoalAccountingMode.ACTIVE_OR_COMPLETE
            if args.status is ThreadGoalStatus.COMPLETE
            else GoalAccountingMode.ACTIVE_OR_STOPPED
        )
        await self._account_active_goal_progress(
            mode,
            invocation.call_id,
            BudgetLimitedGoalDisposition.CLEAR_ACTIVE,
        )
        try:
            state_goal = await _maybe_await(
                self._thread_goals().update_thread_goal(
                    self.thread_id,
                    GoalUpdate(status=_state_status_from_protocol(args.status)),
                )
            )
        except Exception as err:
            raise FunctionCallError.respond_to_model(f"failed to update goal: {err}") from err
        if state_goal is None:
            raise FunctionCallError.respond_to_model("cannot update goal because this thread has no goal")
        goal = protocol_goal_from_state(state_goal)
        turn_id = self.accounting_state.clear_current_turn_goal()
        await self.event_emitter.thread_goal_updated(invocation.call_id, turn_id, goal)
        return goal_response(
            goal,
            include_completion_budget_report=args.status is ThreadGoalStatus.COMPLETE,
        )

    async def _account_active_goal_progress(
        self,
        mode: GoalAccountingMode,
        event_id: str,
        disposition: BudgetLimitedGoalDisposition,
    ) -> ThreadGoal | None:
        turn_id = self.accounting_state.current_turn_id()
        if turn_id is None:
            return None
        snapshot = self.accounting_state.progress_snapshot(turn_id)
        if snapshot is None:
            return None
        try:
            outcome = await _maybe_await(
                self._thread_goals().account_thread_goal_usage(
                    self.thread_id,
                    snapshot.time_delta_seconds,
                    snapshot.token_delta,
                    mode,
                    snapshot.expected_goal_id,
                )
            )
        except Exception as err:
            raise FunctionCallError.respond_to_model(f"failed to account goal progress: {err}") from err
        if not bool(getattr(outcome, "updated", False)):
            return None
        state_goal = outcome.goal
        self.accounting_state.mark_progress_accounted_for_status(
            turn_id,
            snapshot,
            state_goal.status,
            disposition,
        )
        goal = protocol_goal_from_state(state_goal)
        await self.event_emitter.thread_goal_updated(event_id, turn_id, goal)
        return goal

    async def _fill_empty_thread_preview(self, objective: str) -> None:
        threads = getattr(self.state_dbs, "threads", None)
        threads = threads() if callable(threads) else threads
        setter = getattr(threads, "set_thread_preview_if_empty", None)
        if callable(setter):
            try:
                await _maybe_await(setter(self.thread_id, objective))
            except Exception:
                pass

    def _thread_goals(self) -> Any:
        value = getattr(self.state_dbs, "thread_goals", None)
        value = value() if callable(value) else value
        if value is None:
            raise RuntimeError("state DB must provide thread_goals")
        return value


def protocol_goal_from_state(goal: Any) -> ThreadGoal:
    return ThreadGoal(
        thread_id=goal.thread_id,
        objective=goal.objective,
        status=ThreadGoalStatus(goal.status.value),
        token_budget=goal.token_budget,
        tokens_used=goal.tokens_used,
        time_used_seconds=goal.time_used_seconds,
        created_at=_epoch_seconds(goal.created_at),
        updated_at=_epoch_seconds(goal.updated_at),
    )


def _state_status_from_protocol(status: ThreadGoalStatus) -> StateGoalStatus:
    return StateGoalStatus(status.value)


def _epoch_seconds(value: Any) -> int:
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return int(timestamp())
    raw = int(value)
    return raw // 1000 if raw > 10_000_000_000 else raw


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "CreateGoalRequest",
    "GoalToolExecutor",
    "GoalToolKind",
    "protocol_goal_from_state",
]
