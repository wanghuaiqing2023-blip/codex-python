from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace

from pycodex.app_server.error_code import INTERNAL_ERROR_CODE, INVALID_REQUEST_ERROR_CODE
from pycodex.app_server.request_processors_thread_goal_processor import (
    ThreadGoalRequestProcessor,
    ThreadGoalRequestProcessorError,
    api_thread_goal_from_state,
    parse_thread_id_for_request,
    send_thread_goal_snapshot_notification,
    thread_goal_status_from_state,
    thread_goal_status_to_state,
    validate_goal_budget,
)
from pycodex.app_server.thread_state import ListenerCommandSink
from pycodex.app_server_protocol import ThreadGoalStatus

THREAD_ID = "11111111-1111-4111-8111-111111111111"
_MISSING = object()


def _run(coro):
    return asyncio.run(coro)


def test_validate_goal_budget_rejects_non_positive_values() -> None:
    # Rust source: validate_goal_budget.
    validate_goal_budget(None)
    validate_goal_budget(1)
    for value in (0, -1):
        try:
            validate_goal_budget(value)
        except ValueError as exc:
            assert str(exc) == "goal budgets must be positive when provided"
        else:
            raise AssertionError("expected ValueError")


def test_thread_goal_status_roundtrips_state_values() -> None:
    # Rust source: thread_goal_status_to_state/thread_goal_status_from_state.
    assert thread_goal_status_to_state(ThreadGoalStatus.ACTIVE) == "active"
    assert thread_goal_status_to_state(ThreadGoalStatus.PAUSED) == "paused"
    assert thread_goal_status_to_state(ThreadGoalStatus.BLOCKED) == "blocked"
    assert thread_goal_status_to_state(ThreadGoalStatus.USAGE_LIMITED) == "usage_limited"
    assert thread_goal_status_to_state(ThreadGoalStatus.BUDGET_LIMITED) == "budget_limited"
    assert thread_goal_status_to_state(ThreadGoalStatus.COMPLETE) == "complete"
    assert thread_goal_status_from_state("budget_limited") is ThreadGoalStatus.BUDGET_LIMITED
    assert thread_goal_status_from_state("usageLimited") is ThreadGoalStatus.USAGE_LIMITED


def test_api_thread_goal_from_state_projects_protocol_goal_fields() -> None:
    goal = _goal(status="usage_limited", token_budget=500)

    api_goal = api_thread_goal_from_state(goal)

    assert api_goal.thread_id == THREAD_ID
    assert api_goal.objective == "Ship parity"
    assert api_goal.status is ThreadGoalStatus.USAGE_LIMITED
    assert api_goal.token_budget == 500
    assert api_goal.tokens_used == 42
    assert api_goal.time_used_seconds == 9
    assert api_goal.created_at == 1_700_000_000
    assert api_goal.updated_at == 1_700_000_030


def test_parse_thread_id_for_request_maps_invalid_request() -> None:
    try:
        parse_thread_id_for_request("not-a-uuid")
    except ThreadGoalRequestProcessorError as exc:
        assert exc.error.code == INVALID_REQUEST_ERROR_CODE
        assert exc.error.message.startswith("invalid thread id:")
    else:
        raise AssertionError("expected ThreadGoalRequestProcessorError")


def test_thread_goal_get_feature_gate_and_success_response() -> None:
    _run(_thread_goal_get_feature_gate_and_success_response())


async def _thread_goal_get_feature_gate_and_success_response() -> None:
    processor = _processor(goals_enabled=False)
    try:
        await processor.thread_goal_get({"threadId": THREAD_ID})
    except ThreadGoalRequestProcessorError as exc:
        assert exc.error.code == INVALID_REQUEST_ERROR_CODE
        assert exc.error.message == "goals feature is disabled"
    else:
        raise AssertionError("expected disabled feature error")

    processor = _processor(goal=_goal())
    response = await processor.thread_goal_get({"threadId": THREAD_ID})
    assert response.goal.objective == "Ship parity"


def test_thread_goal_set_creates_goal_sends_response_and_listener_update() -> None:
    _run(_thread_goal_set_creates_goal_sends_response_and_listener_update())


