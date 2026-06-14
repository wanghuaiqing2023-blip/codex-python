"""Parity tests for Rust ``codex-tui::status_indicator_widget``.

Rust source: ``codex/codex-rs/tui/src/status_indicator_widget.rs``.
"""

from pycodex.tui.status_indicator_widget import (
    STATUS_DETAILS_DEFAULT_MAX_LINES,
    AppEventSender,
    FrameRequester,
    KeyBinding,
    StatusDetailsCapitalization,
    StatusIndicatorWidget,
    fmt_elapsed_compact,
)
from pycodex.tui.wrapping import concat_line


def test_fmt_elapsed_compact_formats_seconds_minutes_hours() -> None:
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


def test_details_update_capitalization_and_limit() -> None:
    widget = StatusIndicatorWidget.new(animations_enabled=False, clock=lambda: 0.0)
    widget.update_details("   a man a plan", StatusDetailsCapitalization.CapitalizeFirst, 0)
    assert widget.details() == "A man a plan"
    assert widget.details_max_lines == 1
    widget.update_details("cargo test", StatusDetailsCapitalization.Preserve, 2)
    assert widget.details() == "cargo test"
    widget.update_details("", StatusDetailsCapitalization.Preserve, 3)
    assert widget.details() is None


def test_inline_message_trim_and_interrupt() -> None:
    sender = AppEventSender()
    widget = StatusIndicatorWidget.new(sender, animations_enabled=False, clock=lambda: 0.0)
    widget.update_inline_message("  bg tasks  ")
    assert widget.inline_message == "bg tasks"
    widget.update_inline_message("   ")
    assert widget.inline_message is None
    widget.interrupt()
    assert sender.interrupted


def test_timer_pauses_when_requested() -> None:
    widget = StatusIndicatorWidget.new(animations_enabled=True, clock=lambda: 0.0)
    baseline = 100.0
    widget.last_resume_at = baseline
    before_pause = widget.elapsed_seconds_at(baseline + 5)
    assert before_pause == 5
    widget.pause_timer_at(baseline + 5)
    assert widget.elapsed_seconds_at(baseline + 10) == before_pause
    widget.resume_timer_at(baseline + 10)
    assert widget.elapsed_seconds_at(baseline + 13) == before_pause + 3
    assert widget.frame_requester.scheduled == [0.0]
    widget.resume_timer_at(baseline + 20)
    assert widget.frame_requester.scheduled == [0.0]


def test_render_without_spinner_when_animations_disabled() -> None:
    widget = StatusIndicatorWidget.new(animations_enabled=False, clock=lambda: 0.0)
    widget.is_paused = True
    widget.elapsed_running = 0.0
    text = concat_line(widget.render_lines(80, 1)[0])
    assert text.startswith("Working (0s • esc to interrupt)")


def test_render_remapped_interrupt_hint_and_inline_message() -> None:
    widget = StatusIndicatorWidget.new(animations_enabled=False, clock=lambda: 0.0)
    widget.set_interrupt_binding(KeyBinding("f12"))
    widget.update_inline_message("running shell")
    text = concat_line(widget.render_lines(80, 1)[0])
    assert "f12 to interrupt" in text
    assert "· running shell" in text
    widget.set_interrupt_hint_visible(False)
    text = concat_line(widget.render_lines(80, 1)[0])
    assert "to interrupt" not in text
    assert "(0s)" in text


def test_render_schedules_animation_frame_and_empty_area_noops() -> None:
    widget = StatusIndicatorWidget.new(animations_enabled=True, clock=lambda: 0.0)
    assert widget.render_lines(0, 1) == []
    assert widget.frame_requester.scheduled == []
    widget.render_lines(80, 1)
    assert widget.frame_requester.scheduled == [0.032]


def test_details_overflow_adds_ellipsis() -> None:
    widget = StatusIndicatorWidget.new(animations_enabled=True, clock=lambda: 0.0)
    widget.update_details(
        "abcd abcd abcd abcd",
        StatusDetailsCapitalization.CapitalizeFirst,
        STATUS_DETAILS_DEFAULT_MAX_LINES,
    )
    lines = widget.wrapped_details_lines(6)
    assert len(lines) == STATUS_DETAILS_DEFAULT_MAX_LINES
    assert concat_line(lines[-1]).endswith("…")


def test_desired_height_and_render_details_height_limit() -> None:
    widget = StatusIndicatorWidget.new(animations_enabled=False, clock=lambda: 0.0)
    widget.update_details("A man a plan a canal panama", StatusDetailsCapitalization.CapitalizeFirst, 3)
    assert widget.desired_height(30) == 3
    rendered = widget.render_lines(30, 2)
    assert len(rendered) == 2
    assert concat_line(rendered[1]).startswith("  │ ")
