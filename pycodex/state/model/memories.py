"""Memory extraction model types ported from ``codex-state/src/model/memories.rs``."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import ThreadId

JsonValue = Any


@dataclass(frozen=True)
class Stage1Output:
    thread_id: ThreadId
    rollout_path: Path
    source_updated_at: datetime
    raw_memory: str
    rollout_summary: str
    rollout_slug: str | None
    cwd: Path
    git_branch: str | None
    generated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.thread_id, ThreadId):
            raise TypeError("thread_id must be a ThreadId")
        object.__setattr__(self, "rollout_path", _path(self.rollout_path, "rollout_path"))
        object.__setattr__(self, "source_updated_at", _datetime_utc(self.source_updated_at, "source_updated_at"))
        object.__setattr__(self, "raw_memory", _required_str(self.raw_memory, "raw_memory"))
        object.__setattr__(self, "rollout_summary", _required_str(self.rollout_summary, "rollout_summary"))
        object.__setattr__(self, "rollout_slug", _optional_str(self.rollout_slug, "rollout_slug"))
        object.__setattr__(self, "cwd", _path(self.cwd, "cwd"))
        object.__setattr__(self, "git_branch", _optional_str(self.git_branch, "git_branch"))
        object.__setattr__(self, "generated_at", _datetime_utc(self.generated_at, "generated_at"))


@dataclass(frozen=True)
class Stage1JobClaimed:
    ownership_token: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ownership_token", _required_str(self.ownership_token, "ownership_token"))


class Stage1JobClaimOutcome(str, Enum):
    SKIPPED_UP_TO_DATE = "skipped_up_to_date"
    SKIPPED_RUNNING = "skipped_running"
    SKIPPED_RETRY_BACKOFF = "skipped_retry_backoff"
    SKIPPED_RETRY_EXHAUSTED = "skipped_retry_exhausted"


@dataclass(frozen=True)
class Stage1JobClaim:
    thread: JsonValue
    ownership_token: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ownership_token", _required_str(self.ownership_token, "ownership_token"))


@dataclass(frozen=True)
class Stage1StartupClaimParams:
    scan_limit: int
    max_claimed: int
    max_age_days: int
    min_rollout_idle_hours: int
    allowed_sources: tuple[str, ...]
    lease_seconds: int

    def __post_init__(self) -> None:
        _ensure_usize(self.scan_limit, "scan_limit")
        _ensure_usize(self.max_claimed, "max_claimed")
        _ensure_i64(self.max_age_days, "max_age_days")
        _ensure_i64(self.min_rollout_idle_hours, "min_rollout_idle_hours")
        object.__setattr__(self, "allowed_sources", _string_tuple(self.allowed_sources, "allowed_sources"))
        _ensure_i64(self.lease_seconds, "lease_seconds")


@dataclass(frozen=True)
class Phase2JobClaimed:
    ownership_token: str
    input_watermark: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "ownership_token", _required_str(self.ownership_token, "ownership_token"))
        _ensure_i64(self.input_watermark, "input_watermark")


class Phase2JobClaimOutcome(str, Enum):
    SKIPPED_RETRY_UNAVAILABLE = "skipped_retry_unavailable"
    SKIPPED_COOLDOWN = "skipped_cooldown"
    SKIPPED_RUNNING = "skipped_running"


def claimed_stage1(ownership_token: str) -> Stage1JobClaimed:
    return Stage1JobClaimed(ownership_token=ownership_token)


def claimed_phase2(ownership_token: str, input_watermark: int) -> Phase2JobClaimed:
    return Phase2JobClaimed(ownership_token=ownership_token, input_watermark=input_watermark)


def _path(value: JsonValue, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a string or Path")
    return Path(value)


def _datetime_utc(value: JsonValue, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _required_str(value, name)


def _string_tuple(value: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence of strings")
    return tuple(_required_str(item, f"{name} item") for item in value)


def _ensure_i64(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _ensure_usize(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


__all__ = [
    "Phase2JobClaimOutcome",
    "Phase2JobClaimed",
    "Stage1JobClaim",
    "Stage1JobClaimOutcome",
    "Stage1JobClaimed",
    "Stage1Output",
    "Stage1StartupClaimParams",
    "claimed_phase2",
    "claimed_stage1",
]