async def _thread_goal_set_creates_goal_sends_response_and_listener_update() -> None:
    sink = ListenerCommandSink()
    state_db = FakeStateDb(goal=None)
    processor = _processor(state_db=state_db, listener_sink=sink, rollout_path="rollout.jsonl")

    await processor.thread_goal_set(
        "request-1",
        {"threadId": THREAD_ID, "objective": "  New goal  ", "status": "paused", "tokenBudget": 25},
    )

    assert state_db.goals.replaced == [(THREAD_ID, "New goal", "paused", 25)]
    assert state_db.preview_updates == [(THREAD_ID, "New goal")]
    assert processor.outgoing.responses[0][0] == "request-1"
    assert processor.outgoing.responses[0][1].goal.objective == "New goal"
    assert processor.outgoing.notifications == []
    assert [command.kind for command in sink.commands] == ["EmitThreadGoalUpdated"]


def test_thread_goal_set_status_only_requires_existing_goal() -> None:
    _run(_thread_goal_set_status_only_requires_existing_goal())


async def _thread_goal_set_status_only_requires_existing_goal() -> None:
    processor = _processor(goal=None, rollout_path="rollout.jsonl")

    try:
        await processor.thread_goal_set("request-2", {"threadId": THREAD_ID, "status": "complete"})
    except ThreadGoalRequestProcessorError as exc:
        assert exc.error.code == INVALID_REQUEST_ERROR_CODE
        assert exc.error.message == f"cannot update goal for thread {THREAD_ID}: no goal exists"
    else:
        raise AssertionError("expected missing goal error")


def test_thread_goal_clear_sends_response_and_fallback_notification() -> None:
    _run(_thread_goal_clear_sends_response_and_fallback_notification())


async def _thread_goal_clear_sends_response_and_fallback_notification() -> None:
    processor = _processor(goal=_goal(), listener_sink=None, rollout_path="rollout.jsonl")

    await processor.thread_goal_clear("request-3", {"threadId": THREAD_ID})

    assert processor.outgoing.responses[0][1].cleared is True
    assert [notification.type for notification in processor.outgoing.notifications] == ["ThreadGoalCleared"]


def test_state_db_for_materialized_thread_reports_ephemeral_and_missing_state_db() -> None:
    _run(_state_db_for_materialized_thread_reports_ephemeral_and_missing_state_db())


async def _state_db_for_materialized_thread_reports_ephemeral_and_missing_state_db() -> None:
    running = FakeRunningThread(rollout_path=None, state_db=FakeStateDb())
    processor = _processor(running_thread=running, state_db=FakeStateDb())
    try:
        await processor.state_db_for_materialized_thread(THREAD_ID)
    except ThreadGoalRequestProcessorError as exc:
        assert exc.error.code == INVALID_REQUEST_ERROR_CODE
        assert exc.error.message == f"ephemeral thread does not support goals: {THREAD_ID}"
    else:
        raise AssertionError("expected ephemeral error")

    materialized_without_state_db = FakeRunningThread(rollout_path="rollout.jsonl", state_db=None)
    processor = _processor(running_thread=materialized_without_state_db, state_db=None)
    try:
        await processor.state_db_for_materialized_thread(THREAD_ID)
    except ThreadGoalRequestProcessorError as exc:
        assert exc.error.code == INTERNAL_ERROR_CODE
        assert exc.error.message == "sqlite state db unavailable for thread goals"
    else:
        raise AssertionError("expected missing state db error")


def test_send_thread_goal_snapshot_notification_updates_or_clears() -> None:
    _run(_send_thread_goal_snapshot_notification_updates_or_clears())


async def _send_thread_goal_snapshot_notification_updates_or_clears() -> None:
    outgoing = FakeOutgoing()
    await send_thread_goal_snapshot_notification(outgoing, THREAD_ID, FakeStateDb(goal=_goal()))
    assert outgoing.notifications[0].type == "ThreadGoalUpdated"

    outgoing = FakeOutgoing()
    await send_thread_goal_snapshot_notification(outgoing, THREAD_ID, FakeStateDb(goal=None))
    assert outgoing.notifications[0].type == "ThreadGoalCleared"


