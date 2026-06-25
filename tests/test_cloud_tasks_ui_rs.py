from datetime import datetime, timezone

from pycodex.cloud_tasks import App, AttemptView, NewTaskPage, ScrollableDiff
from pycodex.cloud_tasks.app import DetailView, DiffOverlay, EnvironmentRow
from pycodex.cloud_tasks.ui import (
    ConversationSpeaker,
    Rect,
    StyledSpan,
    attempt_status_span,
    best_of_modal_area,
    best_of_option_lines,
    best_of_selected_index,
    centered_spinner_area,
    conversation_gutter_span,
    conversation_header_line,
    conversation_text_spans,
    env_modal_item_lines,
    env_modal_selected_index,
    filter_environment_rows,
    footer_help_line,
    footer_spinner_visible,
    footer_status_line,
    inline_spinner_line,
    new_task_composer_area,
    new_task_composer_desired_height,
    new_task_content_area,
    new_task_title_line,
    overlay_content,
    overlay_outer,
    render_best_of_option,
    render_environment_item,
    render_task_item,
    rounded_enabled,
    span_text,
    spinner_dot,
    style_conversation_lines,
    style_diff_line,
    task_list_dimmed,
    task_list_env_suffix,
    task_list_inner_area,
    task_list_percent_span,
    task_list_rows_area,
    task_list_title_line,
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


def test_overlay_helpers_match_rust_layout_and_env_contract():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::rounded_enabled,
    # overlay_outer, and overlay_content.
    assert rounded_enabled({}) is True
    assert rounded_enabled({"CODEX_TUI_ROUNDED": "1"}) is True
    assert rounded_enabled({"CODEX_TUI_ROUNDED": "0"}) is False
    assert rounded_enabled({"CODEX_TUI_ROUNDED": "true"}) is False

    outer = overlay_outer(Rect(x=5, y=7, width=100, height=50))
    assert outer == Rect(x=15, y=12, width=80, height=40)

    # overlay_block uses borders plus Padding::new(2, 2, 1, 1), so content
    # starts after 1 border + left/top padding and shrinks by both sides.
    assert overlay_content(outer) == Rect(x=18, y=14, width=74, height=36)
    assert overlay_content(Rect(x=0, y=0, width=4, height=3)) == Rect(
        x=3, y=2, width=0, height=0
    )


def test_spinner_helpers_match_rust_blink_and_center_contract():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::draw_inline_spinner
    # and draw_centered_spinner.
    assert spinner_dot(0) == StyledSpan("鈥?")
    assert spinner_dot(599) == StyledSpan("鈥?")
    assert spinner_dot(600) == StyledSpan("鈼?", dim=True)
    assert spinner_dot(1199) == StyledSpan("鈼?", dim=True)
    assert spinner_dot(1200) == StyledSpan("鈥?")
    assert spinner_dot(-1) == StyledSpan("鈥?")

    assert inline_spinner_line("Loading…", 600) == (
        StyledSpan("鈼?", dim=True),
        StyledSpan("Loading…", fg="cyan"),
    )
    assert centered_spinner_area(Rect(x=2, y=3, width=100, height=11)) == Rect(
        x=43, y=8, width=18, height=1
    )
    assert centered_spinner_area(Rect(x=2, y=3, width=8, height=0)) == Rect(
        x=2, y=3, width=8, height=0
    )


def test_environment_modal_helpers_match_rust_filter_and_item_contract():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::draw_env_modal.
    envs = [
        EnvironmentRow(id="env-a", label="Alpha", is_pinned=True, repo_hints="openai/codex"),
        EnvironmentRow(id="env-b", label=None, repo_hints="other/repo"),
        EnvironmentRow(id="prod-east", label="Production", repo_hints=None),
    ]

    assert filter_environment_rows(envs, "") == envs
    assert filter_environment_rows(envs, "ALP") == [envs[0]]
    assert filter_environment_rows(envs, "env-b") == [envs[1]]
    assert filter_environment_rows(envs, "CODEX") == [envs[0]]
    assert filter_environment_rows(envs, "missing") == []

    assert env_modal_selected_index(0, 0) == 0
    assert env_modal_selected_index(3, 2) == 2
    assert env_modal_selected_index(-1, 2) == 0

    assert render_environment_item(envs[0]) == (
        StyledSpan("Alpha"),
        StyledSpan("  "),
        StyledSpan("PINNED", fg="magenta", bold=True),
        StyledSpan("  "),
        StyledSpan("env-a", dim=True),
        StyledSpan("  "),
        StyledSpan("openai/codex", dim=True),
    )
    assert render_environment_item(envs[1]) == (
        StyledSpan("<unnamed>"),
        StyledSpan("  "),
        StyledSpan("env-b", dim=True),
        StyledSpan("  "),
        StyledSpan("other/repo", dim=True),
    )

    assert line_texts(env_modal_item_lines(envs, "prod")) == [
        "All Environments (Global)",
        "Production  prod-east",
    ]


def test_best_of_modal_helpers_match_rust_layout_and_option_contract():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::draw_best_of_modal.
    assert best_of_modal_area(Rect(x=10, y=20, width=100, height=40)) == Rect(
        x=40, y=34, width=40, height=12
    )
    assert best_of_modal_area(Rect(x=10, y=20, width=30, height=8)) == Rect(
        x=10, y=20, width=30, height=8
    )
    assert best_of_modal_area(Rect(x=10, y=20, width=12, height=4)) == Rect(
        x=10, y=20, width=12, height=4
    )

    assert best_of_selected_index(0) == 0
    assert best_of_selected_index(3) == 3
    assert best_of_selected_index(7) == 3
    assert best_of_selected_index(-2) == 0

    assert render_best_of_option(1, 2) == (
        StyledSpan("1 attempt "),
        StyledSpan("  "),
        StyledSpan("1x parallel", dim=True),
    )
    assert render_best_of_option(2, 2) == (
        StyledSpan("2 attempts"),
        StyledSpan("  "),
        StyledSpan("2x parallel", dim=True),
        StyledSpan("  "),
        StyledSpan("Current", fg="magenta", bold=True),
    )
    assert line_texts(best_of_option_lines(4)) == [
        "1 attempt   1x parallel",
        "2 attempts  2x parallel",
        "3 attempts  3x parallel",
        "4 attempts  4x parallel  Current",
    ]


def test_footer_helpers_match_rust_help_spinner_and_status_contract():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::draw_footer.
    app = App.new()
    assert span_text(footer_help_line(app)) == (
        "閳?閳?: Move  r: Refresh  Enter: Open  a: Apply  "
        "o : Set Env  n : New Task  q: Quit  "
    )
    assert all(span.dim for span in footer_help_line(app))
    assert footer_spinner_visible(app) is False

    disabled = DiffOverlay.new(TaskId("task-1"), "Task")
    app.diff_overlay = disabled
    assert "a: Apply (disabled)" in span_text(footer_help_line(app))

    enabled = DiffOverlay.new(TaskId("task-2"), "Task")
    enabled.current_view = DetailView.DIFF
    enabled.attempts = [
        AttemptView(diff_raw="diff --git a/a b/a"),
        AttemptView(diff_raw="diff --git a/b b/b"),
    ]
    app.diff_overlay = enabled
    assert span_text(footer_help_line(app)) == (
        "閳?閳?: Move  r: Refresh  Enter: Open  a: Apply  "
        "Tab: Next attempt  [ ]: Cycle attempts  "
        "o : Set Env  n : New Task  q: Quit  "
    )

    app.new_task = object()
    app.best_of_n = 3
    assert "Ctrl+N: Attempts 3x  (editing new task)" in span_text(footer_help_line(app))

    app.refresh_inflight = True
    assert footer_spinner_visible(app) is True
    app.refresh_inflight = False
    app.apply_inflight = True
    assert footer_spinner_visible(app) is True

    assert footer_status_line("one\ntwo") == "one two"
    long_status = "x" * 2001
    assert footer_status_line(long_status) == ("x" * 2000) + "鈥?"


def test_new_task_page_helpers_match_rust_title_and_composer_layout_contract():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::draw_new_task_page.
    app = App.new()
    app.environments = [
        EnvironmentRow(id="env-1", label="Production", is_pinned=True),
        EnvironmentRow(id="env-2", label=None),
    ]

    assert new_task_title_line(app) == (
        StyledSpan("New Task", fg="magenta", bold=True),
        StyledSpan("  鈥?"),
        StyledSpan("Env: none (press ctrl-o to choose)", fg="red"),
    )

    app.new_task = NewTaskPage.new("env-1", 1)
    assert new_task_title_line(app) == (
        StyledSpan("New Task", fg="magenta", bold=True),
        StyledSpan("  鈥?"),
        StyledSpan("Production", dim=True),
        StyledSpan("  鈥?"),
        StyledSpan("1 attempt", fg="cyan"),
    )

    app.new_task = NewTaskPage.new("missing-env", 4)
    assert span_text(new_task_title_line(app)) == "New Task  鈥?missing-env  鈥?4 attempts"

    area = Rect(x=10, y=20, width=80, height=20)
    content = new_task_content_area(area)
    assert content == Rect(x=11, y=21, width=78, height=18)
    assert new_task_content_area(Rect(x=0, y=0, width=1, height=1)) == Rect(
        x=1, y=1, width=0, height=0
    )

    app.new_task.composer.text = "x" * 200
    desired = new_task_composer_desired_height(app, content_width=20, terminal_height=14)
    assert desired == 8
    assert new_task_composer_desired_height(app, content_width=20, terminal_height=4) == 3
    assert new_task_composer_area(content, desired) == Rect(x=11, y=31, width=78, height=8)
    assert new_task_composer_area(Rect(x=1, y=2, width=5, height=2), 5) == Rect(
        x=1, y=2, width=5, height=2
    )


def test_task_list_helpers_match_rust_title_and_layout_contract():
    # Rust crate/module: codex-cloud-tasks/src/ui.rs::draw_list.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    app = App.new()
    app.tasks = [
        TaskSummary(
            id=TaskId("task-1"),
            title="First",
            status=TaskStatus.READY,
            updated_at=now,
            environment_id="env-1",
            environment_label="Production",
            summary=DiffSummary(),
        ),
        TaskSummary(
            id=TaskId("task-2"),
            title="Second",
            status=TaskStatus.PENDING,
            updated_at=now,
            environment_id=None,
            environment_label="",
            summary=DiffSummary(),
        ),
        TaskSummary(
            id=TaskId("task-3"),
            title="Third",
            status=TaskStatus.ERROR,
            updated_at=now,
            environment_id=None,
            environment_label="",
            summary=DiffSummary(),
        ),
    ]
    app.selected = 1

    assert task_list_dimmed(app) is False
    assert task_list_env_suffix(app) == StyledSpan(" \u9225?All", dim=True)
    assert task_list_percent_span(len(app.tasks), app.selected) == StyledSpan(
        "  \u9225?50%", dim=True
    )
    assert task_list_title_line(app) == (
        StyledSpan("Cloud Tasks", dim=False),
        StyledSpan(" \u9225?All", dim=True),
        StyledSpan("  \u9225?50%", dim=True),
    )

    app.environments = [
        EnvironmentRow(id="env-1", label="Production", is_pinned=True),
        EnvironmentRow(id="env-2", label=None),
    ]
    app.env_filter = "env-1"
    assert task_list_env_suffix(app) == StyledSpan(" \u9225?Production", dim=True)
    app.env_filter = "env-2"
    assert task_list_env_suffix(app) == StyledSpan(" \u9225?Selected", dim=True)
    app.env_filter = "missing"
    assert task_list_env_suffix(app) == StyledSpan(" \u9225?Selected", dim=True)

    assert task_list_percent_span(0, 99) == StyledSpan("  \u9225?0%", dim=True)
    assert task_list_percent_span(1, 99) == StyledSpan("  \u9225?0%", dim=True)
    assert task_list_percent_span(3, -1) == StyledSpan("  \u9225?0%", dim=True)
    assert task_list_percent_span(3, 99) == StyledSpan("  \u9225?100%", dim=True)

    app.env_modal = object()
    title = task_list_title_line(app)
    assert task_list_dimmed(app) is True
    assert title[0] == StyledSpan("Cloud Tasks", dim=True)

    inner = task_list_inner_area(Rect(x=10, y=20, width=80, height=20))
    assert inner == Rect(x=11, y=21, width=78, height=18)
    assert task_list_rows_area(inner) == Rect(x=11, y=22, width=78, height=17)
    assert task_list_rows_area(Rect(x=1, y=2, width=3, height=0)) == Rect(
        x=1, y=2, width=3, height=0
    )


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
