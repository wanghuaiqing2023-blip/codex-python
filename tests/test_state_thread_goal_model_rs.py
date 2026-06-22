from datetime import datetime, timezone

import pytest

from pycodex.protocol import ThreadId
from pycodex.state.model.thread_goal import (
    ThreadGoal,
    ThreadGoalRow,
    ThreadGoalStatus,
    epoch_millis_to_datetime,
)


THREAD_ID = "123e4567-e89b-12d3-a456-426614174000"


def test_thread_goal_status_wire_values_parse_and_predicates() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_goal.rs::ThreadGoalStatus
    # Behavior contract: persisted status strings and active/terminal predicates
    # match Rust's as_str/is_active/is_terminal implementations.
    assert ThreadGoalStatus.ACTIVE.as_str() == "active"
    assert ThreadGoalStatus.PAUSED.as_str() == "paused"
    assert ThreadGoalStatus.BLOCKED.as_str() == "blocked"
    assert ThreadGoalStatus.USAGE_LIMITED.as_str() == "usage_limited"
    assert ThreadGoalStatus.BUDGET_LIMITED.as_str() == "budget_limited"
    assert ThreadGoalStatus.COMPLETE.as_str() == "complete"

    assert ThreadGoalStatus.parse("active") is ThreadGoalStatus.ACTIVE
    assert ThreadGoalStatus.ACTIVE.is_active() is True
    assert ThreadGoalStatus.PAUSED.is_active() is False
    assert ThreadGoalStatus.BUDGET_LIMITED.is_terminal() is True
    assert ThreadGoalStatus.COMPLETE.is_terminal() is True
    assert ThreadGoalStatus.BLOCKED.is_terminal() is False
    assert ThreadGoalStatus.USAGE_LIMITED.is_terminal() is False


def test_thread_goal_status_parse_rejects_unknown() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_goal.rs::TryFrom<&str>
    # Behavior contract: unknown persisted status values are invalid.
    with pytest.raises(ValueError, match="unknown thread goal status `stopped`"):
        ThreadGoalStatus.parse("stopped")


def test_thread_goal_row_to_thread_goal_converts_ids_status_and_timestamps() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_goal.rs::TryFrom<ThreadGoalRow>
    # Behavior contract: storage rows parse ThreadId/status and convert epoch
    # millis to UTC DateTime values without changing numeric counters.
    row = ThreadGoalRow.from_mapping(
        {
            "thread_id": THREAD_ID,
            "goal_id": "goal-1",
            "objective": "ship parity",
            "status": "budget_limited",
            "token_budget": 1000,
            "tokens_used": 900,
            "time_used_seconds": 12,
            "created_at_ms": 1_700_000_000_123,
            "updated_at_ms": 1_700_000_001_456,
        }
    )

    goal = row.to_thread_goal()

    assert goal == ThreadGoal(
        thread_id=ThreadId.from_string(THREAD_ID),
        goal_id="goal-1",
        objective="ship parity",
        status=ThreadGoalStatus.BUDGET_LIMITED,
        token_budget=1000,
        tokens_used=900,
        time_used_seconds=12,
        created_at=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc).replace(
            microsecond=123_000
        ),
        updated_at=datetime.fromtimestamp(1_700_000_001, tz=timezone.utc).replace(
            microsecond=456_000
        ),
    )


def test_thread_goal_row_accepts_null_token_budget() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_goal.rs::ThreadGoalRow
    # Behavior contract: nullable token_budget remains None in the domain model.
    goal = ThreadGoalRow.from_mapping(
        {
            "thread_id": THREAD_ID,
            "goal_id": "goal-2",
            "objective": "no budget",
            "status": "active",
            "token_budget": None,
            "tokens_used": 0,
            "time_used_seconds": 0,
            "created_at_ms": 0,
            "updated_at_ms": 0,
        }
    ).to_thread_goal()

    assert goal.token_budget is None
    assert goal.status is ThreadGoalStatus.ACTIVE


def test_thread_goal_dataclass_normalizes_status_and_utc_datetime() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_goal.rs::ThreadGoal
    # Behavior contract: Python preserves the Rust domain fields while accepting
    # row-derived status strings and normalizing datetimes to UTC.
    goal = ThreadGoal(
        thread_id=ThreadId.from_string(THREAD_ID),
        goal_id="goal-3",
        objective="normalize",
        status="complete",
        token_budget=None,
        tokens_used=1,
        time_used_seconds=2,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        updated_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert goal.status is ThreadGoalStatus.COMPLETE
    assert goal.created_at.tzinfo is timezone.utc
    assert goal.updated_at.tzinfo is timezone.utc


def test_thread_goal_row_rejects_invalid_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_goal.rs::ThreadGoalRow::try_from_row
    # Behavior contract: invalid row values fail instead of being silently
    # coerced into storage/domain fields.
    valid = {
        "thread_id": THREAD_ID,
        "goal_id": "goal-4",
        "objective": "validate",
        "status": "paused",
        "token_budget": 10,
        "tokens_used": 1,
        "time_used_seconds": 2,
        "created_at_ms": 3,
        "updated_at_ms": 4,
    }

    invalid_thread = dict(valid, thread_id=123)
    with pytest.raises(TypeError, match="thread_id must be a string"):
        ThreadGoalRow.from_mapping(invalid_thread)

    invalid_budget = dict(valid, token_budget=2**63)
    with pytest.raises(ValueError, match="token_budget must fit"):
        ThreadGoalRow.from_mapping(invalid_budget)

    invalid_counter = dict(valid, tokens_used=True)
    with pytest.raises(TypeError, match="tokens_used must be an integer"):
        ThreadGoalRow.from_mapping(invalid_counter)

    invalid_status = dict(valid, status="done")
    with pytest.raises(ValueError, match="unknown thread goal status `done`"):
        ThreadGoalRow.from_mapping(invalid_status).to_thread_goal()


def test_epoch_millis_to_datetime_rejects_invalid_timestamp() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/thread_goal.rs::epoch_millis_to_datetime use
    # Behavior contract: invalid Unix millisecond timestamps fail.
    with pytest.raises(ValueError, match="invalid unix timestamp millis"):
        epoch_millis_to_datetime(10**30)
