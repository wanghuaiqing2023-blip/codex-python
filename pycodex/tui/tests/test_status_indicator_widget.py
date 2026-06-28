from pycodex.tui.status_indicator_widget import (
    AppEventSender,
    FrameRequester,
    KeyBinding,
    STATUS_DETAILS_DEFAULT_MAX_LINES,
    StatusDetailsCapitalization,
    StatusIndicatorWidget,
    desired_height,
    fmt_elapsed_compact,
    render,
)


def _text(lines) -> list[str]:
    return ["".join(span.content for span in line.spans) for line in lines]


def _widget(*, animations_enabled: bool = True, now: float = 100.0) -> StatusIndicatorWidget:
    return StatusIndicatorWidget.new(
        AppEventSender(),
        FrameRequester(),
        animations_enabled,
        clock=lambda: now,
    )


def test_fmt_elapsed_compact_formats_seconds_minutes_hours() -> None:
    """Rust codex-tui::status_indicator_widget::tests::fmt_elapsed_compact_formats_seconds_minutes_hours."""

    assert fmt_elapsed_compact(0) == "0s"
    assert fmt_elapsed_compact(1) == "1s"
    assert fmt_elapsed_compact(59) == "59s"
    assert fmt_elapsed_compact(60) == "1m 00s"
    assert fmt_elapsed_compact(61) == "1m 01s"
    assert fmt_elapsed_compact(3 * 60 + 5) == "3m 05s"
    assert fmt_elapsed_compact(59 * 60 + 59) == "59m 59s"
    assert fmt_elapsed_compact(3600) == "1h 00m 00s"
    assert fmt_elapsed_compact(3600 + 60 + 1) == "1h 01m 01s"
    assert fmt_elapsed_compact(25 * 3600 + 2 * 60 + 3) == "25h 02m 03s"


def test_renders_with_working_header_and_interrupt_hint() -> None:
    """Rust codex-tui::status_indicator_widget::tests::renders_with_working_header."""

    widget = _widget(animations_enabled=False)
    widget.pause_timer_at(100.0)

    rendered = _text(widget.render_lines(width=80, height=1, now=100.0))

    assert rendered == ["Working (0s • esc to interrupt)"]


def test_render_truncates_status_row_to_width() -> None:
    """Rust codex-tui::status_indicator_widget::tests::renders_truncated."""

    widget = _widget(animations_enabled=False)
    widget.update_header("Working on a long task")
    widget.pause_timer_at(100.0)

    rendered = _text(widget.render_lines(width=20, height=1, now=100.0))

    assert len(rendered[0]) <= 20
    assert rendered[0].endswith("…")


def test_renders_wrapped_details_panama_two_lines() -> None:
    """Rust codex-tui::status_indicator_widget::tests::renders_wrapped_details_panama_two_lines."""

    widget = _widget(animations_enabled=False)
    widget.update_details(
        "A man a plan a canal panama",
        StatusDetailsCapitalization.CapitalizeFirst,
        STATUS_DETAILS_DEFAULT_MAX_LINES,
    )
    widget.set_interrupt_hint_visible(False)
    widget.pause_timer_at(100.0)

    rendered = _text(widget.render_lines(width=30, height=3, now=100.0))

    assert rendered[0] == "Working (0s)"
    assert rendered[1] == "  │ A man a plan a canal"
    assert rendered[2] == "    panama"


def test_render_schedules_animation_frame_only_when_animations_enabled() -> None:
    """Rust source contract: rendering keeps active status animation ticking."""

    animated = _widget(animations_enabled=True)
    render(animated, area=type("Area", (), {"width": 80, "height": 1})())
    assert animated.frame_requester.scheduled == [0.032]

    reduced = _widget(animations_enabled=False)
    render(reduced, area=type("Area", (), {"width": 80, "height": 1})())
    assert reduced.frame_requester.scheduled == []


def test_renders_remapped_interrupt_hint_and_inline_message() -> None:
    """Rust codex-tui::status_indicator_widget::tests::renders_remapped_interrupt_hint."""

    widget = _widget(animations_enabled=False)
    widget.set_interrupt_binding(KeyBinding("F12"))
    widget.update_inline_message("queued")
    widget.pause_timer_at(100.0)

    rendered = _text(widget.render_lines(width=80, height=1, now=100.0))

    assert rendered == ["Working (0s • f12 to interrupt) · queued"]


def test_timer_pauses_when_requested() -> None:
    """Rust codex-tui::status_indicator_widget::tests::timer_pauses_when_requested."""

    widget = _widget()
    baseline = 1000.0
    widget.last_resume_at = baseline

    assert widget.elapsed_seconds_at(baseline + 5) == 5
    widget.pause_timer_at(baseline + 5)
    assert widget.elapsed_seconds_at(baseline + 10) == 5
    widget.resume_timer_at(baseline + 10)
    assert widget.elapsed_seconds_at(baseline + 13) == 8
    assert widget.frame_requester.scheduled[-1] == 0.0


def test_details_overflow_adds_ellipsis() -> None:
    """Rust codex-tui::status_indicator_widget::tests::details_overflow_adds_ellipsis."""

    widget = _widget()
    widget.update_details(
        "abcd abcd abcd abcd",
        StatusDetailsCapitalization.CapitalizeFirst,
        STATUS_DETAILS_DEFAULT_MAX_LINES,
    )

    lines = widget.wrapped_details_lines(width=6)

    assert len(lines) == STATUS_DETAILS_DEFAULT_MAX_LINES
    assert lines[-1].spans[-1].content.endswith("…")


def test_details_args_can_disable_capitalization_and_limit_lines() -> None:
    """Rust codex-tui::status_indicator_widget::tests::details_args_can_disable_capitalization_and_limit_lines."""

    widget = _widget()
    widget.update_details(
        "cargo test -p codex-core and then cargo test -p codex-tui",
        StatusDetailsCapitalization.Preserve,
        max_lines=1,
    )

    lines = widget.wrapped_details_lines(width=24)

    assert widget.details() == "cargo test -p codex-core and then cargo test -p codex-tui"
    assert len(lines) == 1
    assert any("…" in span.content for span in lines[-1].spans)
    assert desired_height(widget, width=24) == 2
