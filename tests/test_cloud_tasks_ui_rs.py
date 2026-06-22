from datetime import datetime, timezone

from pycodex.cloud_tasks import App, AttemptView, ScrollableDiff
from pycodex.cloud_tasks.ui import (
    ConversationSpeaker,
    StyledSpan,
    attempt_status_span,
    conversation_gutter_span,
    conversation_header_line,
    conversation_text_spans,
    render_task_item,
    span_text,
    style_conversation_lines,
    style_diff_line,
)
from pycodex.cloud_tasks_client import (
    AttemptStatus,
    DiffSummary,
    TaskId,
    TaskStatus,
    TaskSummary,
)


def line_texts(lines):
    return [span_text(line) for line in lines]


def test_attempt_status_span_matches_rust_status_labels_and_styles():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::attempt_status_span.
    assert attempt_status_span(AttemptStatus.COMPLETED) == StyledSpan("Completed", fg="green")
    assert attempt_status_span(AttemptStatus.FAILED) == StyledSpan(
        "Failed", fg="red", bold=True
    )
    assert attempt_status_span(AttemptStatus.IN_PROGRESS) == StyledSpan(
        "In progress", fg="magenta"
    )
    assert attempt_status_span(AttemptStatus.PENDING) == StyledSpan("Pending", fg="cyan")
    assert attempt_status_span(AttemptStatus.CANCELLED) == StyledSpan("Cancelled", dim=True)
    assert attempt_status_span(AttemptStatus.UNKNOWN) is None


def test_style_diff_line_classifies_diff_prefixes():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::style_diff_line.
    assert style_diff_line("@@ -1 +1 @@") == (
        StyledSpan("@@ -1 +1 @@", fg="magenta", bold=True),
    )
    assert style_diff_line("+++ b/file") == (StyledSpan("+++ b/file", dim=True),)
    assert style_diff_line("--- a/file") == (StyledSpan("--- a/file", dim=True),)
    assert style_diff_line("+added") == (StyledSpan("+added", fg="green"),)
    assert style_diff_line("-removed") == (StyledSpan("-removed", fg="red"),)
    assert style_diff_line(" context") == (StyledSpan(" context"),)


def test_conversation_header_gutter_and_text_spans_contracts():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs conversation helper functions.
    attempt = AttemptView(status=AttemptStatus.FAILED)
    assert span_text(conversation_header_line(ConversationSpeaker.USER)) == "╭ User prompt"
    assistant = conversation_header_line(ConversationSpeaker.ASSISTANT, attempt)
    assert span_text(assistant) == "╭ Assistant response  • Failed"
    assert assistant[-1] == StyledSpan("Failed", fg="red", bold=True)
    assert conversation_gutter_span(ConversationSpeaker.USER) == StyledSpan(
        "│ ", fg="cyan", dim=True
    )
    assert conversation_gutter_span(ConversationSpeaker.ASSISTANT) == StyledSpan(
        "│ ", fg="magenta", dim=True
    )

    assert conversation_text_spans("code", True, True, None) == (
        StyledSpan("code", fg="cyan"),
    )
    assert conversation_text_spans("  - item", False, True, 2) == (
        StyledSpan("  "),
        StyledSpan("•"),
        StyledSpan("item"),
    )
    assert conversation_text_spans("wrapped", False, False, 2) == (
        StyledSpan("    wrapped"),
    )
    assert conversation_text_spans("# Heading", False, True, None) == (
        StyledSpan("# Heading", fg="magenta", bold=True),
    )


def test_style_conversation_lines_tracks_roles_code_bullets_and_wrapped_indices():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::style_conversation_lines.
    sd = ScrollableDiff.new()
    sd.set_content(
        [
            "user:",
            "hello",
            "",
            "assistant:",
            "```",
            "let x = 1;",
            "```",
            "  - first wrapped words",
        ]
    )
    sd.set_width(12)
    attempt = AttemptView(status=AttemptStatus.IN_PROGRESS)

    lines = style_conversation_lines(sd, attempt)
    assert line_texts(lines) == [
        "╭ User prompt",
        "│ hello",
        "│ ",
        "╭ Assistant response  • In progress",
        "│ ```",
        "│ let x = 1;",
        "│ ```",
        "│   •first",
        "│     wrapped",
        "│     words",
    ]
    assert lines[5][1] == StyledSpan("let x = 1;", fg="cyan")


def test_render_task_item_projects_status_meta_summary_and_spacer():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::render_task_item.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    task = TaskSummary(
        id=TaskId("task-1"),
        title="Example",
        status=TaskStatus.READY,
        updated_at=now,
        environment_id="env-1",
        environment_label="Env",
        summary=DiffSummary(files_changed=3, lines_added=5, lines_removed=2),
    )

    item = render_task_item(App.new(), task, now=now)
    assert line_texts(item) == [
        "[READY] Example",
        "Env  •  0s ago",
        "+5/−2 • 3 files",
        "",
    ]
    assert item[0][1] == StyledSpan("READY", fg="green")
    assert item[2][0] == StyledSpan("+5", fg="green")
    assert item[2][2] == StyledSpan("−2", fg="red")

    no_diff = render_task_item(
        App.new(),
        TaskSummary(
            id=TaskId("task-2"),
            title="No Diff",
            status=TaskStatus.PENDING,
            updated_at=now,
            environment_id=None,
            environment_label="",
            summary=DiffSummary(),
        ),
        now=now,
    )
    assert line_texts(no_diff) == ["[PENDING] No Diff", "0s ago", "no diff", ""]
    assert no_diff[0][1] == StyledSpan("PENDING", fg="magenta")
