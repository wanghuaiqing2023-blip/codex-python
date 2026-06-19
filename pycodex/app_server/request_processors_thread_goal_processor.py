"""Thread goal request processor ported from ``app-server/src/request_processors/thread_goal_processor.rs``."""

from __future__ import annotations

import inspect
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.app_server.error_code import internal_error, invalid_request
from pycodex.app_server.thread_state import ThreadListenerCommand
from pycodex.app_server_protocol import (
    JSONRPCErrorError,
    ServerNotification,
    ThreadGoal,
    ThreadGoalClearParams,
    ThreadGoalClearResponse,
    ThreadGoalClearedNotification,
    ThreadGoalGetParams,
    ThreadGoalGetResponse,
    ThreadGoalSetParams,
    ThreadGoalSetResponse,
    ThreadGoalStatus,
    ThreadGoalUpdatedNotification,
)
from pycodex.protocol import validate_thread_goal_objective

JsonValue = Any


@dataclass
class ThreadGoalRequestProcessorError(Exception):
    error: JSONRPCErrorError

    def __post_init__(self) -> None:
        Exception.__init__(self, self.error.message)


@dataclass(frozen=True)
class ExternalGoalPreviousStatus:
    status: str

    @classmethod
    def new_goal(cls) -> "ExternalGoalPreviousStatus":
        return cls("NewGoal")

    @classmethod
    def from_goal(cls, goal: Any) -> "ExternalGoalPreviousStatus":
        return cls(str(_enum_value(_get(goal, "status"))))


@dataclass(frozen=True)
class ExternalGoalSet:
    goal: Any
    previous_status: ExternalGoalPreviousStatus