@dataclass
class FakeGoal:
    thread_id: str = THREAD_ID
    objective: str = "Ship parity"
    status: str = "active"
    token_budget: int | None = None
    tokens_used: int = 42
    time_used_seconds: int = 9
    created_at: datetime = datetime.fromtimestamp(1_700_000_000, timezone.utc)
    updated_at: datetime = datetime.fromtimestamp(1_700_000_030, timezone.utc)
    goal_id: str = "goal-1"


def _goal(**overrides) -> FakeGoal:
    data = FakeGoal().__dict__ | overrides
    return FakeGoal(**data)


class FakeGoalStore:
    def __init__(self, goal=None) -> None:
        self.goal = goal
        self.replaced = []
        self.updated = []
        self.deleted = []

    async def get_thread_goal(self, thread_id):
        return self.goal

    async def replace_thread_goal(self, thread_id, objective, status, token_budget):
        self.replaced.append((thread_id, objective, status, token_budget))
        self.goal = _goal(thread_id=thread_id, objective=objective, status=status, token_budget=token_budget)
        return self.goal

    async def update_thread_goal(self, thread_id, update):
        self.updated.append((thread_id, update))
        if self.goal is None:
            return None
        if update.get("objective") is not None:
            self.goal.objective = update["objective"]
        if update.get("status") is not None:
            self.goal.status = update["status"]
        if "token_budget" in update and update["token_budget"] is not None:
            self.goal.token_budget = update["token_budget"]
        return self.goal

    async def delete_thread_goal(self, thread_id):
        self.deleted.append(thread_id)
        existed = self.goal is not None
        self.goal = None
        return existed


class FakeStateDb:
    def __init__(self, goal=_MISSING, path="rollout.jsonl") -> None:
        initial_goal = _goal() if goal is _MISSING else goal
        self.goals = FakeGoalStore(initial_goal)
        self.path = path
        self.preview_updates = []

    def thread_goals(self):
        return self.goals

    async def find_thread_path_by_id_str(self, _thread_id):
        return self.path

    async def set_thread_preview_if_empty(self, thread_id, preview):
        self.preview_updates.append((thread_id, preview))


class FakeOutgoing:
    def __init__(self) -> None:
        self.responses = []
        self.notifications = []

    async def send_response(self, request_id, response):
        self.responses.append((request_id, response))

    async def send_server_notification(self, notification):
        self.notifications.append(notification)


class FakeThreadManager:
    def __init__(self, thread=None) -> None:
        self.thread = thread

    async def get_thread(self, _thread_id):
        if self.thread is None:
            raise KeyError("missing")
        return self.thread


class FakeRunningThread:
    def __init__(self, rollout_path="rollout.jsonl", state_db=None) -> None:
        self._rollout_path = rollout_path
        self._state_db = state_db
        self.applied_sets = []
        self.clears = 0

    def rollout_path(self):
        return self._rollout_path

    def state_db(self):
        return self._state_db

    async def prepare_external_goal_mutation(self):
        pass

    async def apply_external_goal_set(self, external_goal_set):
        self.applied_sets.append(external_goal_set)

    async def apply_external_goal_clear(self):
        self.clears += 1


class FakeThreadStateManager:
    def __init__(self, sink=None) -> None:
        self.state = SimpleNamespace(listener_command_tx=sink)

    async def thread_state(self, _thread_id):
        return self.state


def _processor(**overrides):
    state_db = overrides.get(
        "state_db",
        FakeStateDb(goal=overrides.get("goal", _MISSING), path=overrides.get("rollout_path", "rollout.jsonl")),
    )
    processor = ThreadGoalRequestProcessor(
        thread_manager=FakeThreadManager(overrides.get("running_thread")),
        outgoing=FakeOutgoing(),
        config=SimpleNamespace(
            goals_enabled=overrides.get("goals_enabled", True),
            codex_home="codex-home",
            model_provider_id="mock_provider",
        ),
        thread_state_manager=FakeThreadStateManager(overrides.get("listener_sink")),
        state_db=state_db,
    )
    return processor
