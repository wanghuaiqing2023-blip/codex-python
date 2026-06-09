"""Port of Rust ``codex-cloud-tasks-mock-client``.

Rust source:
- ``codex/codex-rs/cloud-tasks-mock-client/src/lib.rs``
- ``codex/codex-rs/cloud-tasks-mock-client/src/mock.rs``
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    READY = "ready"
    PENDING = "pending"


class AttemptStatus(str, Enum):
    COMPLETED = "completed"


class ApplyStatus(str, Enum):
    SUCCESS = "success"


class CloudTaskError(Exception):
    pass


@dataclass(frozen=True)
class TaskId:
    value: str

    @property
    def id(self) -> str:
        return self.value

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DiffSummary:
    files_changed: int
    lines_added: int
    lines_removed: int


@dataclass(frozen=True)
class TaskSummary:
    id: TaskId
    title: str
    status: TaskStatus
    updated_at: float
    environment_id: str | None
    environment_label: str | None
    summary: DiffSummary
    is_review: bool = False
    attempt_total: int | None = None


@dataclass(frozen=True)
class TaskListPage:
    tasks: list[TaskSummary]
    cursor: str | None = None


@dataclass(frozen=True)
class TaskText:
    prompt: str | None
    messages: list[str]
    turn_id: str | None
    sibling_turn_ids: list[str] = field(default_factory=list)
    attempt_placement: int | None = None
    attempt_status: AttemptStatus = AttemptStatus.COMPLETED


@dataclass(frozen=True)
class ApplyOutcome:
    applied: bool
    status: ApplyStatus
    message: str
    skipped_paths: list[str] = field(default_factory=list)
    conflict_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnAttempt:
    turn_id: str
    attempt_placement: int | None
    created_at: float | None
    status: AttemptStatus
    diff: str | None
    messages: list[str]


@dataclass(frozen=True)
class CreatedTask:
    id: TaskId


class MockClient:
    async def list_tasks(
        self, env: str | None = None, limit: int | None = None, cursor: str | None = None
    ) -> TaskListPage:
        del limit, cursor
        if env == "env-A":
            rows = [("T-2000", "A: First", TaskStatus.READY)]
        elif env == "env-B":
            rows = [
                ("T-3000", "B: One", TaskStatus.READY),
                ("T-3001", "B: Two", TaskStatus.PENDING),
            ]
        else:
            rows = [
                ("T-1000", "Update README formatting", TaskStatus.READY),
                ("T-1001", "Fix clippy warnings in core", TaskStatus.PENDING),
                ("T-1002", "Add contributing guide", TaskStatus.READY),
            ]

        environment_label = "Global" if env is None else "Env A" if env == "env-A" else "Env B" if env == "env-B" else env
        tasks: list[TaskSummary] = []
        for id_str, title, status in rows:
            task_id = TaskId(id_str)
            added, removed = count_from_unified(mock_diff_for(task_id))
            tasks.append(
                TaskSummary(
                    id=task_id,
                    title=title,
                    status=status,
                    updated_at=time.time(),
                    environment_id=env,
                    environment_label=environment_label,
                    summary=DiffSummary(files_changed=1, lines_added=added, lines_removed=removed),
                    is_review=False,
                    attempt_total=2 if id_str == "T-1000" else 1,
                )
            )
        return TaskListPage(tasks=tasks, cursor=None)

    async def get_task_summary(self, id: TaskId) -> TaskSummary:
        for task in (await self.list_tasks()).tasks:
            if task.id == id:
                return task
        raise CloudTaskError(f"Task {id.value} not found (mock)")

    async def get_task_diff(self, id: TaskId) -> str | None:
        return mock_diff_for(id)

    async def get_task_messages(self, id: TaskId) -> list[str]:
        del id
        return ["Mock assistant output: this task contains no diff."]

    async def get_task_text(self, id: TaskId) -> TaskText:
        del id
        return TaskText(
            prompt="Why is there no diff?",
            messages=["Mock assistant output: this task contains no diff."],
            turn_id="mock-turn",
            sibling_turn_ids=[],
            attempt_placement=0,
            attempt_status=AttemptStatus.COMPLETED,
        )

    async def apply_task(self, id: TaskId, diff_override: str | None = None) -> ApplyOutcome:
        del diff_override
        return ApplyOutcome(
            applied=True,
            status=ApplyStatus.SUCCESS,
            message=f"Applied task {id.value} locally (mock)",
        )

    async def apply_task_preflight(self, id: TaskId, diff_override: str | None = None) -> ApplyOutcome:
        del diff_override
        return ApplyOutcome(
            applied=False,
            status=ApplyStatus.SUCCESS,
            message=f"Preflight passed for task {id.value} (mock)",
        )

    async def list_sibling_attempts(self, task: TaskId, turn_id: str) -> list[TurnAttempt]:
        del turn_id
        if task.value == "T-1000":
            return [
                TurnAttempt(
                    turn_id="T-1000-attempt-2",
                    attempt_placement=1,
                    created_at=time.time(),
                    status=AttemptStatus.COMPLETED,
                    diff=mock_diff_for(task),
                    messages=["Mock alternate attempt"],
                )
            ]
        return []

    async def create_task(
        self, env_id: str, prompt: str, git_ref: str, qa_mode: bool, best_of_n: int
    ) -> CreatedTask:
        del env_id, prompt, git_ref, qa_mode, best_of_n
        return CreatedTask(id=TaskId(f"task_local_{int(time.time() * 1000)}"))


def mock_diff_for(id: TaskId) -> str:
    if id.value == "T-1000":
        return (
            "diff --git a/README.md b/README.md\n"
            "index 000000..111111 100644\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1,2 +1,3 @@\n"
            " Intro\n"
            "-Hello\n"
            "+Hello, world!\n"
            "+Task: T-1000\n"
        )
    if id.value == "T-1001":
        return (
            "diff --git a/core/src/lib.rs b/core/src/lib.rs\n"
            "index 000000..111111 100644\n"
            "--- a/core/src/lib.rs\n"
            "+++ b/core/src/lib.rs\n"
            "@@ -1,2 +1,1 @@\n"
            "-use foo;\n"
            " use bar;\n"
        )
    return (
        "diff --git a/CONTRIBUTING.md b/CONTRIBUTING.md\n"
        "index 000000..111111 100644\n"
        "--- /dev/null\n"
        "+++ b/CONTRIBUTING.md\n"
        "@@ -0,0 +1,3 @@\n"
        "+## Contributing\n"
        "+Please open PRs.\n"
        "+Thanks!\n"
    )


def count_from_unified(diff: str) -> tuple[int, int]:
    added = 0
    removed = 0
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


__all__ = [
    "ApplyOutcome",
    "ApplyStatus",
    "AttemptStatus",
    "CloudTaskError",
    "CreatedTask",
    "DiffSummary",
    "MockClient",
    "TaskId",
    "TaskListPage",
    "TaskStatus",
    "TaskSummary",
    "TaskText",
    "TurnAttempt",
    "count_from_unified",
    "mock_diff_for",
]