@dataclass
class ThreadGoalRequestProcessor:
    thread_manager: Any
    outgoing: Any
    config: Any
    thread_state_manager: Any
    state_db: Any | None = None
    rollout_locator: Callable[..., Any] | None = None
    rollout_reconciler: Callable[..., Any] | None = None

    @classmethod
    def new(
        cls,
        thread_manager: Any,
        outgoing: Any,
        config: Any,
        thread_state_manager: Any,
        state_db: Any | None = None,
    ) -> "ThreadGoalRequestProcessor":
        return cls(thread_manager, outgoing, config, thread_state_manager, state_db)

    async def thread_goal_set(
        self,
        request_id: Any,
        params: ThreadGoalSetParams | Mapping[str, JsonValue],
    ) -> None:
        parsed = params if isinstance(params, ThreadGoalSetParams) else ThreadGoalSetParams.from_mapping(params)
        await self.thread_goal_set_inner(request_id, parsed)

    async def thread_goal_get(
        self,
        params: ThreadGoalGetParams | Mapping[str, JsonValue],
    ) -> ThreadGoalGetResponse:
        parsed = params if isinstance(params, ThreadGoalGetParams) else ThreadGoalGetParams.from_mapping(params)
        return await self.thread_goal_get_inner(parsed)

    async def thread_goal_clear(
        self,
        request_id: Any,
        params: ThreadGoalClearParams | Mapping[str, JsonValue],
    ) -> None:
        parsed = params if isinstance(params, ThreadGoalClearParams) else ThreadGoalClearParams.from_mapping(params)
        await self.thread_goal_clear_inner(request_id, parsed)

    async def emit_resume_goal_snapshot_and_continue(self, thread_id: str, thread: Any) -> None:
        if not _goals_enabled(self.config):
            return
        await self.emit_thread_goal_snapshot(thread_id)
        try:
            await _maybe_await(_call_or_get(thread, "continue_active_goal_if_idle"))
        except Exception:
            return

    async def pending_resume_goal_state(self, thread: Any) -> tuple[bool, Any | None]:
        emit_thread_goal_update = _goals_enabled(self.config)
        if not emit_thread_goal_update:
            return False, None
        return True, _call_or_get(thread, "state_db") or self.state_db

    async def thread_goal_set_inner(self, request_id: Any, params: ThreadGoalSetParams) -> None:
        if not _goals_enabled(self.config):
            raise ThreadGoalRequestProcessorError(invalid_request("goals feature is disabled"))

        thread_id = parse_thread_id_for_request(params.thread_id)
        state_db = await self.state_db_for_materialized_thread(thread_id)
        running_thread = await _maybe_get_thread(self.thread_manager, thread_id)
        rollout_path = await self._rollout_path_for_thread(thread_id, running_thread)
        await self._reconcile_rollout(state_db, rollout_path)
        listener_command_tx = await self._listener_command_tx(thread_id)
        request_status = _get(params, "status")
        request_objective = _get(params, "objective")
        request_token_budget = _get(params, "token_budget")
        status = thread_goal_status_to_state(request_status) if request_status is not None else None
        objective = request_objective.strip() if request_objective is not None else None

        if objective is not None:
            try:
                validate_thread_goal_objective(objective)
            except Exception as exc:
                raise ThreadGoalRequestProcessorError(invalid_request(str(exc))) from exc
        token_budget_value = _flatten_optional(request_token_budget)
        if objective is not None or request_token_budget is not None:
            try:
                validate_goal_budget(token_budget_value)
            except Exception as exc:
                raise ThreadGoalRequestProcessorError(invalid_request(str(exc))) from exc

        if running_thread is not None:
            await _maybe_await(_call_or_get(running_thread, "prepare_external_goal_mutation"))

        goals = _thread_goals(state_db)
        if objective is not None:
            existing_goal = await _maybe_await(goals.get_thread_goal(thread_id))
            if existing_goal is not None:
                previous_status = ExternalGoalPreviousStatus.from_goal(existing_goal)
                goal = await _maybe_await(
                    goals.update_thread_goal(
                        thread_id,
                        {
                            "objective": objective,
                            "status": status,
                            "token_budget": request_token_budget,
                            "expected_goal_id": _get(existing_goal, "goal_id"),
                        },
                    )
                )
                if goal is None:
                    raise ThreadGoalRequestProcessorError(
                        invalid_request(f"cannot update goal for thread {thread_id}: no goal exists")
                    )
            else:
                previous_status = ExternalGoalPreviousStatus.new_goal()
                goal = await _maybe_await(
                    goals.replace_thread_goal(
                        thread_id,
                        objective,
                        status or "active",
                        token_budget_value,
                    )
                )
        else:
            existing_goal = await _maybe_await(goals.get_thread_goal(thread_id))
            if existing_goal is None:
                raise ThreadGoalRequestProcessorError(
                    invalid_request(f"cannot update goal for thread {thread_id}: no goal exists")
                )
            previous_status = ExternalGoalPreviousStatus.from_goal(existing_goal)
            goal = await _maybe_await(
                goals.update_thread_goal(
                    thread_id,
                    {
                        "objective": None,
                        "status": status,
                        "token_budget": request_token_budget,
                        "expected_goal_id": None,
                    },
                )
            )
            if goal is None:
                raise ThreadGoalRequestProcessorError(
                    invalid_request(f"cannot update goal for thread {thread_id}: no goal exists")
                )

        if objective is not None:
            await _maybe_await(_call_or_get(state_db, "set_thread_preview_if_empty", thread_id, _get(goal, "objective")))

        external_goal_set = ExternalGoalSet(goal=goal, previous_status=previous_status)
        api_goal = api_thread_goal_from_state(goal)
        await _send_response(self.outgoing, request_id, ThreadGoalSetResponse(goal=api_goal))
        await self.emit_thread_goal_updated_ordered(thread_id, api_goal, listener_command_tx)
        if running_thread is not None:
            await _maybe_await(_call_or_get(running_thread, "apply_external_goal_set", external_goal_set))

    async def thread_goal_get_inner(self, params: ThreadGoalGetParams) -> ThreadGoalGetResponse:
        if not _goals_enabled(self.config):
            raise ThreadGoalRequestProcessorError(invalid_request("goals feature is disabled"))
        thread_id = parse_thread_id_for_request(params.thread_id)
        state_db = await self.state_db_for_materialized_thread(thread_id)
        try:
            goal = await _maybe_await(_thread_goals(state_db).get_thread_goal(thread_id))
        except Exception as exc:
            raise ThreadGoalRequestProcessorError(internal_error(f"failed to read thread goal: {exc}")) from exc
        return ThreadGoalGetResponse(goal=api_thread_goal_from_state(goal) if goal is not None else None)

    async def thread_goal_clear_inner(self, request_id: Any, params: ThreadGoalClearParams) -> None:
        if not _goals_enabled(self.config):
            raise ThreadGoalRequestProcessorError(invalid_request("goals feature is disabled"))
        thread_id = parse_thread_id_for_request(params.thread_id)
        state_db = await self.state_db_for_materialized_thread(thread_id)
        running_thread = await _maybe_get_thread(self.thread_manager, thread_id)
        rollout_path = await self._rollout_path_for_thread(thread_id, running_thread)
        await self._reconcile_rollout(state_db, rollout_path)
        if running_thread is not None:
            await _maybe_await(_call_or_get(running_thread, "prepare_external_goal_mutation"))
        listener_command_tx = await self._listener_command_tx(thread_id)
        try:
            cleared = bool(await _maybe_await(_thread_goals(state_db).delete_thread_goal(thread_id)))
        except Exception as exc:
            raise ThreadGoalRequestProcessorError(internal_error(f"failed to clear thread goal: {exc}")) from exc
        if cleared and running_thread is not None:
            await _maybe_await(_call_or_get(running_thread, "apply_external_goal_clear"))
        await _send_response(self.outgoing, request_id, ThreadGoalClearResponse(cleared=cleared))
        if cleared:
            await self.emit_thread_goal_cleared_ordered(thread_id, listener_command_tx)

    async def state_db_for_materialized_thread(self, thread_id: str) -> Any:
        thread = await _maybe_get_thread(self.thread_manager, thread_id)
        if thread is not None:
            if _call_or_get(thread, "rollout_path") is None:
                raise ThreadGoalRequestProcessorError(invalid_request(f"ephemeral thread does not support goals: {thread_id}"))
            thread_state_db = _call_or_get(thread, "state_db")
            if thread_state_db is not None:
                return thread_state_db
        else:
            found = await self._find_thread_path(thread_id)
            if found is None:
                raise ThreadGoalRequestProcessorError(invalid_request(f"thread not found: {thread_id}"))
        if self.state_db is None:
            raise ThreadGoalRequestProcessorError(internal_error("sqlite state db unavailable for thread goals"))
        return self.state_db

    async def emit_thread_goal_snapshot(self, thread_id: str) -> None:
        try:
            state_db = await self.state_db_for_materialized_thread(thread_id)
        except ThreadGoalRequestProcessorError:
            return
        listener_command_tx = await self._listener_command_tx(thread_id)
        if listener_command_tx is not None:
            if _send_listener_command(listener_command_tx, ThreadListenerCommand.emit_thread_goal_snapshot(state_db)):
                return
        await send_thread_goal_snapshot_notification(self.outgoing, thread_id, state_db)

    async def emit_thread_goal_updated_ordered(self, thread_id: str, goal: ThreadGoal, listener_command_tx: Any | None) -> None:
        if listener_command_tx is not None:
            if _send_listener_command(listener_command_tx, ThreadListenerCommand.emit_thread_goal_updated(goal)):
                return
        await _send_server_notification(
            self.outgoing,
            ServerNotification(
                "ThreadGoalUpdated",
                ThreadGoalUpdatedNotification(thread_id=thread_id, turn_id=None, goal=goal),
            ),
        )

    async def emit_thread_goal_cleared_ordered(self, thread_id: str, listener_command_tx: Any | None) -> None:
        if listener_command_tx is not None:
            if _send_listener_command(listener_command_tx, ThreadListenerCommand.emit_thread_goal_cleared()):
                return
        await _send_server_notification(
            self.outgoing,
            ServerNotification("ThreadGoalCleared", ThreadGoalClearedNotification(thread_id=thread_id)),
        )

    async def _listener_command_tx(self, thread_id: str) -> Any | None:
        manager = self.thread_state_manager
        if manager is None:
            return None
        state = await _maybe_await(_call_or_get(manager, "thread_state", thread_id))
        if hasattr(state, "lock"):
            locked = state.lock()
            if inspect.isawaitable(locked):
                state = await locked
        return _call_or_get(state, "listener_command_tx")

    async def _rollout_path_for_thread(self, thread_id: str, running_thread: Any | None) -> Any:
        if running_thread is not None:
            rollout_path = _call_or_get(running_thread, "rollout_path")
            if rollout_path is None:
                raise ThreadGoalRequestProcessorError(invalid_request(f"ephemeral thread does not support goals: {thread_id}"))
            return rollout_path
        rollout_path = await self._find_thread_path(thread_id)
        if rollout_path is None:
            raise ThreadGoalRequestProcessorError(invalid_request(f"thread not found: {thread_id}"))
        return rollout_path

    async def _find_thread_path(self, thread_id: str) -> Any:
        if self.rollout_locator is not None:
            try:
                return await _maybe_await(self.rollout_locator(_get(self.config, "codex_home"), thread_id, self.state_db))
            except Exception as exc:
                raise ThreadGoalRequestProcessorError(internal_error(f"failed to locate thread id {thread_id}: {exc}")) from exc
        finder = _callable(self.state_db, "find_thread_path_by_id_str")
        if finder is None:
            return None
        try:
            return await _maybe_await(finder(thread_id))
        except Exception as exc:
            raise ThreadGoalRequestProcessorError(internal_error(f"failed to locate thread id {thread_id}: {exc}")) from exc

    async def _reconcile_rollout(self, state_db: Any, rollout_path: Any) -> None:
        if self.rollout_reconciler is not None:
            await _maybe_await(self.rollout_reconciler(state_db, rollout_path, _get(self.config, "model_provider_id")))


