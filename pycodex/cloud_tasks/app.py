"""Port of Rust ``codex-cloud-tasks/src/app.rs`` state helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pycodex.cloud_tasks.new_task import NewTaskPage
from pycodex.cloud_tasks.scrollable_diff import ScrollableDiff
from pycodex.cloud_tasks_client import AttemptStatus
from pycodex.cloud_tasks_client import TaskId
from pycodex.cloud_tasks_client import TaskSummary


@dataclass(frozen=True)
class EnvModalState:
    query: str = ""
    selected: int = 0


@dataclass(frozen=True)
class BestOfModalState:
    selected: int = 0


class DetailView(str, Enum):
    DIFF = "diff"
    PROMPT = "prompt"


@dataclass
class ApplyModalState:
    task_id: TaskId
    title: str
    result_message: str | None = None
    result_level: Any | None = None
    skipped_paths: list[str] = field(default_factory=list)
    conflict_paths: list[str] = field(default_factory=list)
    diff_override: str | None = None


@dataclass
class App:
    tasks: list[TaskSummary] = field(default_factory=list)
    selected: int = 0
    status: str = "Press r to refresh"
    diff_overlay: "DiffOverlay | None" = None
    spinner_start: Any | None = None
    refresh_inflight: bool = False
    details_inflight: bool = False
    env_filter: str | None = None
    env_modal: EnvModalState | None = None
    apply_modal: ApplyModalState | None = None
    best_of_modal: BestOfModalState | None = None
    environments: list[Any] = field(default_factory=list)
    env_last_loaded: Any | None = None
    env_loading: bool = False
    env_error: str | None = None
    new_task: NewTaskPage | None = None
    best_of_n: int = 1
    apply_preflight_inflight: bool = False
    apply_inflight: bool = False
    list_generation: int = 0
    in_flight: set[str] = field(default_factory=set)

    @classmethod
    def new(cls) -> "App":
        return cls()

    def next(self) -> None:
        if not self.tasks:
            return
        self.selected = min(self.selected + 1, len(self.tasks) - 1)

    def prev(self) -> None:
        if not self.tasks:
            return
        if self.selected > 0:
            self.selected -= 1


@dataclass
class AttemptView:
    turn_id: str | None = None
    status: AttemptStatus = AttemptStatus.UNKNOWN
    attempt_placement: int | None = None
    diff_lines: list[str] = field(default_factory=list)
    text_lines: list[str] = field(default_factory=list)
    prompt: str | None = None
    diff_raw: str | None = None

    def has_diff(self) -> bool:
        return bool(self.diff_lines)

    def has_text(self) -> bool:
        return bool(self.text_lines) or self.prompt is not None


@dataclass
class DiffOverlay:
    title: str
    task_id: TaskId
    sd: ScrollableDiff
    base_can_apply: bool = False
    diff_lines: list[str] = field(default_factory=list)
    text_lines: list[str] = field(default_factory=list)
    prompt: str | None = None
    attempts: list[AttemptView] = field(default_factory=lambda: [AttemptView()])
    selected_attempt: int = 0
    current_view: DetailView = DetailView.PROMPT
    base_turn_id: str | None = None
    sibling_turn_ids: list[str] = field(default_factory=list)
    attempt_total_hint: int | None = None

    @classmethod
    def new(
        cls, task_id: TaskId, title: str, attempt_total_hint: int | None = None
    ) -> "DiffOverlay":
        sd = ScrollableDiff.new()
        sd.set_content([])
        return cls(
            title=title,
            task_id=task_id,
            sd=sd,
            attempt_total_hint=attempt_total_hint,
        )

    def current_attempt(self) -> AttemptView | None:
        if 0 <= self.selected_attempt < len(self.attempts):
            return self.attempts[self.selected_attempt]
        return None

    def base_attempt_mut(self) -> AttemptView:
        if not self.attempts:
            self.attempts.append(AttemptView())
        return self.attempts[0]

    def set_view(self, view: DetailView) -> None:
        self.current_view = view
        self.apply_selection_to_fields()

    def expected_attempts(self) -> int | None:
        if self.attempt_total_hint is not None:
            return self.attempt_total_hint
        if not self.attempts:
            return None
        return len(self.attempts)

    def attempt_count(self) -> int:
        return len(self.attempts)

    def attempt_display_total(self) -> int:
        expected = self.expected_attempts()
        if expected is not None:
            return expected
        return max(len(self.attempts), 1)

    def step_attempt(self, delta: int) -> bool:
        total = len(self.attempts)
        if total <= 1:
            return False
        self.selected_attempt = (self.selected_attempt + int(delta)) % total
        self.apply_selection_to_fields()
        return True

    def current_can_apply(self) -> bool:
        attempt = self.current_attempt()
        return (
            self.current_view is DetailView.DIFF
            and attempt is not None
            and bool(attempt.diff_raw)
        )

    def apply_selection_to_fields(self) -> None:
        attempt = self.current_attempt()
        if attempt is None:
            self.diff_lines.clear()
            self.text_lines.clear()
            self.prompt = None
            self.sd.set_content(["<loading attempt>"])
            return

        self.diff_lines = list(attempt.diff_lines)
        self.text_lines = list(attempt.text_lines)
        self.prompt = attempt.prompt

        if self.current_view is DetailView.DIFF:
            self.sd.set_content(
                list(self.diff_lines) if self.diff_lines else ["<no diff available>"]
            )
        else:
            self.sd.set_content(
                list(self.text_lines) if self.text_lines else ["<no output>"]
            )


async def load_tasks(backend: Any, env: str | None) -> list[TaskSummary]:
    page = await asyncio.wait_for(backend.list_tasks(env, 20, None), timeout=5)
    return [task for task in page.tasks if not task.is_review]


__all__ = [
    "App",
    "ApplyModalState",
    "AttemptView",
    "BestOfModalState",
    "DetailView",
    "DiffOverlay",
    "EnvModalState",
    "load_tasks",
]
