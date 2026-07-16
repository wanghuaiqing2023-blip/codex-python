"""Goal runtime handle aligned with ``codex-goal-extension::runtime``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pycodex.protocol import ModeKind, ThreadGoalStatus
from pycodex.state import GoalAccountingMode, ThreadGoalStatus as StateGoalStatus

from .accounting import BudgetLimitedGoalDisposition, GoalAccountingState
from .steering import budget_limit_steering_item, objective_updated_steering_item
from .tool import protocol_goal_from_state


@dataclass(frozen=True)
class PreviousGoalSnapshot:
    goal_id: str
    status: StateGoalStatus
    objective: str


@dataclass(frozen=True)
class AccountedGoalProgress:
    goal: Any
    goal_id: str


class GoalRuntimeHandle:
    def __init__(
        self,
        session: Any,
        state_dbs: Any,
        *,
        thread_id: Any = None,
        event_emitter: Any = None,
        enabled: bool,
    ) -> None:
        self.session = session
        self.state_dbs = state_dbs
        self.thread_id = thread_id
        self.event_emitter = event_emitter
        self.accounting_state = GoalAccountingState()
        self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    async def restore_after_resume(self) -> None:
        if not self._enabled:
            return
        goal = await self._state_goal()
        if goal is not None and goal.status is StateGoalStatus.ACTIVE:
            self.accounting_state.mark_idle_goal_active(goal.goal_id)
        else:
            self.accounting_state.clear_active_goal()

    async def prepare_external_goal_mutation(self) -> None:
        if not self._enabled:
            return
        turn_id = self.accounting_state.current_turn_id()
        if turn_id is not None:
            await self.account_active_goal_progress(
                turn_id,
                f"{turn_id}:external-goal-mutation",
                GoalAccountingMode.ACTIVE_ONLY,
                BudgetLimitedGoalDisposition.CLEAR_ACTIVE,
            )
            return
        await self.account_idle_goal_progress(
            f"{self._thread_id()}:external-goal-mutation",
            GoalAccountingMode.ACTIVE_ONLY,
            BudgetLimitedGoalDisposition.CLEAR_ACTIVE,
        )

    async def apply_external_goal_set(
        self,
        goal: Any,
        previous_goal: PreviousGoalSnapshot | None = None,
    ) -> None:
        if not self._enabled:
            return
        if goal.status is StateGoalStatus.ACTIVE:
            if self.accounting_state.current_turn_id() is None:
                self.accounting_state.mark_idle_goal_active(goal.goal_id)
            else:
                self.accounting_state.mark_current_turn_goal_active(goal.goal_id)
            changed = (
                previous_goal is None
                or previous_goal.goal_id != goal.goal_id
                or previous_goal.status is not StateGoalStatus.ACTIVE
                or previous_goal.objective != goal.objective
            )
            if changed:
                await self.inject_objective_updated_steering(goal)
        elif goal.status is StateGoalStatus.BUDGET_LIMITED:
            if self.accounting_state.current_turn_id() is None:
                self.accounting_state.clear_active_goal()
        else:
            self.accounting_state.clear_active_goal()

    async def apply_external_goal_clear(self) -> None:
        if self._enabled:
            self.accounting_state.clear_active_goal()

    async def maybe_continue_if_idle(self) -> None:
        if not self._enabled:
            return
        state_goal = await self._state_goal()
        goal = None if state_goal is None else _protocol_goal(state_goal)
        if goal is None or goal.status is not ThreadGoalStatus.ACTIVE:
            return
        collaboration_mode = getattr(self.session, "collaboration_mode", None)
        if getattr(collaboration_mode, "mode", collaboration_mode) is ModeKind.PLAN:
            return
        callback = getattr(self.session, "goal_continuation_callback", None)
        if not callable(callback):
            return
        from pycodex.core.goals import continuation_prompt, goal_context_input_item

        await _maybe_await(callback(goal_context_input_item(continuation_prompt(goal)), goal))

    async def usage_limit_active_goal_for_turn(self, turn_id: str) -> None:
        if not self._enabled or not self.accounting_state.turn_is_current_active_goal(turn_id):
            return
        await self.account_active_goal_progress(
            turn_id,
            f"{turn_id}:usage-limit-progress",
            GoalAccountingMode.ACTIVE_ONLY,
            BudgetLimitedGoalDisposition.CLEAR_ACTIVE,
        )
        limiter = getattr(self._thread_goals(), "usage_limit_active_thread_goal", None)
        if not callable(limiter):
            return
        state_goal = await _maybe_await(limiter(self._thread_id()))
        if state_goal is None:
            return
        self.accounting_state.clear_active_goal()
        await self._emit_goal_updated(
            f"{turn_id}:usage-limit",
            turn_id,
            _protocol_goal(state_goal),
        )

    async def account_active_goal_progress(
        self,
        turn_id: str | None = None,
        event_id: str | None = None,
        mode: GoalAccountingMode = GoalAccountingMode.ACTIVE_ONLY,
        disposition: BudgetLimitedGoalDisposition = BudgetLimitedGoalDisposition.KEEP_ACTIVE,
    ) -> AccountedGoalProgress | None:
        if not self._enabled:
            return None
        turn_id = turn_id or self.accounting_state.current_turn_id()
        if turn_id is None:
            return None
        snapshot = self.accounting_state.progress_snapshot(turn_id)
        if snapshot is None:
            return None
        outcome = await _maybe_await(
            self._thread_goals().account_thread_goal_usage(
                self._thread_id(),
                snapshot.time_delta_seconds,
                snapshot.token_delta,
                mode,
                snapshot.expected_goal_id,
            )
        )
        if not bool(getattr(outcome, "updated", False)):
            return None
        state_goal = outcome.goal
        self.accounting_state.mark_progress_accounted_for_status(
            turn_id,
            snapshot,
            state_goal.status,
            disposition,
        )
        goal = _protocol_goal(state_goal)
        await self._emit_goal_updated(event_id or f"{turn_id}:goal-progress", turn_id, goal)
        return AccountedGoalProgress(goal, state_goal.goal_id)

    async def account_idle_goal_progress(
        self,
        event_id: str,
        mode: GoalAccountingMode,
        disposition: BudgetLimitedGoalDisposition,
    ) -> AccountedGoalProgress | None:
        snapshot = self.accounting_state.idle_progress_snapshot()
        if snapshot is None:
            return None
        outcome = await _maybe_await(
            self._thread_goals().account_thread_goal_usage(
                self._thread_id(),
                snapshot.time_delta_seconds,
                0,
                mode,
                snapshot.expected_goal_id,
            )
        )
        if not bool(getattr(outcome, "updated", False)):
            self.accounting_state.reset_idle_progress_baseline_and_clear_active_goal()
            return None
        state_goal = outcome.goal
        self.accounting_state.mark_idle_progress_accounted_for_status(
            snapshot,
            state_goal.status,
            disposition,
        )
        goal = _protocol_goal(state_goal)
        await self._emit_goal_updated(event_id, None, goal)
        return AccountedGoalProgress(goal, state_goal.goal_id)

    async def finish_turn(self, turn_id: str, *, event_suffix: str) -> None:
        await self.account_active_goal_progress(
            turn_id,
            f"{turn_id}:{event_suffix}",
            GoalAccountingMode.ACTIVE_ONLY,
            BudgetLimitedGoalDisposition.CLEAR_ACTIVE,
        )
        self.accounting_state.finish_turn(turn_id)

    async def inject_budget_limit_steering(self, goal: Any) -> None:
        if getattr(goal, "status", None) is not ThreadGoalStatus.BUDGET_LIMITED:
            return
        await self._inject([budget_limit_steering_item(goal)])

    async def inject_objective_updated_steering(self, state_goal: Any) -> None:
        goal = _protocol_goal(state_goal)
        await self._inject([objective_updated_steering_item(goal)])

    async def _inject(self, items: list[Any]) -> None:
        injector = getattr(self.session, "inject_if_running", None)
        if callable(injector):
            await _maybe_await(injector(items))

    async def _emit_goal_updated(self, event_id: str, turn_id: str | None, goal: Any) -> None:
        await self.event_emitter.thread_goal_updated(event_id, turn_id, goal)

    async def _state_goal(self) -> Any:
        return await _maybe_await(self._thread_goals().get_thread_goal(self._thread_id()))

    def _thread_goals(self) -> Any:
        value = getattr(self.state_dbs, "thread_goals", None)
        return value() if callable(value) else value

    def _thread_id(self) -> Any:
        if self.thread_id is not None:
            return self.thread_id
        return getattr(self.session, "conversation_id", None) or self.session.thread_id


def _protocol_goal(goal: Any) -> Any:
    return protocol_goal_from_state(goal)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = ["AccountedGoalProgress", "GoalRuntimeHandle", "PreviousGoalSnapshot"]