def validate_goal_budget(value: int | None) -> None:
    if value is not None and value <= 0:
        raise ValueError("goal budgets must be positive when provided")


def thread_goal_status_to_state(status: ThreadGoalStatus | str) -> str:
    return _state_status(ThreadGoalStatus.parse(status))


def thread_goal_status_from_state(status: Any) -> ThreadGoalStatus:
    raw = _enum_value(status)
    mapping = {
        "active": ThreadGoalStatus.ACTIVE,
        "paused": ThreadGoalStatus.PAUSED,
        "blocked": ThreadGoalStatus.BLOCKED,
        "usage_limited": ThreadGoalStatus.USAGE_LIMITED,
        "usageLimited": ThreadGoalStatus.USAGE_LIMITED,
        "budget_limited": ThreadGoalStatus.BUDGET_LIMITED,
        "budgetLimited": ThreadGoalStatus.BUDGET_LIMITED,
        "complete": ThreadGoalStatus.COMPLETE,
    }
    return mapping[str(raw)]


def api_thread_goal_from_state(goal: Any) -> ThreadGoal:
    return ThreadGoal(
        thread_id=str(_get(goal, "thread_id")),
        objective=str(_get(goal, "objective")),
        status=thread_goal_status_from_state(_get(goal, "status")),
        token_budget=_get(goal, "token_budget"),
        tokens_used=int(_get(goal, "tokens_used", 0)),
        time_used_seconds=int(_get(goal, "time_used_seconds", 0)),
        created_at=_timestamp(_get(goal, "created_at")),
        updated_at=_timestamp(_get(goal, "updated_at")),
    )


