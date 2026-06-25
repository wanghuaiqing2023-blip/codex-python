"""Port of Rust ``codex-cloud-tasks/src/app.rs`` state helpers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import json
from typing import Any

from pycodex.cloud_tasks.new_task import NewTaskPage
from pycodex.cloud_tasks.scrollable_diff import ScrollableDiff
from pycodex.cloud_tasks_client import AttemptStatus
from pycodex.cloud_tasks_client import TaskId
from pycodex.cloud_tasks_client import TaskSummary


@dataclass(frozen=True)
class EnvironmentRow:
    id: str
    label: str | None = None
    is_pinned: bool = False
    repo_hints: str | None = None


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


@dataclass(frozen=True)
class AppEvent:
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def tasks_loaded(cls, env: str | None, result: Any) -> "AppEvent":
        return cls("TasksLoaded", {"env": env, "result": result})

    @classmethod
    def environment_autodetected(cls, result: Any) -> "AppEvent":
        return cls("EnvironmentAutodetected", {"result": result})

    @classmethod
    def environments_loaded(cls, result: Any) -> "AppEvent":
        return cls("EnvironmentsLoaded", {"result": result})

    @classmethod
    def details_diff_loaded(
        cls, id: TaskId, title: str, diff: str
    ) -> "AppEvent":
        return cls("DetailsDiffLoaded", {"id": id, "title": title, "diff": diff})

    @classmethod
    def details_messages_loaded(
        cls,
        id: TaskId,
        title: str,
        messages: list[str],
        prompt: str | None,
        turn_id: str | None,
        sibling_turn_ids: list[str],
        attempt_placement: int | None,
        attempt_status: AttemptStatus,
    ) -> "AppEvent":
        return cls(
            "DetailsMessagesLoaded",
            {
                "id": id,
                "title": title,
                "messages": messages,
                "prompt": prompt,
                "turn_id": turn_id,
                "sibling_turn_ids": sibling_turn_ids,
                "attempt_placement": attempt_placement,
                "attempt_status": attempt_status,
            },
        )

    @classmethod
    def details_failed(cls, id: TaskId, title: str, error: str) -> "AppEvent":
        return cls("DetailsFailed", {"id": id, "title": title, "error": error})

    @classmethod
    def attempts_loaded(cls, id: TaskId, attempts: list[Any]) -> "AppEvent":
        return cls("AttemptsLoaded", {"id": id, "attempts": attempts})

    @classmethod
    def new_task_submitted(cls, result: Any) -> "AppEvent":
        return cls("NewTaskSubmitted", {"result": result})

    @classmethod
    def apply_preflight_finished(
        cls,
        id: TaskId,
        title: str,
        message: str,
        level: Any,
        skipped: list[str],
        conflicts: list[str],
    ) -> "AppEvent":
        return cls(
            "ApplyPreflightFinished",
            {
                "id": id,
                "title": title,
                "message": message,
                "level": level,
                "skipped": skipped,
                "conflicts": conflicts,
            },
        )

    @classmethod
    def apply_finished(cls, id: TaskId, result: Any) -> "AppEvent":
        return cls("ApplyFinished", {"id": id, "result": result})


def handle_tasks_loaded_event(
    app: App,
    *,
    env: str | None,
    result: Any,
    logger: Any | None = None,
) -> bool:
    log = logger or (lambda _message: None)
    current_env = app.env_filter
    if env != current_env:
        log(
            "refresh.drop: env={} current={}".format(
                env if env is not None else "<all>",
                current_env if current_env is not None else "<all>",
            )
        )
        return False

    app.refresh_inflight = False
    if isinstance(result, BaseException):
        log(f"refresh load_tasks failed: {result}")
        app.status = f"Failed to load tasks: {result}"
        return True

    tasks = list(result)
    log(
        "refresh.apply: env={} count={}".format(
            env if env is not None else "<all>",
            len(tasks),
        )
    )
    app.tasks = tasks
    if app.selected >= len(app.tasks):
        app.selected = max(len(app.tasks) - 1, 0)
    app.status = "Loaded tasks"
    return True


def handle_apply_preflight_finished_event(
    app: App,
    *,
    id: TaskId,
    title: str,
    message: str,
    level: Any,
    skipped: list[str],
    conflicts: list[str],
) -> bool:
    modal = app.apply_modal
    if modal is None or modal.task_id != id:
        return False
    modal.title = title
    modal.result_message = message
    modal.result_level = level
    modal.skipped_paths = list(skipped)
    modal.conflict_paths = list(conflicts)
    app.apply_preflight_inflight = False
    return True


def handle_environments_loaded_event(
    app: App,
    *,
    result: Any,
    now: Any | None = None,
) -> bool:
    app.env_loading = False
    if isinstance(result, BaseException):
        app.env_error = str(result)
        return True

    app.environments = list(result)
    app.env_error = None
    app.env_last_loaded = now
    return True


def handle_environment_autodetected_event(
    app: App,
    *,
    result: Any,
    logger: Any | None = None,
    schedule_tasks_refresh: Any | None = None,
    schedule_environments_load: Any | None = None,
) -> bool:
    if isinstance(result, BaseException):
        return False

    sel_id = str(_get_field(result, "id"))
    label = _get_field(result, "label")
    if app.env_filter == sel_id:
        return False

    log = logger or (lambda _message: None)
    log(
        "env.select: autodetected id={} label={}".format(
            sel_id, label if label is not None else "<none>"
        )
    )
    if label is not None and not any(
        _get_field(row, "id") == sel_id for row in app.environments
    ):
        app.environments.append(
            EnvironmentRow(
                id=sel_id,
                label=str(label),
                is_pinned=False,
                repo_hints=None,
            )
        )

    app.env_filter = sel_id
    app.status = "Loading tasks..."
    app.refresh_inflight = True
    app.list_generation += 1
    app.in_flight.clear()
    if schedule_tasks_refresh is not None:
        schedule_tasks_refresh(app.env_filter)

    app.env_loading = True
    if schedule_environments_load is not None:
        schedule_environments_load()
    return True


def handle_new_task_submitted_event(
    app: App,
    *,
    result: Any,
    logger: Any | None = None,
    schedule_tasks_refresh: Any | None = None,
) -> bool:
    log = logger or (lambda _message: None)
    if isinstance(result, BaseException) or isinstance(result, str):
        message = str(result)
        log(f"new-task: submit failed: {message}")
        if app.new_task is not None:
            app.new_task.submitting = False
        app.status = f"Submit failed: {message}. See error.log for details."
        return True

    task_id = _get_field(result, "id")
    task_id_text = str(_get_field(task_id, "0", task_id))
    log(f"new-task: created id={task_id_text}")
    app.status = f"Submitted as {task_id_text}"
    app.new_task = None
    app.status = f"Submitted as {task_id_text} - refreshing..."
    app.refresh_inflight = True
    app.list_generation += 1
    if schedule_tasks_refresh is not None:
        schedule_tasks_refresh(app.env_filter)
    return True


def handle_apply_finished_event(
    app: App,
    *,
    id: TaskId,
    result: Any,
    logger: Any | None = None,
    schedule_tasks_refresh: Any | None = None,
) -> bool:
    modal = app.apply_modal
    if modal is None or modal.task_id != id:
        return False

    app.apply_inflight = False
    if isinstance(result, BaseException) or isinstance(result, str):
        message = str(result)
        log = logger or (lambda _message: None)
        log(f"apply_task failed for {id}: {message}")
        app.status = f"Apply failed: {message}"
        return True

    app.status = str(_get_field(result, "message", ""))
    status = _get_field(result, "status", None)
    status_value = getattr(status, "value", status)
    if str(status_value).lower() == "success":
        app.apply_modal = None
        app.diff_overlay = None
        if schedule_tasks_refresh is not None:
            schedule_tasks_refresh(app.env_filter)
    return True


def handle_details_diff_loaded_event(
    app: App,
    *,
    id: TaskId,
    title: str,
    diff: str,
) -> bool:
    overlay = app.diff_overlay
    if overlay is not None and overlay.task_id != id:
        return False

    diff_lines = diff.splitlines()
    if overlay is None:
        overlay = DiffOverlay.new(id, title, None)
        overlay.current_view = DetailView.DIFF
        app.diff_overlay = overlay
    else:
        overlay.title = title

    base = overlay.base_attempt_mut()
    base.diff_lines = list(diff_lines)
    base.diff_raw = diff
    overlay.base_can_apply = True
    overlay.apply_selection_to_fields()
    app.details_inflight = False
    app.status = ""
    return True


def handle_details_messages_loaded_event(
    app: App,
    *,
    id: TaskId,
    title: str,
    messages: list[str],
    prompt: str | None,
    turn_id: str | None,
    sibling_turn_ids: list[str],
    attempt_placement: int | None,
    attempt_status: AttemptStatus,
    schedule_attempts_load: Any | None = None,
) -> bool:
    overlay = app.diff_overlay
    if overlay is not None and overlay.task_id != id:
        return False

    conv = conversation_lines(prompt, messages)
    should_schedule_attempts = (
        overlay is not None
        and turn_id is not None
        and bool(sibling_turn_ids)
        and len(overlay.attempts) == 1
    )
    if overlay is None:
        overlay = DiffOverlay.new(id, title, None)
        overlay.current_view = DetailView.PROMPT
        app.diff_overlay = overlay
    else:
        overlay.title = title

    base = overlay.base_attempt_mut()
    base.text_lines = list(conv)
    base.prompt = prompt
    base.turn_id = turn_id
    base.status = attempt_status
    base.attempt_placement = attempt_placement
    overlay.base_turn_id = turn_id
    overlay.sibling_turn_ids = list(sibling_turn_ids)
    overlay.attempt_total_hint = len(sibling_turn_ids) + 1
    if not overlay.base_can_apply:
        overlay.current_view = DetailView.PROMPT
    overlay.apply_selection_to_fields()
    if should_schedule_attempts and schedule_attempts_load is not None:
        schedule_attempts_load(id, turn_id)
    app.details_inflight = False
    app.status = ""
    return True


def handle_details_failed_event(
    app: App,
    *,
    id: TaskId,
    title: str,
    error: str,
    logger: Any | None = None,
) -> bool:
    overlay = app.diff_overlay
    if overlay is not None and overlay.task_id != id:
        return False

    log = logger or (lambda _message: None)
    log(f"details failed for {id}: {error}")
    pretty = pretty_lines_from_error(error)
    if overlay is None:
        overlay = DiffOverlay.new(id, title, None)
        app.diff_overlay = overlay
    else:
        overlay.title = title

    base = overlay.base_attempt_mut()
    base.diff_lines.clear()
    base.text_lines = list(pretty)
    base.prompt = None
    overlay.base_can_apply = False
    overlay.current_view = DetailView.PROMPT
    overlay.apply_selection_to_fields()
    app.details_inflight = False
    return True


def handle_attempts_loaded_event(
    app: App,
    *,
    id: TaskId,
    attempts: list[Any],
) -> bool:
    overlay = app.diff_overlay
    if overlay is None or overlay.task_id != id:
        return False

    existing_turn_ids = {
        attempt.turn_id for attempt in overlay.attempts if attempt.turn_id is not None
    }
    for attempt in attempts:
        turn_id = str(_get_field(attempt, "turn_id"))
        if turn_id in existing_turn_ids:
            continue
        diff_raw = _get_field(attempt, "diff")
        diff_lines = str(diff_raw).splitlines() if diff_raw is not None else []
        messages = list(_get_field(attempt, "messages", []) or [])
        overlay.attempts.append(
            AttemptView(
                turn_id=turn_id,
                status=_get_field(attempt, "status", AttemptStatus.UNKNOWN),
                attempt_placement=_get_field(attempt, "attempt_placement"),
                diff_lines=diff_lines,
                text_lines=conversation_lines(None, messages),
                prompt=None,
                diff_raw=diff_raw,
            )
        )
        existing_turn_ids.add(turn_id)

    if len(overlay.attempts) > 1:
        base = overlay.attempts[0]
        rest = sorted(overlay.attempts[1:], key=_attempt_sort_key)
        overlay.attempts = [base, *rest]
    if overlay.selected_attempt >= len(overlay.attempts):
        overlay.selected_attempt = max(len(overlay.attempts) - 1, 0)
    overlay.attempt_total_hint = len(overlay.attempts)
    overlay.apply_selection_to_fields()
    return True


def handle_app_event(
    app: App,
    event: AppEvent,
    *,
    logger: Any | None = None,
    now: Any | None = None,
    schedule_tasks_refresh: Any | None = None,
    schedule_environments_load: Any | None = None,
    schedule_attempts_load: Any | None = None,
) -> bool:
    payload = event.payload
    if event.kind == "TasksLoaded":
        return handle_tasks_loaded_event(
            app,
            env=payload.get("env"),
            result=payload.get("result"),
            logger=logger,
        )
    if event.kind == "NewTaskSubmitted":
        return handle_new_task_submitted_event(
            app,
            result=payload.get("result"),
            logger=logger,
            schedule_tasks_refresh=schedule_tasks_refresh,
        )
    if event.kind == "ApplyPreflightFinished":
        return handle_apply_preflight_finished_event(
            app,
            id=payload["id"],
            title=payload["title"],
            message=payload["message"],
            level=payload["level"],
            skipped=payload["skipped"],
            conflicts=payload["conflicts"],
        )
    if event.kind == "EnvironmentsLoaded":
        return handle_environments_loaded_event(
            app,
            result=payload.get("result"),
            now=now,
        )
    if event.kind == "EnvironmentAutodetected":
        return handle_environment_autodetected_event(
            app,
            result=payload.get("result"),
            logger=logger,
            schedule_tasks_refresh=schedule_tasks_refresh,
            schedule_environments_load=schedule_environments_load,
        )
    if event.kind == "DetailsDiffLoaded":
        return handle_details_diff_loaded_event(
            app,
            id=payload["id"],
            title=payload["title"],
            diff=payload["diff"],
        )
    if event.kind == "DetailsMessagesLoaded":
        return handle_details_messages_loaded_event(
            app,
            id=payload["id"],
            title=payload["title"],
            messages=payload["messages"],
            prompt=payload["prompt"],
            turn_id=payload["turn_id"],
            sibling_turn_ids=payload["sibling_turn_ids"],
            attempt_placement=payload["attempt_placement"],
            attempt_status=payload["attempt_status"],
            schedule_attempts_load=schedule_attempts_load,
        )
    if event.kind == "AttemptsLoaded":
        return handle_attempts_loaded_event(
            app,
            id=payload["id"],
            attempts=payload["attempts"],
        )
    if event.kind == "DetailsFailed":
        return handle_details_failed_event(
            app,
            id=payload["id"],
            title=payload["title"],
            error=payload["error"],
            logger=logger,
        )
    if event.kind == "ApplyFinished":
        return handle_apply_finished_event(
            app,
            id=payload["id"],
            result=payload["result"],
            logger=logger,
            schedule_tasks_refresh=schedule_tasks_refresh,
        )
    raise ValueError(f"unknown AppEvent kind: {event.kind}")


def conversation_lines(prompt: str | None, messages: list[str]) -> list[str]:
    lines: list[str] = []
    if prompt is not None:
        lines.append("user:")
        lines.extend(prompt.splitlines())
        lines.append("")
    if messages:
        lines.append("assistant:")
        for index, message in enumerate(messages):
            lines.extend(message.splitlines())
            if index + 1 < len(messages):
                lines.append("")
    if not lines:
        lines.append("<no output>")
    return lines


def _attempt_sort_key(attempt: "AttemptView") -> tuple[int, int | str]:
    if attempt.attempt_placement is not None:
        return (0, int(attempt.attempt_placement))
    return (1, attempt.turn_id or "")


def _get_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    if name == "0":
        return getattr(value, "value", default)
    return getattr(value, name, default)


def pretty_lines_from_error(raw: str) -> list[str]:
    lines: list[str] = []
    if "No output_diff in response." in raw:
        lines.append("No diff available for this task.")
    elif "No assistant text messages in response." in raw:
        lines.append("No assistant messages found for this task.")
    else:
        lines.append("Failed to load task details.")

    body_index = raw.find(" body=")
    if body_index != -1:
        json_index = raw.find("{", body_index)
        if json_index != -1:
            try:
                parsed = json.loads(raw[json_index:].strip())
            except Exception:
                parsed = None
            if isinstance(parsed, dict):
                turn = parsed.get("current_assistant_turn")
                if not isinstance(turn, dict):
                    turn = parsed.get("current_diff_task_turn")
                if isinstance(turn, dict):
                    error = turn.get("error")
                    if isinstance(error, dict):
                        code = str(error.get("code") or "")
                        message = str(error.get("message") or "")
                        if code or message:
                            summary = (
                                message
                                if not code
                                else code
                                if not message
                                else f"{code}: {message}"
                            )
                            lines.append(f"Assistant error: {summary}")
                    status = turn.get("turn_status")
                    if isinstance(status, str):
                        lines.append(f"Status: {status}")
                    latest_event = turn.get("latest_event")
                    if isinstance(latest_event, dict):
                        text = latest_event.get("text")
                        if isinstance(text, str) and text.strip():
                            lines.append(f"Latest event: {text.strip()}")

    if len(lines) == 1:
        tail = f"{raw[:320]}..." if len(raw) > 320 else raw
        lines.append(tail)
    elif len(lines) >= 2:
        if any("in_progress" in line for line in lines):
            lines.append("This task may still be running. Press 'r' to refresh.")
        lines.append("")
    return lines


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
    "AppEvent",
    "ApplyModalState",
    "AttemptView",
    "BestOfModalState",
    "DetailView",
    "DiffOverlay",
    "EnvModalState",
    "EnvironmentRow",
    "conversation_lines",
    "handle_app_event",
    "handle_apply_preflight_finished_event",
    "handle_apply_finished_event",
    "handle_attempts_loaded_event",
    "handle_environment_autodetected_event",
    "handle_environments_loaded_event",
    "handle_details_diff_loaded_event",
    "handle_details_failed_event",
    "handle_details_messages_loaded_event",
    "handle_new_task_submitted_event",
    "handle_tasks_loaded_event",
    "load_tasks",
    "pretty_lines_from_error",
]
