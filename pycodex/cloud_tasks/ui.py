"""Pure helper projection for Rust ``codex-cloud-tasks/src/ui.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from pycodex.cloud_tasks import format_relative_time
from pycodex.cloud_tasks.app import App, AttemptView
from pycodex.cloud_tasks.scrollable_diff import ScrollableDiff
from pycodex.cloud_tasks_client import AttemptStatus, TaskStatus, TaskSummary


@dataclass(frozen=True)
class StyledSpan:
    text: str
    fg: str | None = None
    bold: bool = False
    dim: bool = False


Line = tuple[StyledSpan, ...]


class ConversationSpeaker(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


def span_text(line: Iterable[StyledSpan]) -> str:
    return "".join(span.text for span in line)


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
    "StyledSpan",
    "attempt_status_span",
    "conversation_gutter_span",
    "conversation_header_line",
    "conversation_text_spans",
    "render_task_item",
    "span_text",
    "style_conversation_lines",
    "style_diff_line",
]
