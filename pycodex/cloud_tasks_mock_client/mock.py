"""Port of Rust ``codex-cloud-tasks-mock-client/src/mock.rs``."""

from __future__ import annotations

from datetime import datetime, timezone

from pycodex.cloud_tasks_client import (
    ApplyOutcome,
    ApplyStatus,
    AttemptStatus,
    CloudTaskError,
    CreatedTask,
    DiffSummary,
    TaskId,
    TaskListPage,
    TaskStatus,
    TaskSummary,
    TaskText,
    TurnAttempt,
)


class MockClient:
    async def list_tasks(
        self,
        env: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
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

        environment_label = (
            "Global"
            if env is None
            else "Env A"
            if env == "env-A"
            else "Env B"
            if env == "env-B"
            else env
        )
        tasks = []
        for id_str, title, status in rows:
            task_id = TaskId(id_str)
            added, removed = count_from_unified(mock_diff_for(task_id))
            tasks.append(
                TaskSummary(
                    id=task_id,
                    title=title,
                    status=status,
                    updated_at=datetime.now(timezone.utc),
                    environment_id=env,
                    environment_label=environment_label,
                    summary=DiffSummary(
                        files_changed=1,
                        lines_added=added,
                        lines_removed=removed,
                    ),
                    is_review=False,
                    attempt_total=2 if id_str == "T-1000" else 1,
                )
            )
        return TaskListPage(tasks=tasks, cursor=None)

    async def get_task_summary(self, id: TaskId) -> TaskSummary:
        tasks = (await self.list_tasks()).tasks
        for task in tasks:
            if task.id == id:
                return task
        raise CloudTaskError.msg(f"Task {id.value} not found (mock)")

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

    async def apply_task(
        self,
        id: TaskId,
        diff_override: str | None = None,
    ) -> ApplyOutcome:
        del diff_override
        return ApplyOutcome(
            applied=True,
            status=ApplyStatus.SUCCESS,
            message=f"Applied task {id.value} locally (mock)",
            skipped_paths=[],
            conflict_paths=[],
        )

    async def apply_task_preflight(
        self,
        id: TaskId,
        diff_override: str | None = None,
    ) -> ApplyOutcome:
        del diff_override
        return ApplyOutcome(
            applied=False,
            status=ApplyStatus.SUCCESS,
            message=f"Preflight passed for task {id.value} (mock)",
            skipped_paths=[],
            conflict_paths=[],
        )

    async def list_sibling_attempts(
        self,
        task: TaskId,
        turn_id: str,
    ) -> list[TurnAttempt]:
        del turn_id
        if task.value != "T-1000":
            return []
        return [
            TurnAttempt(
                turn_id="T-1000-attempt-2",
                attempt_placement=1,
                created_at=datetime.now(timezone.utc),
                status=AttemptStatus.COMPLETED,
                diff=mock_diff_for(task),
                messages=["Mock alternate attempt"],
            )
        ]

    async def create_task(
        self,
        env_id: str,
        prompt: str,
        git_ref: str,
        qa_mode: bool,
        best_of_n: int,
    ) -> CreatedTask:
        del env_id, prompt, git_ref, qa_mode, best_of_n
        timestamp_ms = int(datetime.now(timezone.utc).timestamp() * 1_000)
        return CreatedTask(id=TaskId(f"task_local_{timestamp_ms}"))


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


__all__ = ["MockClient"]
