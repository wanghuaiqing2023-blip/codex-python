import asyncio
from io import StringIO

from pycodex.tui.tui import (
    DisableAlternateScroll,
    EnableAlternateScroll,
    NotificationCondition,
    Rect,
    RestoreMode,
    SemanticTerminal,
    Tui,
    clear_for_viewport_change,
    should_emit_notification,
)


def test_notification_condition_matches_rust_cases() -> None:
    assert should_emit_notification(NotificationCondition.ALWAYS, True)
    assert should_emit_notification(NotificationCondition.ALWAYS, False)
    assert not should_emit_notification(NotificationCondition.UNFOCUSED, True)
    assert should_emit_notification(NotificationCondition.UNFOCUSED, False)


def test_alternate_scroll_ansi_commands_match_rust_literals() -> None:
    writer = StringIO()
    EnableAlternateScroll().write_ansi(writer)
    DisableAlternateScroll().write_ansi(writer)
    assert writer.getvalue() == "\x1b[?1007h\x1b[?1007l"


def test_history_batches_by_wrap_policy_and_schedules_frame() -> None:
    tui = Tui.new()

    tui.insert_history_hyperlink_lines_with_wrap_policy(["a"], "PreWrap")
    tui.insert_history_hyperlink_lines_with_wrap_policy(["b"], "PreWrap")
    tui.insert_history_hyperlink_lines_with_wrap_policy(["c"], "NoWrap")

    assert [batch.lines for batch in tui.pending_history_lines] == [["a", "b"], ["c"]]
    assert [batch.wrap_policy for batch in tui.pending_history_lines] == ["PreWrap", "NoWrap"]
    assert len(tui.frame_requester().scheduled) == 3

    tui.clear_pending_history_lines()
    assert tui.pending_history_lines == []


def test_alt_screen_enter_leave_saves_and_restores_inline_viewport() -> None:
    terminal = SemanticTerminal(width=100, height=40)
    terminal.viewport_area = Rect(0, 10, 100, 12)
    tui = Tui.new(terminal=terminal)

    tui.enter_alt_screen()
    assert tui.is_alt_screen_active()
    assert terminal.viewport_area == Rect(0, 0, 100, 40)

    tui.leave_alt_screen()
    assert not tui.is_alt_screen_active()
    assert terminal.viewport_area == Rect(0, 10, 100, 12)
    assert "enter_alternate_screen" in terminal.operations
    assert "leave_alternate_screen" in terminal.operations


def test_clear_for_viewport_change_uses_new_area_when_first_viewport() -> None:
    terminal = SemanticTerminal()
    new_area = Rect(0, 4, 80, 10)

    clear_for_viewport_change(terminal, new_area)

    assert terminal.operations[-1] == ("clear_after_position", new_area.as_position())


def test_clear_for_viewport_change_uses_previous_area_when_existing_viewport() -> None:
    terminal = SemanticTerminal()
    previous = Rect(0, 3, 80, 10)
    terminal.viewport_area = previous

    clear_for_viewport_change(terminal, Rect(0, 5, 80, 10))

    assert terminal.operations[-1] == ("clear_after_position", previous.as_position())


def test_resize_reflow_keeps_bottom_aligned_viewport_bottom_aligned() -> None:
    terminal = SemanticTerminal(width=100, height=20)
    terminal.last_known_screen_size = Rect(0, 0, 100, 10)
    terminal.viewport_area = Rect(0, 5, 100, 5)
    tui = Tui.new(terminal=terminal)

    assert tui.update_inline_viewport_for_resize_reflow(6)
    assert terminal.viewport_area == Rect(0, 14, 100, 6)


def test_notify_respects_focus_condition_and_disables_failing_backend() -> None:
    calls = []
    tui = Tui.new()
    tui.terminal_focused = False
    tui.set_notification_settings(calls.append, NotificationCondition.UNFOCUSED)

    assert tui.notify("hello")
    assert calls == ["hello"]

    def failing_backend(message: str) -> None:
        raise RuntimeError(message)

    tui.set_notification_settings(failing_backend, NotificationCondition.ALWAYS)
    assert not tui.notify("boom")
    assert tui.notification_backend is None


def test_with_restored_pauses_events_restores_modes_and_reenters_alt_screen() -> None:
    async def run() -> str:
        tui = Tui.new()
        tui.enter_alt_screen()
        result = await tui.with_restored(RestoreMode.FULL, lambda: "ok")
        assert result == "ok"
        assert tui.is_alt_screen_active()
        assert not tui.event_broker_paused
        assert "disable_raw_mode" in tui.terminal.operations
        assert "enable_raw_mode" in tui.terminal.operations
        return result

    assert asyncio.run(run()) == "ok"


def test_draw_applies_pending_viewport_and_flushes_pending_history() -> None:
    terminal = SemanticTerminal()
    terminal.viewport_area = Rect(0, 2, 80, 10)
    terminal.last_known_cursor_pos = terminal.cursor_position
    tui = Tui.new(terminal=terminal)
    tui.insert_history_lines(["line"])

    result = tui.draw(lambda frame: frame.viewport_area)

    assert result == Rect(0, 2, 80, 10)
    assert tui.pending_history_lines == []
    assert ("insert_history_lines", ("line",), "PreWrap") in terminal.operations
