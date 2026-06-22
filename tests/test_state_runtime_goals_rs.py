import asyncio
import sqlite3
from pathlib import Path

from pycodex.protocol import ThreadId
from pycodex.state.model.thread_goal import ThreadGoalStatus
from pycodex.state.runtime.goals import (
    GoalAccountingMode,
    GoalStore,
    GoalUpdate,
    TOKEN_BUDGET_UNCHANGED,
)


THREAD_ID = ThreadId.from_string("00000000-0000-0000-0000-000000000123")


def _run(coro):
    return asyncio.run(coro)


def _init_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
CREATE TABLE thread_goals (
    thread_id TEXT PRIMARY KEY NOT NULL,
    goal_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'active',
        'paused',
        'blocked',
        'usage_limited',
        'budget_limited',
        'complete'
    )),
    token_budget INTEGER,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    time_used_seconds INTEGER NOT NULL DEFAULT 0,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);
        """
    )


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    _init_schema(connection)
    return connection


def test_replace_update_and_get_thread_goal() -> None:
    # Rust crate: codex-state
    # Rust module/test: src/runtime/goals.rs::replace_update_and_get_thread_goal
    # Behavior contract: replace creates a goal, update mutates selected
    # fields, get returns the row-converted goal, and delete removes it.
    store = GoalStore(_connection())

    goal = _run(
        store.replace_thread_goal(
            THREAD_ID,
            "ship it",
            ThreadGoalStatus.ACTIVE,
            100,
            now_ms=1_700_000_000_000,
            goal_id="goal-1",
        )
    )
    updated = _run(
        store.update_thread_goal(
            THREAD_ID,
            GoalUpdate(objective="ship it well", status=ThreadGoalStatus.PAUSED, token_budget=200, expected_goal_id="goal-1"),
            now_ms=1_700_000_001_000,
        )
    )

    assert goal.goal_id == "goal-1"
    assert goal.status is ThreadGoalStatus.ACTIVE
    assert updated is not None
    assert updated.objective == "ship it well"
    assert updated.status is ThreadGoalStatus.PAUSED
    assert updated.token_budget == 200
    assert updated.tokens_used == 0
    assert updated.created_at == goal.created_at
    assert updated.updated_at > goal.updated_at
    assert _run(store.get_thread_goal(THREAD_ID)) == updated
    assert _run(store.delete_thread_goal(THREAD_ID)) is True
    assert _run(store.get_thread_goal(THREAD_ID)) is None


def test_insert_thread_goal_does_not_replace_existing_goal() -> None:
    # Rust crate: codex-state
    # Rust module/test: src/runtime/goals.rs::insert_thread_goal_does_not_replace_existing_goal
    # Behavior contract: insert is insert-or-ignore and returns None when a
    # thread already has a goal.
    store = GoalStore(_connection())

    first = _run(store.insert_thread_goal(THREAD_ID, "first", ThreadGoalStatus.ACTIVE, None, now_ms=100, goal_id="goal-1"))
    second = _run(store.insert_thread_goal(THREAD_ID, "second", ThreadGoalStatus.ACTIVE, None, now_ms=200, goal_id="goal-2"))

    assert first is not None
    assert first.goal_id == "goal-1"
    assert second is None
    assert _run(store.get_thread_goal(THREAD_ID)).objective == "first"


def test_update_and_accounting_ignore_replaced_goal_version() -> None:
    # Rust crate: codex-state
    # Rust module/tests:
    # src/runtime/goals.rs::update_thread_goal_ignores_replaced_goal_version
    # src/runtime/goals.rs::usage_accounting_ignores_replaced_goal_version
    # Behavior contract: expected_goal_id is an optimistic concurrency guard
    # for both updates and usage accounting.
    store = GoalStore(_connection())
    _run(store.replace_thread_goal(THREAD_ID, "current", ThreadGoalStatus.ACTIVE, 100, now_ms=100, goal_id="current-goal"))

    stale_update = _run(store.update_thread_goal(THREAD_ID, GoalUpdate(objective="stale", expected_goal_id="old-goal"), now_ms=200))
    stale_accounting = _run(
        store.account_thread_goal_usage(
            THREAD_ID,
            time_delta_seconds=10,
            token_delta=20,
            mode=GoalAccountingMode.ACTIVE_ONLY,
            expected_goal_id="old-goal",
            now_ms=300,
        )
    )

    goal = _run(store.get_thread_goal(THREAD_ID))
    assert stale_update is None
    assert stale_accounting.updated is False
    assert stale_accounting.goal == goal
    assert goal.objective == "current"
    assert goal.tokens_used == 0


def test_active_status_filters_do_not_clobber_terminal_status() -> None:
    # Rust crate: codex-state
    # Rust module/tests: pause/usage-limit active thread goal status filters
    # Behavior contract: pausing applies only to active goals, while usage
    # limit applies to active or budget-limited goals.
    store = GoalStore(_connection())
    _run(store.replace_thread_goal(THREAD_ID, "done", ThreadGoalStatus.COMPLETE, None, now_ms=100, goal_id="goal-1"))
    assert _run(store.pause_active_thread_goal(THREAD_ID, now_ms=200)) is None
    assert _run(store.usage_limit_active_thread_goal(THREAD_ID, now_ms=300)) is None
    assert _run(store.get_thread_goal(THREAD_ID)).status is ThreadGoalStatus.COMPLETE

    _run(store.replace_thread_goal(THREAD_ID, "active", ThreadGoalStatus.ACTIVE, 0, now_ms=400, goal_id="goal-2"))
    limited = _run(store.usage_limit_active_thread_goal(THREAD_ID, now_ms=500))
    assert limited is not None
    assert limited.status is ThreadGoalStatus.USAGE_LIMITED


def test_budget_limit_transitions_and_preservation_rules() -> None:
    # Rust crate: codex-state
    # Rust module/tests: immediate budget-limit transitions and paused/blocked
    # preservation for budget-limited goals.
    store = GoalStore(_connection())

    created = _run(store.replace_thread_goal(THREAD_ID, "budget", ThreadGoalStatus.ACTIVE, 0, now_ms=100, goal_id="goal-1"))
    paused = _run(store.update_thread_goal(THREAD_ID, GoalUpdate(status=ThreadGoalStatus.PAUSED), now_ms=200))
    blocked = _run(store.update_thread_goal(THREAD_ID, GoalUpdate(status=ThreadGoalStatus.BLOCKED), now_ms=300))
    reactivated = _run(store.update_thread_goal(THREAD_ID, GoalUpdate(status=ThreadGoalStatus.ACTIVE), now_ms=400))

    assert created.status is ThreadGoalStatus.BUDGET_LIMITED
    assert paused.status is ThreadGoalStatus.BUDGET_LIMITED
    assert blocked.status is ThreadGoalStatus.BUDGET_LIMITED
    assert reactivated.status is ThreadGoalStatus.BUDGET_LIMITED


def test_usage_accounting_modes_and_budget_promotion() -> None:
    # Rust crate: codex-state
    # Rust module/tests: usage accounting updates active goals, skips active
    # status only for budget-limited goals, and can account stopped goals.
    store = GoalStore(_connection())
    _run(store.replace_thread_goal(THREAD_ID, "usage", ThreadGoalStatus.ACTIVE, 10, now_ms=100, goal_id="goal-1"))

    first = _run(store.account_thread_goal_usage(THREAD_ID, 5, 9, GoalAccountingMode.ACTIVE_ONLY, now_ms=200))
    second = _run(store.account_thread_goal_usage(THREAD_ID, 1, 1, GoalAccountingMode.ACTIVE_ONLY, now_ms=300))
    skipped = _run(store.account_thread_goal_usage(THREAD_ID, 1, 1, GoalAccountingMode.ACTIVE_STATUS_ONLY, now_ms=400))

    assert first.updated is True
    assert first.goal.tokens_used == 9
    assert first.goal.status is ThreadGoalStatus.ACTIVE
    assert second.updated is True
    assert second.goal.tokens_used == 10
    assert second.goal.status is ThreadGoalStatus.BUDGET_LIMITED
    assert skipped.updated is False
    assert skipped.goal.tokens_used == 10

    paused = _run(store.replace_thread_goal(THREAD_ID, "paused", ThreadGoalStatus.PAUSED, 5, now_ms=500, goal_id="goal-2"))
    stopped = _run(store.account_thread_goal_usage(THREAD_ID, 2, 6, GoalAccountingMode.ACTIVE_OR_STOPPED, now_ms=600))
    assert paused.status is ThreadGoalStatus.PAUSED
    assert stopped.updated is True
    assert stopped.goal.status is ThreadGoalStatus.BUDGET_LIMITED
    assert stopped.goal.tokens_used == 6


def test_goal_update_can_leave_token_budget_unchanged_and_path_backed_db(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/items: GoalUpdate token_budget Option<Option<i64>> and
    # path-backed GoalStore DB opening.
    db_path = tmp_path / "goals_1.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        _init_schema(connection)
    finally:
        connection.close()
    store = GoalStore(db_path)

    _run(store.replace_thread_goal(THREAD_ID, "original", ThreadGoalStatus.ACTIVE, 123, now_ms=100, goal_id="goal-1"))
    updated = _run(
        store.update_thread_goal(
            THREAD_ID,
            GoalUpdate(objective="renamed", token_budget=TOKEN_BUDGET_UNCHANGED),
            now_ms=200,
        )
    )

    assert updated.objective == "renamed"
    assert updated.token_budget == 123
