import asyncio
from datetime import datetime, timezone

from pycodex.cloud_tasks import (
    App,
    AttemptView,
    DetailView,
    DiffOverlay,
    load_tasks,
)
from pycodex.cloud_tasks_client import (
    AttemptStatus,
    DiffSummary,
    TaskId,
    TaskListPage,
    TaskStatus,
    TaskSummary,
)


def make_task(
    id_value: str,
    title: str,
    *,
    env: str | None = None,
    is_review: bool = False,
) -> TaskSummary:
    return TaskSummary(
        id=TaskId(id_value),
        title=title,
        status=TaskStatus.READY,
        updated_at=datetime(2026, 6, 22, tzinfo=timezone.utc),
        environment_id=env,
        environment_label=None,
        summary=DiffSummary(),
        is_review=is_review,
        attempt_total=1,
    )


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.by_env = {
            None: [make_task("T-0", "root-1"), make_task("T-1", "root-review", is_review=True)],
            "env-A": [make_task("T-A", "A-1", env="env-A")],
            "env-B": [
                make_task("T-B1", "B-1", env="env-B"),
                make_task("T-B2", "B-2", env="env-B"),
                make_task("T-B3", "B-3", env="env-B"),
            ],
        }

    async def list_tasks(self, env, limit, cursor):
        self.calls.append((env, limit, cursor))
        return TaskListPage(tasks=list(self.by_env.get(env, [])), cursor=cursor)


def test_app_new_next_prev_match_source_contract():
    # Rust crate/module: codex-cloud-tasks/src/app.rs::App::{new,next,prev}.
    app = App.new()
    assert app.tasks == []
    assert app.selected == 0
    assert app.status == "Press r to refresh"
    assert app.best_of_n == 1
    assert app.in_flight == set()

    app.next()
    app.prev()
    assert app.selected == 0

    app.tasks = [make_task("T-1", "one"), make_task("T-2", "two")]
    app.next()
    assert app.selected == 1
    app.next()
    assert app.selected == 1
    app.prev()
    assert app.selected == 0
    app.prev()
    assert app.selected == 0


def test_load_tasks_uses_env_parameter_and_filters_review_tasks():
    # Rust crate/module/test: codex-cloud-tasks/src/app.rs::load_tasks_uses_env_parameter.
    backend = FakeBackend()

    root = asyncio.run(load_tasks(backend, None))
    assert [task.title for task in root] == ["root-1"]

    env_a = asyncio.run(load_tasks(backend, "env-A"))
    assert [task.title for task in env_a] == ["A-1"]

    env_b = asyncio.run(load_tasks(backend, "env-B"))
    assert [task.title for task in env_b] == ["B-1", "B-2", "B-3"]

    assert backend.calls == [
        (None, 20, None),
        ("env-A", 20, None),
        ("env-B", 20, None),
    ]


def test_attempt_view_has_diff_and_text_contracts():
    # Rust crate/module: codex-cloud-tasks/src/app.rs::AttemptView::{has_diff,has_text}.
    attempt = AttemptView()
    assert attempt.status is AttemptStatus.UNKNOWN
    assert attempt.has_diff() is False
    assert attempt.has_text() is False

    attempt.diff_lines = ["diff"]
    assert attempt.has_diff() is True
    attempt.text_lines = ["output"]
    assert attempt.has_text() is True

    prompt_only = AttemptView(prompt="prompt")
    assert prompt_only.has_text() is True


def test_diff_overlay_new_and_attempt_selection_contracts():
    # Rust crate/module: codex-cloud-tasks/src/app.rs::DiffOverlay.
    overlay = DiffOverlay.new(TaskId("task-1"), "Title", attempt_total_hint=3)

    assert overlay.title == "Title"
    assert overlay.task_id == TaskId("task-1")
    assert overlay.base_can_apply is False
    assert overlay.current_view is DetailView.PROMPT
    assert overlay.selected_attempt == 0
    assert overlay.attempt_count() == 1
    assert overlay.expected_attempts() == 3
    assert overlay.attempt_display_total() == 3
    assert overlay.current_can_apply() is False
    assert overlay.sd.wrapped_lines() == []

    base = overlay.base_attempt_mut()
    base.diff_lines = ["+a"]
    base.diff_raw = "diff"
    base.text_lines = ["message"]
    base.prompt = "prompt"

    overlay.set_view(DetailView.DIFF)
    overlay.sd.set_width(80)
    assert overlay.diff_lines == ["+a"]
    assert overlay.sd.wrapped_lines() == ["+a"]
    assert overlay.current_can_apply() is True

    overlay.set_view(DetailView.PROMPT)
    overlay.sd.set_width(80)
    assert overlay.text_lines == ["message"]
    assert overlay.prompt == "prompt"
    assert overlay.sd.wrapped_lines() == ["message"]
    assert overlay.current_can_apply() is False


def test_diff_overlay_step_attempt_wraps_and_missing_attempt_loading_state():
    # Rust crate/module: codex-cloud-tasks/src/app.rs::DiffOverlay::step_attempt/apply_selection_to_fields.
    overlay = DiffOverlay.new(TaskId("task-1"), "Title", attempt_total_hint=None)
    overlay.attempts = [
        AttemptView(diff_lines=["first"], diff_raw="diff-1"),
        AttemptView(diff_lines=["second"], diff_raw="diff-2"),
    ]
    overlay.set_view(DetailView.DIFF)

    assert overlay.expected_attempts() == 2
    assert overlay.attempt_display_total() == 2
    assert overlay.step_attempt(1) is True
    assert overlay.selected_attempt == 1
    overlay.sd.set_width(80)
    assert overlay.sd.wrapped_lines() == ["second"]
    assert overlay.step_attempt(1) is True
    assert overlay.selected_attempt == 0
    assert overlay.step_attempt(-1) is True
    assert overlay.selected_attempt == 1

    overlay.attempts = []
    assert overlay.base_attempt_mut() == AttemptView()
    overlay.attempts = []
    overlay.apply_selection_to_fields()
    overlay.sd.set_width(80)
    assert overlay.sd.wrapped_lines() == ["<loading attempt>"]

    overlay.attempts = [AttemptView()]
    overlay.selected_attempt = 0
    assert overlay.step_attempt(1) is False
    overlay.set_view(DetailView.DIFF)
    overlay.sd.set_width(80)
    assert overlay.sd.wrapped_lines() == ["<no diff available>"]
    overlay.set_view(DetailView.PROMPT)
    overlay.sd.set_width(80)
    assert overlay.sd.wrapped_lines() == ["<no output>"]
