import asyncio
from datetime import datetime, timezone

import pytest

from pycodex.cloud_tasks import (
    App,
    AppEvent,
    ApplyModalState,
    AutodetectSelection,
    AttemptView,
    DetailView,
    DiffOverlay,
    EnvironmentRow,
    conversation_lines,
    handle_app_event,
    handle_apply_preflight_finished_event,
    handle_apply_finished_event,
    handle_attempts_loaded_event,
    handle_environment_autodetected_event,
    handle_environments_loaded_event,
    handle_details_diff_loaded_event,
    handle_details_failed_event,
    handle_details_messages_loaded_event,
    handle_new_task_submitted_event,
    handle_tasks_loaded_event,
    load_tasks,
    pretty_lines_from_error,
)
from pycodex.cloud_tasks_client import (
    ApplyOutcome,
    ApplyStatus,
    AttemptStatus,
    CreatedTask,
    DiffSummary,
    TaskId,
    TaskListPage,
    TaskStatus,
    TaskSummary,
    TurnAttempt,
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


def test_app_event_variant_payload_shapes_match_rust_enum():
    # Rust crate/module: codex-cloud-tasks/src/app.rs::AppEvent.
    # Source contract: internal background event enum variants and payload field names.
    task_id = TaskId("task-1")
    attempts = [object()]
    outcome = object()

    assert AppEvent.tasks_loaded("env-1", result=["task"]) == AppEvent(
        "TasksLoaded", {"env": "env-1", "result": ["task"]}
    )
    assert AppEvent.environment_autodetected(result="env") == AppEvent(
        "EnvironmentAutodetected", {"result": "env"}
    )
    assert AppEvent.environments_loaded(result=["env"]) == AppEvent(
        "EnvironmentsLoaded", {"result": ["env"]}
    )
    assert AppEvent.details_diff_loaded(task_id, "Title", "diff") == AppEvent(
        "DetailsDiffLoaded", {"id": task_id, "title": "Title", "diff": "diff"}
    )
    assert AppEvent.details_messages_loaded(
        task_id,
        "Title",
        messages=["message"],
        prompt="prompt",
        turn_id="turn-1",
        sibling_turn_ids=["turn-2"],
        attempt_placement=2,
        attempt_status=AttemptStatus.COMPLETED,
    ) == AppEvent(
        "DetailsMessagesLoaded",
        {
            "id": task_id,
            "title": "Title",
            "messages": ["message"],
            "prompt": "prompt",
            "turn_id": "turn-1",
            "sibling_turn_ids": ["turn-2"],
            "attempt_placement": 2,
            "attempt_status": AttemptStatus.COMPLETED,
        },
    )
    assert AppEvent.details_failed(task_id, "Title", "boom") == AppEvent(
        "DetailsFailed", {"id": task_id, "title": "Title", "error": "boom"}
    )
    assert AppEvent.attempts_loaded(task_id, attempts) == AppEvent(
        "AttemptsLoaded", {"id": task_id, "attempts": attempts}
    )
    assert AppEvent.new_task_submitted(result="created") == AppEvent(
        "NewTaskSubmitted", {"result": "created"}
    )
    assert AppEvent.apply_preflight_finished(
        task_id,
        "Title",
        "ok",
        level="success",
        skipped=["skip.py"],
        conflicts=["conflict.py"],
    ) == AppEvent(
        "ApplyPreflightFinished",
        {
            "id": task_id,
            "title": "Title",
            "message": "ok",
            "level": "success",
            "skipped": ["skip.py"],
            "conflicts": ["conflict.py"],
        },
    )
    assert AppEvent.apply_finished(task_id, result=outcome) == AppEvent(
        "ApplyFinished", {"id": task_id, "result": outcome}
    )


def test_handle_app_event_dispatches_rust_match_arms_and_runtime_hooks():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent match dispatch.
    # Source contract: event kind dispatches to the same state transition branch and registers follow-up work hooks.
    app = App.new()
    app.env_filter = "env-A"
    logs: list[str] = []

    changed = handle_app_event(
        app,
        AppEvent.tasks_loaded("env-A", [make_task("T-A", "A-1", env="env-A")]),
        logger=logs.append,
    )

    assert changed is True
    assert [task.title for task in app.tasks] == ["A-1"]
    assert logs == ["refresh.apply: env=env-A count=1"]

    app.diff_overlay = DiffOverlay.new(TaskId("task-1"), "Title")
    attempts_loads: list[tuple[TaskId, str]] = []
    changed = handle_app_event(
        app,
        AppEvent.details_messages_loaded(
            TaskId("task-1"),
            "Title",
            messages=["assistant output"],
            prompt="prompt",
            turn_id="turn-1",
            sibling_turn_ids=["turn-2"],
            attempt_placement=1,
            attempt_status=AttemptStatus.COMPLETED,
        ),
        schedule_attempts_load=lambda task_id, turn_id: attempts_loads.append(
            (task_id, turn_id)
        ),
    )

    assert changed is True
    assert attempts_loads == [(TaskId("task-1"), "turn-1")]
    assert app.diff_overlay.attempt_total_hint == 2

    app.apply_modal = ApplyModalState(task_id=TaskId("task-1"), title="Apply")
    app.diff_overlay = DiffOverlay.new(TaskId("task-1"), "Title")
    refreshes: list[str | None] = []
    changed = handle_app_event(
        app,
        AppEvent.apply_finished(
            TaskId("task-1"),
            ApplyOutcome(applied=True, status=ApplyStatus.SUCCESS, message="Applied"),
        ),
        schedule_tasks_refresh=refreshes.append,
    )

    assert changed is True
    assert app.apply_modal is None
    assert app.diff_overlay is None
    assert refreshes == ["env-A"]


def test_handle_app_event_rejects_unknown_kind():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent match dispatch.
    # Source contract: Rust exhaustiveness means unregistered event kinds are invalid in Python.
    with pytest.raises(ValueError, match="unknown AppEvent kind"):
        handle_app_event(App.new(), AppEvent("Unknown", {}))


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


def test_handle_tasks_loaded_event_matches_rust_state_transition():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::TasksLoaded branch.
    app = App.new()
    app.env_filter = "env-A"
    app.refresh_inflight = True
    app.selected = 4
    logs: list[str] = []

    changed = handle_tasks_loaded_event(
        app,
        env="env-A",
        result=[make_task("T-A", "A-1", env="env-A")],
        logger=logs.append,
    )

    assert changed is True
    assert app.refresh_inflight is False
    assert [task.title for task in app.tasks] == ["A-1"]
    assert app.selected == 0
    assert app.status == "Loaded tasks"
    assert logs == ["refresh.apply: env=env-A count=1"]

    app.refresh_inflight = True
    changed = handle_tasks_loaded_event(
        app,
        env="env-B",
        result=[make_task("T-B", "B-1", env="env-B")],
        logger=logs.append,
    )

    assert changed is False
    assert app.refresh_inflight is True
    assert [task.title for task in app.tasks] == ["A-1"]
    assert logs[-1] == "refresh.drop: env=env-B current=env-A"

    changed = handle_tasks_loaded_event(
        app,
        env="env-A",
        result=RuntimeError("network down"),
        logger=logs.append,
    )

    assert changed is True
    assert app.refresh_inflight is False
    assert app.status == "Failed to load tasks: network down"
    assert logs[-1] == "refresh load_tasks failed: network down"


def test_environment_events_match_rust_state_transitions():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::{EnvironmentsLoaded,EnvironmentAutodetected} branches.
    app = App.new()
    app.env_loading = True
    now = object()

    changed = handle_environments_loaded_event(
        app,
        result=[EnvironmentRow(id="env-1", label="One", is_pinned=True)],
        now=now,
    )

    assert changed is True
    assert app.env_loading is False
    assert app.environments == [EnvironmentRow(id="env-1", label="One", is_pinned=True)]
    assert app.env_error is None
    assert app.env_last_loaded is now

    changed = handle_environments_loaded_event(app, result=RuntimeError("env down"))
    assert changed is True
    assert app.env_loading is False
    assert app.env_error == "env down"
    assert app.environments == [EnvironmentRow(id="env-1", label="One", is_pinned=True)]

    logs: list[str] = []
    refreshes: list[str | None] = []
    env_loads: list[str] = []
    app.env_filter = None
    app.in_flight = {"task-1"}

    changed = handle_environment_autodetected_event(
        app,
        result=AutodetectSelection(id="env-2", label="Two"),
        logger=logs.append,
        schedule_tasks_refresh=refreshes.append,
        schedule_environments_load=lambda: env_loads.append("load"),
    )

    assert changed is True
    assert app.env_filter == "env-2"
    assert app.status == "Loading tasks..."
    assert app.refresh_inflight is True
    assert app.list_generation == 1
    assert app.in_flight == set()
    assert app.env_loading is True
    assert refreshes == ["env-2"]
    assert env_loads == ["load"]
    assert logs == ["env.select: autodetected id=env-2 label=Two"]
    assert any(row.id == "env-2" and row.label == "Two" for row in app.environments)

    changed = handle_environment_autodetected_event(
        app,
        result=AutodetectSelection(id="env-2", label="Two"),
        logger=logs.append,
    )
    assert changed is False
    assert logs == ["env.select: autodetected id=env-2 label=Two"]

    changed = handle_environment_autodetected_event(app, result=RuntimeError("ignored"))
    assert changed is False


def test_new_task_submitted_event_matches_rust_state_transition():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::NewTaskSubmitted branch.
    app = App.new()
    app.env_filter = "env-1"
    app.new_task = object()
    logs: list[str] = []
    refreshes: list[str | None] = []

    changed = handle_new_task_submitted_event(
        app,
        result=CreatedTask(id=TaskId("task-1")),
        logger=logs.append,
        schedule_tasks_refresh=refreshes.append,
    )

    assert changed is True
    assert logs == ["new-task: created id=task-1"]
    assert app.status == "Submitted as task-1 - refreshing..."
    assert app.new_task is None
    assert app.refresh_inflight is True
    assert app.list_generation == 1
    assert refreshes == ["env-1"]

    page = type("Page", (), {"submitting": True})()
    app.new_task = page
    changed = handle_new_task_submitted_event(
        app,
        result="quota exceeded",
        logger=logs.append,
    )

    assert changed is True
    assert page.submitting is False
    assert app.status == "Submit failed: quota exceeded. See error.log for details."
    assert logs[-1] == "new-task: submit failed: quota exceeded"


def test_handle_apply_preflight_finished_event_updates_matching_modal_only():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::ApplyPreflightFinished branch.
    app = App.new()
    app.apply_preflight_inflight = True
    app.apply_modal = ApplyModalState(task_id=TaskId("task-1"), title="Old")

    changed = handle_apply_preflight_finished_event(
        app,
        id=TaskId("other"),
        title="Ignored",
        message="ignored",
        level="error",
        skipped=[],
        conflicts=[],
    )

    assert changed is False
    assert app.apply_preflight_inflight is True
    assert app.apply_modal.title == "Old"

    changed = handle_apply_preflight_finished_event(
        app,
        id=TaskId("task-1"),
        title="New",
        message="ready",
        level="success",
        skipped=["skip.py"],
        conflicts=["conflict.py"],
    )

    assert changed is True
    assert app.apply_preflight_inflight is False
    assert app.apply_modal.title == "New"
    assert app.apply_modal.result_message == "ready"
    assert app.apply_modal.result_level == "success"
    assert app.apply_modal.skipped_paths == ["skip.py"]
    assert app.apply_modal.conflict_paths == ["conflict.py"]


def test_apply_finished_event_matches_rust_state_transition():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::ApplyFinished branch.
    app = App.new()
    app.apply_inflight = True
    app.apply_modal = ApplyModalState(task_id=TaskId("task-1"), title="Apply")
    app.diff_overlay = DiffOverlay.new(TaskId("task-1"), "Title")
    refreshes: list[str | None] = []

    changed = handle_apply_finished_event(
        app,
        id=TaskId("other"),
        result=ApplyOutcome(applied=True, status=ApplyStatus.SUCCESS, message="done"),
        schedule_tasks_refresh=refreshes.append,
    )

    assert changed is False
    assert app.apply_inflight is True
    assert app.apply_modal is not None
    assert app.diff_overlay is not None

    changed = handle_apply_finished_event(
        app,
        id=TaskId("task-1"),
        result=ApplyOutcome(applied=True, status=ApplyStatus.SUCCESS, message="Applied"),
        schedule_tasks_refresh=refreshes.append,
    )

    assert changed is True
    assert app.apply_inflight is False
    assert app.status == "Applied"
    assert app.apply_modal is None
    assert app.diff_overlay is None
    assert refreshes == [None]

    logs: list[str] = []
    app.apply_inflight = True
    app.apply_modal = ApplyModalState(task_id=TaskId("task-2"), title="Apply")
    changed = handle_apply_finished_event(
        app,
        id=TaskId("task-2"),
        result="patch failed",
        logger=logs.append,
    )

    assert changed is True
    assert app.apply_inflight is False
    assert app.apply_modal is not None
    assert app.status == "Apply failed: patch failed"
    assert logs == ["apply_task failed for task-2: patch failed"]


def test_details_diff_loaded_event_updates_or_creates_overlay():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::DetailsDiffLoaded branch.
    app = App.new()
    app.details_inflight = True

    changed = handle_details_diff_loaded_event(
        app, id=TaskId("task-1"), title="Title", diff="+a\n-b"
    )

    assert changed is True
    assert app.details_inflight is False
    assert app.status == ""
    assert app.diff_overlay is not None
    assert app.diff_overlay.title == "Title"
    assert app.diff_overlay.current_view is DetailView.DIFF
    assert app.diff_overlay.base_can_apply is True
    assert app.diff_overlay.diff_lines == ["+a", "-b"]
    assert app.diff_overlay.base_attempt_mut().diff_raw == "+a\n-b"

    app.diff_overlay = DiffOverlay.new(TaskId("other"), "Other")
    changed = handle_details_diff_loaded_event(
        app, id=TaskId("task-1"), title="Ignored", diff="+ignored"
    )
    assert changed is False
    assert app.diff_overlay.title == "Other"


def test_details_messages_loaded_event_updates_prompt_attempt_fields():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::DetailsMessagesLoaded branch.
    app = App.new()
    app.details_inflight = True

    changed = handle_details_messages_loaded_event(
        app,
        id=TaskId("task-1"),
        title="Title",
        messages=["hello\nworld", "again"],
        prompt="do it",
        turn_id="turn-1",
        sibling_turn_ids=["turn-2", "turn-3"],
        attempt_placement=4,
        attempt_status=AttemptStatus.COMPLETED,
    )

    assert changed is True
    assert app.details_inflight is False
    assert app.status == ""
    assert app.diff_overlay is not None
    assert app.diff_overlay.current_view is DetailView.PROMPT
    assert app.diff_overlay.base_turn_id == "turn-1"
    assert app.diff_overlay.sibling_turn_ids == ["turn-2", "turn-3"]
    assert app.diff_overlay.attempt_total_hint == 3
    base = app.diff_overlay.base_attempt_mut()
    assert base.text_lines == [
        "user:",
        "do it",
        "",
        "assistant:",
        "hello",
        "world",
        "",
        "again",
    ]
    assert base.prompt == "do it"
    assert base.turn_id == "turn-1"
    assert base.attempt_placement == 4
    assert base.status is AttemptStatus.COMPLETED


def test_details_failed_event_sets_pretty_prompt_overlay_and_logs():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::DetailsFailed branch.
    app = App.new()
    app.details_inflight = True
    logs: list[str] = []
    raw = (
        'http failed body={"current_assistant_turn":'
        '{"error":{"code":"busy","message":"still running"},'
        '"turn_status":"in_progress","latest_event":{"text":"working"}}}'
    )

    changed = handle_details_failed_event(
        app,
        id=TaskId("task-1"),
        title="Title",
        error=raw,
        logger=logs.append,
    )

    assert changed is True
    assert app.details_inflight is False
    assert logs == [f"details failed for task-1: {raw}"]
    assert app.diff_overlay is not None
    assert app.diff_overlay.current_view is DetailView.PROMPT
    assert app.diff_overlay.base_can_apply is False
    assert app.diff_overlay.text_lines == [
        "Failed to load task details.",
        "Assistant error: busy: still running",
        "Status: in_progress",
        "Latest event: working",
        "This task may still be running. Press 'r' to refresh.",
        "",
    ]
    assert app.diff_overlay.base_attempt_mut().prompt is None


def test_conversation_and_pretty_error_source_contracts():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs::{conversation_lines,pretty_lines_from_error}.
    assert conversation_lines(None, []) == ["<no output>"]
    assert conversation_lines("p1\np2", ["m1", "m2\nm3"]) == [
        "user:",
        "p1",
        "p2",
        "",
        "assistant:",
        "m1",
        "",
        "m2",
        "m3",
    ]
    assert pretty_lines_from_error("No output_diff in response.") == [
        "No diff available for this task.",
        "No output_diff in response.",
    ]
    assert pretty_lines_from_error("No assistant text messages in response.") == [
        "No assistant messages found for this task.",
        "No assistant text messages in response.",
    ]


def test_attempts_loaded_event_dedupes_sorts_and_clamps_selection():
    # Rust crate/module: codex-cloud-tasks/src/lib.rs AppEvent::AttemptsLoaded branch.
    app = App.new()
    overlay = DiffOverlay.new(TaskId("task-1"), "Title")
    base = overlay.base_attempt_mut()
    base.turn_id = "base-turn"
    overlay.selected_attempt = 99
    app.diff_overlay = overlay

    changed = handle_attempts_loaded_event(
        app,
        id=TaskId("task-1"),
        attempts=[
            TurnAttempt(
                turn_id="turn-c",
                attempt_placement=None,
                created_at=None,
                status=AttemptStatus.FAILED,
                diff=None,
                messages=["no diff"],
            ),
            TurnAttempt(
                turn_id="turn-a",
                attempt_placement=2,
                created_at=None,
                status=AttemptStatus.COMPLETED,
                diff="+a\n+b",
                messages=["first"],
            ),
            TurnAttempt(
                turn_id="turn-b",
                attempt_placement=1,
                created_at=None,
                status=AttemptStatus.IN_PROGRESS,
                diff="+c",
                messages=["second"],
            ),
            TurnAttempt(
                turn_id="turn-a",
                attempt_placement=3,
                created_at=None,
                status=AttemptStatus.CANCELLED,
                diff="+ignored",
                messages=["ignored"],
            ),
        ],
    )

    assert changed is True
    assert [attempt.turn_id for attempt in overlay.attempts] == [
        "base-turn",
        "turn-b",
        "turn-a",
        "turn-c",
    ]
    assert overlay.selected_attempt == 3
    assert overlay.attempt_total_hint == 4
    assert overlay.current_attempt().turn_id == "turn-c"
    assert overlay.current_attempt().text_lines == ["assistant:", "no diff"]
    assert overlay.attempts[1].diff_lines == ["+c"]
    assert overlay.attempts[2].diff_raw == "+a\n+b"

    changed = handle_attempts_loaded_event(
        app,
        id=TaskId("other"),
        attempts=[],
    )
    assert changed is False


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
