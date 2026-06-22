"""Backfill lifecycle model ported from ``codex-state/src/model/backfill_state.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

JsonValue = Any


class BackfillStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"

    def as_str(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: str) -> "BackfillStatus":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"invalid backfill status: {value}") from exc


@dataclass(frozen=True)
class BackfillState:
    status: BackfillStatus = BackfillStatus.PENDING
    last_watermark: str | None = None
    last_success_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, BackfillStatus):
            object.__setattr__(self, "status", BackfillStatus.parse(str(self.status)))
        if self.last_watermark is not None and not isinstance(self.last_watermark, str):
            raise TypeError("last_watermark must be a string or None")
        if self.last_success_at is not None:
            object.__setattr__(
                self,
                "last_success_at",
                _datetime_utc(self.last_success_at, "last_success_at"),
            )

    @classmethod
    def try_from_row(cls, row: Mapping[str, JsonValue]) -> "BackfillState":
        status = _required_str(row.get("status"), "status")
        last_success_raw = row.get("last_success_at")
        return cls(
            status=BackfillStatus.parse(status),
            last_watermark=_optional_str(row.get("last_watermark"), "last_watermark"),
            last_success_at=epoch_seconds_to_datetime(last_success_raw) if last_success_raw is not None else None,
        )


def epoch_seconds_to_datetime(secs: int) -> datetime:
    if isinstance(secs, bool) or not isinstance(secs, int):
        raise TypeError("secs must be an integer")
    try:
        return datetime.fromtimestamp(secs, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"invalid unix timestamp: {secs}") from exc


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _required_str(value, name)


def _datetime_utc(value: JsonValue, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = ["BackfillState", "BackfillStatus", "epoch_seconds_to_datetime"]
