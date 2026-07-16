"""Goal extension registration aligned with ``codex-goal-extension::extension``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pycodex.core.tools.handlers.goal import UPDATE_GOAL_TOOL_NAME
from pycodex.extension_api import ExtensionData, ExtensionRegistryBuilder
from pycodex.protocol import ModeKind, ThreadGoalStatus
from pycodex.state import GoalAccountingMode, ThreadGoalStatus as StateGoalStatus

from .accounting import BudgetLimitedGoalDisposition
from .events import GoalEventEmitter
from .runtime import GoalRuntimeHandle
from .tool import GoalToolExecutor


@dataclass(frozen=True)
class GoalExtensionConfig:
    enabled: bool


class GoalExtension:
    def __init__(
        self,
        state_dbs: Any,
        event_emitter: GoalEventEmitter,
        goals_enabled: Callable[[Any], bool],
        host_session: Any = None,
    ) -> None:
        self.state_dbs = state_dbs
        self.event_emitter = event_emitter
        self.goals_enabled = goals_enabled
        self.host_session = host_session

    async def on_thread_start(self, input: Any) -> None:
        enabled = bool(self.goals_enabled(input.config))
        input.thread_store.insert(GoalExtensionConfig(enabled))
        runtime = input.thread_store.get_or_init(
            GoalRuntimeHandle,
            lambda: GoalRuntimeHandle(
                self.host_session,
                self.state_dbs,
                thread_id=input.thread_store.level_id(),
                event_emitter=self.event_emitter,
                enabled=enabled,
            ),
        )
        runtime.set_enabled(enabled)

    async def on_thread_resume(self, input: Any) -> None:
        runtime = _goal_runtime_handle(input.thread_store)
        if runtime is not None:
            await runtime.restore_after_resume()

    def on_config_changed(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        previous_config: Any,
        new_config: Any,
    ) -> None:
        del session_store, previous_config
        enabled = bool(self.goals_enabled(new_config))
        thread_store.insert(GoalExtensionConfig(enabled))
        runtime = _goal_runtime_handle(thread_store)
        if runtime is not None:
            runtime.set_enabled(enabled)

    async def on_turn_start(self, input: Any) -> None:
        runtime = _goal_runtime_handle(input.thread_store)
        if runtime is None or not runtime.is_enabled():
            return
        mode = getattr(input.collaboration_mode, "mode", input.collaboration_mode)
        if not isinstance(mode, ModeKind):
            mode = ModeKind.DEFAULT
        accounting = runtime.accounting_state
        accounting.start_turn(input.turn_id, mode, input.token_usage_at_turn_start)
        if mode is ModeKind.PLAN:
            accounting.clear_current_turn_goal()
            return
        goal = await runtime._state_goal()
        if goal is not None and goal.status in {StateGoalStatus.ACTIVE, StateGoalStatus.BUDGET_LIMITED}:
            accounting.mark_turn_goal_active(input.turn_id, goal.goal_id)

    async def on_turn_stop(self, input: Any) -> None:
        await self._finish_turn(input.thread_store, input.turn_store.level_id(), "turn-stop")

    async def on_turn_abort(self, input: Any) -> None:
        await self._finish_turn(input.thread_store, input.turn_store.level_id(), "turn-abort")

    async def _finish_turn(self, thread_store: ExtensionData, turn_id: str, suffix: str) -> None:
        runtime = _goal_runtime_handle(thread_store)
        if runtime is None or not runtime.is_enabled():
            return
        await runtime.finish_turn(turn_id, event_suffix=suffix)

    async def on_token_usage(
        self,
        session_store: ExtensionData,
        thread_store: ExtensionData,
        turn_store: ExtensionData,
        token_usage: Any,
    ) -> None:
        del session_store
        runtime = _goal_runtime_handle(thread_store)
        if runtime is None or not runtime.is_enabled():
            return
        total = getattr(token_usage, "total_token_usage", token_usage)
        runtime.accounting_state.record_token_usage(turn_store.level_id(), total)

    async def on_tool_finish(self, input: Any) -> None:
        runtime = _goal_runtime_handle(input.thread_store)
        if runtime is None or not runtime.is_enabled():
            return
        if not _tool_attempt_counts_for_goal_progress(input.outcome):
            return
        if getattr(input.tool_name, "namespace", None) is None and input.tool_name.name == UPDATE_GOAL_TOOL_NAME:
            return
        progress = await runtime.account_active_goal_progress(
            input.turn_id,
            input.call_id,
            GoalAccountingMode.ACTIVE_ONLY,
            BudgetLimitedGoalDisposition.KEEP_ACTIVE,
        )
        if progress is None or progress.goal.status is not ThreadGoalStatus.BUDGET_LIMITED:
            return
        if not runtime.accounting_state.mark_budget_limit_reported_if_new(progress.goal_id):
            return
        await runtime.inject_budget_limit_steering(progress.goal)

    def tools(self, session_store: ExtensionData, thread_store: ExtensionData) -> list[Any]:
        del session_store
        runtime = _goal_runtime_handle(thread_store)
        if runtime is None or not runtime.is_enabled():
            return []
        args = (
            runtime.thread_id,
            self.state_dbs,
            runtime.accounting_state,
            self.event_emitter,
        )
        return [
            GoalToolExecutor.get(*args),
            GoalToolExecutor.create(*args),
            GoalToolExecutor.update(*args),
        ]


def install_with_backend(
    registry: ExtensionRegistryBuilder,
    state_dbs: Any,
    goals_enabled: Callable[[Any], bool],
    **_host_capabilities: Any,
) -> GoalExtension:
    extension = GoalExtension(
        state_dbs,
        GoalEventEmitter(registry.event_sink()),
        goals_enabled,
        host_session=_host_capabilities.get("host_session"),
    )
    registry.thread_lifecycle_contributor(extension)
    registry.config_contributor(extension)
    registry.turn_lifecycle_contributor(extension)
    registry.token_usage_contributor(extension)
    registry.tool_lifecycle_contributor(extension)
    registry.tool_contributor(extension)
    return extension


def _goal_runtime_handle(thread_store: Any) -> GoalRuntimeHandle | None:
    if not isinstance(thread_store, ExtensionData):
        return None
    return thread_store.get(GoalRuntimeHandle)


def _tool_attempt_counts_for_goal_progress(outcome: Any) -> bool:
    outcome_type = getattr(outcome, "type", None)
    if outcome_type == "completed":
        return True
    return outcome_type == "failed" and getattr(outcome, "handler_executed", None) is True


__all__ = ["GoalExtension", "GoalExtensionConfig", "install_with_backend"]
