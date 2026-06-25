"""Pure helper projection for Rust ``codex-cloud-tasks/src/ui.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from typing import Iterable

from pycodex.cloud_tasks import format_relative_time
from pycodex.cloud_tasks.app import App, AttemptView, EnvironmentRow
from pycodex.cloud_tasks.scrollable_diff import ScrollableDiff
from pycodex.cloud_tasks_client import AttemptStatus, TaskStatus, TaskSummary


@dataclass(frozen=True)
class StyledSpan:
    text: str
    fg: str | None = None
    bold: bool = False
    dim: bool = False


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


Line = tuple[StyledSpan, ...]


class ConversationSpeaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


def span_text(line: Iterable[StyledSpan]) -> str:
    return "".join(span.text for span in line)


def rounded_enabled(env: dict[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get("CODEX_TUI_ROUNDED", "1") == "1"


def _percent_split(value: int, percentages: tuple[int, int, int]) -> tuple[int, int, int]:
    first = value * percentages[0] // 100
    second = value * percentages[1] // 100
    third = max(0, value - first - second)
    return first, second, third


def overlay_outer(area: Rect) -> Rect:
    top, middle_h, _bottom = _percent_split(area.height, (10, 80, 10))
    left, middle_w, _right = _percent_split(area.width, (10, 80, 10))
    return Rect(
        x=area.x + left,
        y=area.y + top,
        width=middle_w,
        height=middle_h,
    )


def overlay_content(area: Rect) -> Rect:
    return Rect(
        x=area.x + 3,
        y=area.y + 2,
        width=max(0, area.width - 6),
        height=max(0, area.height - 4),
    )


def spinner_dot(elapsed_ms: int) -> StyledSpan:
    blink_on = (max(0, elapsed_ms) // 600) % 2 == 0
    if blink_on:
        return StyledSpan("鈥?")
    return StyledSpan("鈼?", dim=True)


def inline_spinner_line(label: str, elapsed_ms: int = 0) -> Line:
    return (spinner_dot(elapsed_ms), StyledSpan(label, fg="cyan"))


def centered_spinner_area(area: Rect) -> Rect:
    width = min(18, max(0, area.width))
    height = 1 if area.height > 0 else 0
    return Rect(
        x=area.x + max(0, (area.width - width) // 2),
        y=area.y + max(0, (area.height - height) // 2),
        width=width,
        height=height,
    )


def filter_environment_rows(
    environments: Iterable[EnvironmentRow], query: str
) -> list[EnvironmentRow]:
    ql = query.lower()
    if not ql:
        return list(environments)

    filtered: list[EnvironmentRow] = []
    for env in environments:
        hay = ""
        if env.label is not None:
            hay += env.label.lower() + " "
        hay += env.id.lower()
        if env.repo_hints is not None:
            hay += " " + env.repo_hints.lower()
        if ql in hay:
            filtered.append(env)
    return filtered


def env_modal_selected_index(selected: int, filtered_count: int) -> int:
    return min(max(0, selected), max(0, filtered_count))


def render_environment_item(env: EnvironmentRow) -> Line:
    spans: list[StyledSpan] = [StyledSpan(env.label or "<unnamed>")]
    if env.is_pinned:
        spans.extend([StyledSpan("  "), StyledSpan("PINNED", fg="magenta", bold=True)])
    spans.extend([StyledSpan("  "), StyledSpan(env.id, dim=True)])
    if env.repo_hints is not None:
        spans.extend([StyledSpan("  "), StyledSpan(env.repo_hints, dim=True)])
    return tuple(spans)


def env_modal_item_lines(
    environments: Iterable[EnvironmentRow], query: str
) -> list[Line]:
    filtered = filter_environment_rows(environments, query)
    return [
        (StyledSpan("All Environments (Global)"),),
        *(render_environment_item(env) for env in filtered),
    ]


def best_of_modal_area(inner: Rect) -> Rect:
    modal_width = max(min(inner.width, 40), min(inner.width, 20))
    modal_height = max(min(inner.height, 12), min(inner.height, 6))
    return Rect(
        x=inner.x + max(0, inner.width - modal_width) // 2,
        y=inner.y + max(0, inner.height - modal_height) // 2,
        width=modal_width,
        height=modal_height,
    )


def best_of_selected_index(selected: int) -> int:
    return min(max(0, selected), 3)


def render_best_of_option(attempts: int, current_best_of_n: int) -> Line:
    noun = "attempt" if attempts == 1 else "attempts"
    spans: list[StyledSpan] = [
        StyledSpan(f"{attempts} {noun:<8}"),
        StyledSpan("  "),
        StyledSpan(f"{attempts}x parallel", dim=True),
    ]
    if attempts == current_best_of_n:
        spans.extend([StyledSpan("  "), StyledSpan("Current", fg="magenta", bold=True)])
    return tuple(spans)


def best_of_option_lines(current_best_of_n: int) -> list[Line]:
    return [render_best_of_option(attempts, current_best_of_n) for attempts in (1, 2, 3, 4)]


def footer_help_line(app: App) -> Line:
    spans: list[StyledSpan] = [
        StyledSpan("閳?閳?", dim=True),
        StyledSpan(": Move  ", dim=True),
        StyledSpan("r", dim=True),
        StyledSpan(": Refresh  ", dim=True),
        StyledSpan("Enter", dim=True),
        StyledSpan(": Open  ", dim=True),
    ]

    if app.diff_overlay is not None:
        if not app.diff_overlay.current_can_apply():
            spans.extend([StyledSpan("a", dim=True), StyledSpan(": Apply (disabled)  ", dim=True)])
        else:
            spans.extend([StyledSpan("a", dim=True), StyledSpan(": Apply  ", dim=True)])
        if app.diff_overlay.attempt_count() > 1:
            spans.extend(
                [
                    StyledSpan("Tab", dim=True),
                    StyledSpan(": Next attempt  ", dim=True),
                    StyledSpan("[ ]", dim=True),
                    StyledSpan(": Cycle attempts  ", dim=True),
                ]
            )
    else:
        spans.extend([StyledSpan("a", dim=True), StyledSpan(": Apply  ", dim=True)])

    spans.append(StyledSpan("o : Set Env  ", dim=True))
    if app.new_task is not None:
        spans.extend(
            [
                StyledSpan("Ctrl+N", dim=True),
                StyledSpan(f": Attempts {app.best_of_n}x  ", dim=True),
                StyledSpan("(editing new task)  ", dim=True),
            ]
        )
    else:
        spans.append(StyledSpan("n : New Task  ", dim=True))
    spans.extend([StyledSpan("q", dim=True), StyledSpan(": Quit  ", dim=True)])
    return tuple(spans)


def footer_spinner_visible(app: App) -> bool:
    return bool(
        app.refresh_inflight
        or app.details_inflight
        or app.env_loading
        or app.apply_preflight_inflight
        or app.apply_inflight
    )


def footer_status_line(status: str) -> str:
    status_line = status.replace("\n", " ")
    if len(status_line) > 2000:
        status_line = status_line[:2000] + "鈥?"
    return status_line


def new_task_title_line(app: App) -> Line:
    spans: list[StyledSpan] = [StyledSpan("New Task", fg="magenta", bold=True)]
    page = app.new_task
    if page is not None and page.env_id is not None:
        spans.append(StyledSpan("  鈥?"))
        env_label = page.env_id
        for env in app.environments:
            if getattr(env, "id", None) == page.env_id:
                env_label = getattr(env, "label", None) or page.env_id
                break
        spans.append(StyledSpan(env_label, dim=True))
    else:
        spans.append(StyledSpan("  鈥?"))
        spans.append(StyledSpan("Env: none (press ctrl-o to choose)", fg="red"))

    if page is not None:
        spans.append(StyledSpan("  鈥?"))
        attempts = page.best_of_n
        suffix = "" if attempts == 1 else "s"
        spans.append(StyledSpan(f"{attempts} attempt{suffix}", fg="cyan"))
    return tuple(spans)


def new_task_content_area(area: Rect) -> Rect:
    return Rect(
        x=area.x + 1,
        y=area.y + 1,
        width=max(0, area.width - 2),
        height=max(0, area.height - 2),
    )


def new_task_composer_desired_height(app: App, content_width: int, terminal_height: int) -> int:
    max_allowed = max(max(0, terminal_height - 6), 3)
    page = app.new_task
    desired = page.composer.desired_height(content_width) if page is not None else 3
    return min(max(int(desired), 3), max_allowed)


def new_task_composer_area(content: Rect, desired_height: int) -> Rect:
    height = min(max(0, desired_height), max(0, content.height))
    return Rect(
        x=content.x,
        y=content.y + max(0, content.height - height),
        width=content.width,
        height=height,
    )


def task_list_dimmed(app: App) -> bool:
    return bool(
        app.env_modal is not None
        or app.apply_modal is not None
        or app.best_of_modal is not None
        or app.diff_overlay is not None
    )


def task_list_env_suffix(app: App) -> StyledSpan:
    if app.env_filter is None:
        return StyledSpan(" 鈥?All", dim=True)
    label = "Selected"
    for env in app.environments:
        if getattr(env, "id", None) == app.env_filter:
            label = getattr(env, "label", None) or "Selected"
            break
    return StyledSpan(f" 鈥?{label}", dim=True)


def task_list_percent_span(task_count: int, selected: int) -> StyledSpan:
    if task_count <= 1:
        return StyledSpan("  鈥?0%", dim=True)
    percent = round((selected / (task_count - 1)) * 100)
    percent = min(max(int(percent), 0), 100)
    return StyledSpan(f"  鈥?{percent}%", dim=True)


def task_list_title_line(app: App) -> Line:
    dim = task_list_dimmed(app)
    return (
        StyledSpan("Cloud Tasks", dim=dim),
        StyledSpan(task_list_env_suffix(app).text, dim=True),
        StyledSpan(task_list_percent_span(len(app.tasks), app.selected).text, dim=True),
    )


def task_list_inner_area(area: Rect) -> Rect:
    return Rect(
        x=area.x + 1,
        y=area.y + 1,
        width=max(0, area.width - 2),
        height=max(0, area.height - 2),
    )


def task_list_rows_area(inner: Rect) -> Rect:
    return Rect(
        x=inner.x,
        y=inner.y + min(1, max(0, inner.height)),
        width=inner.width,
        height=max(0, inner.height - 1),
    )


def attempt_status_span(status: AttemptStatus) -> StyledSpan | None:
    if status is AttemptStatus.COMPLETED:
        return StyledSpan("Completed", fg="green")
    if status is AttemptStatus.FAILED:
        return StyledSpan("Failed", fg="red", bold=True)
    if status is AttemptStatus.IN_PROGRESS:
        return StyledSpan("In progress", fg="magenta")
    if status is AttemptStatus.PENDING:
        return StyledSpan("Pending", fg="cyan")
    if status is AttemptStatus.CANCELLED:
        return StyledSpan("Cancelled", dim=True)
    return None


def style_diff_line(raw: str) -> Line:
    if raw.startswith("@@"):
        return (StyledSpan(raw, fg="magenta", bold=True),)
    if raw.startswith("+++") or raw.startswith("---"):
        return (StyledSpan(raw, dim=True),)
    if raw.startswith("+"):
        return (StyledSpan(raw, fg="green"),)
    if raw.startswith("-"):
        return (StyledSpan(raw, fg="red"),)
    return (StyledSpan(raw),)


def conversation_header_line(
    speaker: ConversationSpeaker, attempt: AttemptView | None = None
) -> Line:
    spans = [StyledSpan("╭ ", dim=True)]
    if speaker is ConversationSpeaker.USER:
        spans.extend([StyledSpan("User", fg="cyan", bold=True), StyledSpan(" prompt", dim=True)])
    else:
        spans.extend(
            [StyledSpan("Assistant", fg="magenta", bold=True), StyledSpan(" response", dim=True)]
        )
        if attempt is not None:
            status = attempt_status_span(attempt.status)
            if status is not None:
                spans.extend([StyledSpan("  • ", dim=True), status])
    return tuple(spans)


def conversation_gutter_span(speaker: ConversationSpeaker) -> StyledSpan:
    if speaker is ConversationSpeaker.USER:
        return StyledSpan("│ ", fg="cyan", dim=True)
    return StyledSpan("│ ", fg="magenta", dim=True)


def conversation_text_spans(
    display: str,
    in_code: bool,
    is_new_raw: bool,
    bullet_indent: int | None,
) -> Line:
    if in_code:
        return (StyledSpan(display, fg="cyan"),)

    trimmed = display.lstrip()
    if bullet_indent is not None:
        if is_new_raw:
            rest = trimmed[2:].lstrip() if len(trimmed) >= 2 else ""
            spans: list[StyledSpan] = []
            if bullet_indent > 0:
                spans.append(StyledSpan(" " * bullet_indent))
            spans.extend([StyledSpan("•"), StyledSpan(rest)])
            return tuple(spans)
        return (StyledSpan(" " * (bullet_indent + 2) + trimmed),)

    if is_new_raw and (
        trimmed.startswith("### ") or trimmed.startswith("## ") or trimmed.startswith("# ")
    ):
        return (StyledSpan(display, fg="magenta", bold=True),)
    return (StyledSpan(display),)


def style_conversation_lines(sd: ScrollableDiff, attempt: AttemptView | None = None) -> list[Line]:
    wrapped = sd.wrapped_lines()
    if not wrapped:
        return []

    indices = sd.wrapped_src_indices()
    styled: list[Line] = []
    speaker: ConversationSpeaker | None = None
    in_code = False
    last_src: int | None = None
    bullet_indent: int | None = None

    for display, src_idx in zip(wrapped, indices):
        raw = sd.raw_line_at(src_idx)
        trimmed = raw.strip()
        is_new_raw = last_src is None or last_src != src_idx

        if trimmed.lower() == "user:":
            speaker = ConversationSpeaker.USER
            in_code = False
            bullet_indent = None
            styled.append(conversation_header_line(ConversationSpeaker.USER))
            last_src = src_idx
            continue
        if trimmed.lower() == "assistant:":
            speaker = ConversationSpeaker.ASSISTANT
            in_code = False
            bullet_indent = None
            styled.append(conversation_header_line(ConversationSpeaker.ASSISTANT, attempt))
            last_src = src_idx
            continue

        if raw == "":
            styled.append((conversation_gutter_span(speaker),) if speaker is not None else (StyledSpan(""),))
            last_src = src_idx
            bullet_indent = None
            continue

        if is_new_raw:
            trimmed_start = raw.lstrip()
            if trimmed_start.startswith("```"):
                in_code = not in_code
                bullet_indent = None
            elif not in_code and (trimmed_start.startswith("- ") or trimmed_start.startswith("* ")):
                bullet_indent = len(raw) - len(trimmed_start)
            elif not in_code:
                bullet_indent = None

        spans: list[StyledSpan] = []
        if speaker is not None:
            spans.append(conversation_gutter_span(speaker))
        spans.extend(conversation_text_spans(display, in_code, is_new_raw, bullet_indent))
        styled.append(tuple(spans))
        last_src = src_idx

    return styled or [(StyledSpan(line),) for line in wrapped]


def render_task_item(app: App, task: TaskSummary, *, now=None) -> list[Line]:
    del app
    status_style = {
        TaskStatus.READY: ("READY", "green"),
        TaskStatus.PENDING: ("PENDING", "magenta"),
        TaskStatus.APPLIED: ("APPLIED", "blue"),
        TaskStatus.ERROR: ("ERROR", "red"),
    }[task.status]
    title = (
        StyledSpan("["),
        StyledSpan(status_style[0], fg=status_style[1]),
        StyledSpan("] "),
        StyledSpan(task.title),
    )

    meta: list[StyledSpan] = []
    if task.environment_label:
        meta.append(StyledSpan(task.environment_label, dim=True))
    when = format_relative_time(now or task.updated_at, task.updated_at)
    if meta:
        meta.extend([StyledSpan("  "), StyledSpan("•", dim=True), StyledSpan("  ")])
    meta.append(StyledSpan(when, dim=True))

    summary = task.summary
    if summary.files_changed > 0 or summary.lines_added > 0 or summary.lines_removed > 0:
        sub = (
            StyledSpan(f"+{summary.lines_added}", fg="green"),
            StyledSpan("/"),
            StyledSpan(f"−{summary.lines_removed}", fg="red"),
            StyledSpan(" "),
            StyledSpan("•", dim=True),
            StyledSpan(" "),
            StyledSpan(str(summary.files_changed)),
            StyledSpan(" "),
            StyledSpan("files", dim=True),
        )
    else:
        sub = (StyledSpan("no diff", dim=True),)
    return [title, tuple(meta), sub, (StyledSpan(""),)]


__all__ = [
    "ConversationSpeaker",
    "Line",
    "Rect",
    "StyledSpan",
    "attempt_status_span",
    "best_of_modal_area",
    "best_of_option_lines",
    "best_of_selected_index",
    "centered_spinner_area",
    "conversation_gutter_span",
    "conversation_header_line",
    "conversation_text_spans",
    "env_modal_item_lines",
    "env_modal_selected_index",
    "filter_environment_rows",
    "footer_help_line",
    "footer_spinner_visible",
    "footer_status_line",
    "inline_spinner_line",
    "new_task_composer_area",
    "new_task_composer_desired_height",
    "new_task_content_area",
    "new_task_title_line",
    "overlay_content",
    "overlay_outer",
    "render_best_of_option",
    "render_environment_item",
    "render_task_item",
    "rounded_enabled",
    "span_text",
    "spinner_dot",
    "style_conversation_lines",
    "style_diff_line",
    "task_list_dimmed",
    "task_list_env_suffix",
    "task_list_inner_area",
    "task_list_percent_span",
    "task_list_rows_area",
    "task_list_title_line",
]
