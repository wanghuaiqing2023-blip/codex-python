from datetime import datetime, timezone

import pytest

from pycodex.state import BackfillState, BackfillStatus, epoch_seconds_to_datetime


def test_backfill_status_wire_values_and_parse() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/backfill_state.rs::BackfillStatus
    # Behavior contract: persisted lifecycle strings are pending/running/complete.
    assert BackfillStatus.PENDING.as_str() == "pending"
    assert BackfillStatus.RUNNING.as_str() == "running"
    assert BackfillStatus.COMPLETE.as_str() == "complete"
    assert BackfillStatus.parse("pending") is BackfillStatus.PENDING
    assert BackfillStatus.parse("running") is BackfillStatus.RUNNING
    assert BackfillStatus.parse("complete") is BackfillStatus.COMPLETE


def test_backfill_status_parse_rejects_unknown() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/backfill_state.rs::BackfillStatus::parse
    # Behavior contract: unknown persisted status values are invalid.
    with pytest.raises(ValueError, match="invalid backfill status: stopped"):
        BackfillStatus.parse("stopped")


def test_backfill_state_defaults_match_rust_default() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/backfill_state.rs::BackfillState::default
    # Behavior contract: default state is pending with no watermark/success time.
    state = BackfillState()

    assert state == BackfillState(
        status=BackfillStatus.PENDING,
        last_watermark=None,
        last_success_at=None,
    )


def test_backfill_state_try_from_row_converts_epoch_seconds_to_utc() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/backfill_state.rs::BackfillState::try_from_row
    # Behavior contract: row status/watermark are parsed and last_success_at
    # epoch seconds become UTC DateTime values.
    state = BackfillState.try_from_row(
        {
            "status": "complete",
            "last_watermark": "rollout-42",
            "last_success_at": 1_700_000_000,
        }
    )

    assert state.status is BackfillStatus.COMPLETE
    assert state.last_watermark == "rollout-42"
    assert state.last_success_at == datetime.fromtimestamp(
        1_700_000_000, tz=timezone.utc
    )


def test_backfill_state_try_from_row_accepts_null_optional_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/backfill_state.rs::BackfillState::try_from_row
    # Behavior contract: nullable row fields remain None.
    state = BackfillState.try_from_row(
        {"status": "running", "last_watermark": None, "last_success_at": None}
    )

    assert state == BackfillState(status=BackfillStatus.RUNNING)


def test_backfill_state_try_from_row_rejects_invalid_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/backfill_state.rs::BackfillState::try_from_row
    # Behavior contract: invalid row values fail rather than silently coercing.
    with pytest.raises(TypeError, match="status must be a string"):
        BackfillState.try_from_row({"status": None})
    with pytest.raises(TypeError, match="last_watermark must be a string"):
        BackfillState.try_from_row({"status": "pending", "last_watermark": 123})
    with pytest.raises(TypeError, match="secs must be an integer"):
        BackfillState.try_from_row({"status": "pending", "last_success_at": "1"})


def test_epoch_seconds_to_datetime_rejects_invalid_timestamp() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/backfill_state.rs::epoch_seconds_to_datetime
    # Behavior contract: invalid Unix timestamps fail.
    with pytest.raises(ValueError, match="invalid unix timestamp"):
        epoch_seconds_to_datetime(10**30)