def parse_thread_id_for_request(thread_id: str) -> str:
    try:
        return str(uuid.UUID(str(thread_id)))
    except Exception as exc:
        raise ThreadGoalRequestProcessorError(invalid_request(f"invalid thread id: {exc}")) from exc


async def send_thread_goal_snapshot_notification(outgoing: Any, thread_id: str, state_db: Any) -> None:
    goal = await _maybe_await(_thread_goals(state_db).get_thread_goal(thread_id))
    if goal is not None:
        await _send_server_notification(
            outgoing,
            ServerNotification(
                "ThreadGoalUpdated",
                ThreadGoalUpdatedNotification(thread_id=thread_id, turn_id=None, goal=api_thread_goal_from_state(goal)),
            ),
        )
    else:
        await _send_server_notification(
            outgoing,
            ServerNotification("ThreadGoalCleared", ThreadGoalClearedNotification(thread_id=thread_id)),
        )


def _state_status(status: ThreadGoalStatus) -> str:
    return {
        ThreadGoalStatus.ACTIVE: "active",
        ThreadGoalStatus.PAUSED: "paused",
        ThreadGoalStatus.BLOCKED: "blocked",
        ThreadGoalStatus.USAGE_LIMITED: "usage_limited",
        ThreadGoalStatus.BUDGET_LIMITED: "budget_limited",
        ThreadGoalStatus.COMPLETE: "complete",
    }[status]


def _goals_enabled(config: Any) -> bool:
    features = _get(config, "features")
    checker = _callable(features, "enabled")
    if checker is not None:
        return bool(checker("Goals"))
    return bool(_get(config, "goals_enabled", True))


def _thread_goals(state_db: Any) -> Any:
    return _call_or_get(state_db, "thread_goals")


def _flatten_optional(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _send_listener_command(sink: Any, command: ThreadListenerCommand) -> bool:
    sender = _callable(sink, "send")
    if sender is not None:
        return bool(sender(command))
    commands = _get(sink, "commands")
    if isinstance(commands, list):
        commands.append(command)
        return True
    return False


async def _send_response(outgoing: Any, request_id: Any, response: Any) -> None:
    sender = _callable(outgoing, "send_response")
    if sender is not None:
        await _maybe_await(sender(request_id, response))


async def _send_server_notification(outgoing: Any, notification: ServerNotification) -> None:
    sender = _callable(outgoing, "send_server_notification")
    if sender is not None:
        await _maybe_await(sender(notification))


async def _maybe_get_thread(thread_manager: Any, thread_id: str) -> Any | None:
    getter = _callable(thread_manager, "get_thread")
    if getter is None:
        return None
    try:
        return await _maybe_await(getter(thread_id))
    except Exception:
        return None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _callable(obj: Any, name: str) -> Callable[..., Any] | None:
    candidate = getattr(obj, name, None)
    return candidate if callable(candidate) else None


def _call_or_get(obj: Any, name: str, *args: Any) -> Any:
    value = _get(obj, name)
    if callable(value):
        return value(*args)
    return value


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _timestamp(value: Any) -> int:
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return int(timestamp())
    return int(value)


__all__ = [
    "ExternalGoalPreviousStatus",
    "ExternalGoalSet",
    "ThreadGoalRequestProcessor",
    "ThreadGoalRequestProcessorError",
    "api_thread_goal_from_state",
    "parse_thread_id_for_request",
    "send_thread_goal_snapshot_notification",
    "thread_goal_status_from_state",
    "thread_goal_status_to_state",
    "validate_goal_budget",
]
