"""Port of Rust ``codex-cloud-tasks-client/src/api.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol, TypeAlias, runtime_checkable


class CloudTaskError(Exception):
    """Python counterpart of Rust ``CloudTaskError``."""

    @classmethod
    def unimplemented(cls, name: str) -> "CloudTaskError":
        return cls(f"unimplemented: {name}")

    @classmethod
    def http(cls, message: str) -> "CloudTaskError":
        return cls(f"http error: {message}")

    @classmethod
    def io(cls, message: str) -> "CloudTaskError":
        return cls(f"io error: {message}")

    @classmethod
    def msg(cls, message: str) -> "CloudTaskError":
        return cls(message)


Result: TypeAlias = object


@dataclass(frozen=True)
class TaskId:
    value: str

    @property
    def id(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


class TaskStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    APPLIED = "applied"
    ERROR = "error"


@dataclass(frozen=True)
class DiffSummary:
    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0


@dataclass(frozen=True)
class TaskSummary:
    id: TaskId
    title: str
    status: TaskStatus
    updated_at: datetime
    environment_id: str | None
    environment_label: str | None
    summary: DiffSummary
    is_review: bool = False
    attempt_total: int | None = None


class AttemptStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TurnAttempt:
    turn_id: str
    attempt_placement: int | None
    created_at: datetime | None
    status: AttemptStatus
    diff: str | None
    messages: list[str]


class ApplyStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass(frozen=True)
class ApplyOutcome:
    applied: bool
    status: ApplyStatus
    message: str
    skipped_paths: list[str] = field(default_factory=list)
    conflict_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CreatedTask:
    id: TaskId


@dataclass(frozen=True)
class TaskListPage:
    tasks: list[TaskSummary]
    cursor: str | None = None


@dataclass(frozen=True)
class TaskText:
    prompt: str | None = None
    messages: list[str] = field(default_factory=list)
    turn_id: str | None = None
    sibling_turn_ids: list[str] = field(default_factory=list)
    attempt_placement: int | None = None
    attempt_status: AttemptStatus = AttemptStatus.UNKNOWN


@runtime_checkable
class CloudBackend(Protocol):
    async def list_tasks(
        self, env: str | None = None, limit: int | None = None, cursor: str | None = None
    ) -> TaskListPage: ...

    async def get_task_summary(self, id: TaskId) -> TaskSummary: ...

    async def get_task_diff(self, id: TaskId) -> str | None: ...

    async def get_task_messages(self, id: TaskId) -> list[str]: ...

    async def get_task_text(self, id: TaskId) -> TaskText: ...

    async def list_sibling_attempts(self, task: TaskId, turn_id: str) -> list[TurnAttempt]: ...

    async def apply_task_preflight(
        self, id: TaskId, diff_override: str | None = None
    ) -> ApplyOutcome: ...

    async def apply_task(self, id: TaskId, diff_override: str | None = None) -> ApplyOutcome: ...

    async def create_task(
        self, env_id: str, prompt: str, git_ref: str, qa_mode: bool, best_of_n: int
    ) -> CreatedTask: ...


__all__ = [
    "ApplyOutcome",
    "ApplyStatus",
    "AttemptStatus",
    "CloudBackend",
    "CloudTaskError",
    "CreatedTask",
    "DiffSummary",
    "Result",
    "TaskId",
    "TaskListPage",
    "TaskStatus",
    "TaskSummary",
    "TaskText",
    "TurnAttempt",
]
