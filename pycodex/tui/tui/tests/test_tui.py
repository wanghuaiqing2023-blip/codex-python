import asyncio
import os
from io import StringIO
from types import SimpleNamespace

# Rust owner: codex-tui::tui (codex/codex-rs/tui/src/tui.rs).

from pycodex.tui.tui import (
    DisableAlternateScroll,
    EnableAlternateScroll,
    NotificationCondition,
    Rect,
    RestoreMode,
    SemanticTerminal,
    TerminalBottomPaneViewportCycleRunner,
    TerminalInlineViewport,
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


def test_zellij_raw_mode_is_limited_to_terminal_wrapped_batches(monkeypatch) -> None:
    # Rust tui::flush_pending_history_lines selects ZellijRaw only when both
    # terminal detection reports Zellij and the batch uses Terminal wrapping.
    monkeypatch.setattr(
        "pycodex.tui.tui.terminal_info",
        lambda: type("TerminalInfo", (), {"is_zellij": lambda self: True})(),
    )
    tui = Tui.new()
    tui.insert_history_lines_with_wrap_policy(["pre-wrapped"], "PreWrap")
    tui.flush_pending_history_lines()
    assert "zellij_raw_mode_restore" not in tui.terminal.operations

    tui.insert_history_lines_with_wrap_policy(["terminal-wrapped"], "Terminal")
    tui.flush_pending_history_lines()
    assert tui.terminal.operations.count("zellij_raw_mode_restore") == 1


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


def test_resize_replay_clear_resets_real_terminal_viewport_to_top() -> None:
    # Rust app::resize_reflow::clear_terminal_for_resize_replay sets area.y=0
    # after clearing so retained history is rebuilt from the top of the screen.
    operations = []
    viewport = TerminalInlineViewport(
        terminal_size=lambda: os.terminal_size((80, 24)),
        scroll_region_up_effect=lambda start, end, amount: operations.append(("up", start, end, amount)),
        scroll_region_down_effect=lambda start, end, amount: operations.append(("down", start, end, amount)),
        clear_after_position_effect=lambda row, column: operations.append(("clear", row, column)),
        invalidate_viewport_effect=lambda: operations.append("invalidate"),
        viewport_area=Rect(0, 18, 80, 6),
        last_known_screen_size=Rect(0, 0, 80, 24),
    )

    viewport.reset_top_after_resize_replay_clear()

    assert viewport.viewport_area == Rect(0, 0, 80, 6)
    assert operations == ["invalidate"]


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


def _real_terminal_viewport(
    size: list[os.terminal_size],
    effects: list[tuple[object, ...]],
) -> TerminalInlineViewport:
    return TerminalInlineViewport(
        terminal_size=lambda: size[0],
        scroll_region_up_effect=lambda start, end, amount: effects.append(
            ("up", start, end, amount)
        ),
        scroll_region_down_effect=lambda start, end, amount: effects.append(
            ("down", start, end, amount)
        ),
        clear_after_position_effect=lambda row, column: effects.append(
            ("clear", row, column)
        ),
        invalidate_viewport_effect=lambda: effects.append(("invalidate",)),
    )


def test_real_terminal_draw_grows_inline_viewport_before_render() -> None:
    """Rust tui.rs::draw_with_resize_reflow grows and clears before drawing."""

    size = [os.terminal_size((80, 24))]
    effects: list[tuple[object, ...]] = []
    viewport = _real_terminal_viewport(size, effects)

    drawn = viewport.draw_with_resize_reflow(4, lambda area: area)

    assert drawn == Rect(0, 20, 80, 4)
    assert effects == [
        ("up", 0, 24, 4),
        ("clear", 20, 0),
        ("invalidate",),
    ]


def test_real_terminal_viewport_growth_and_shrink_match_rust_anchor_rules() -> None:
    """Rust tui.rs keeps the viewport y anchor when desired height shrinks."""

    size = [os.terminal_size((80, 24))]
    effects: list[tuple[object, ...]] = []
    viewport = _real_terminal_viewport(size, effects)
    viewport.viewport_area = Rect(0, 20, 80, 4)
    viewport.last_known_screen_size = Rect(0, 0, 80, 24)

    assert viewport.update_inline_viewport_for_resize_reflow(8)
    assert viewport.viewport_area == Rect(0, 16, 80, 8)
    assert effects[:3] == [
        ("up", 0, 20, 4),
        ("clear", 16, 0),
        ("invalidate",),
    ]

    effects.clear()
    assert viewport.update_inline_viewport_for_resize_reflow(4)
    assert viewport.viewport_area == Rect(0, 16, 80, 4)
    assert effects == [("clear", 16, 0), ("invalidate",)]


def test_real_terminal_resize_realigns_growth_but_does_not_scroll_on_shrink() -> None:
    """Rust tui.rs distinguishes terminal growth from terminal shrink."""

    size = [os.terminal_size((80, 24))]
    effects: list[tuple[object, ...]] = []
    viewport = _real_terminal_viewport(size, effects)
    viewport.viewport_area = Rect(0, 20, 80, 4)
    viewport.last_known_screen_size = Rect(0, 0, 80, 24)

    size[0] = os.terminal_size((100, 30))
    assert viewport.update_inline_viewport_for_resize_reflow(4)
    assert viewport.viewport_area == Rect(0, 26, 100, 4)
    assert not any(effect[0] == "up" for effect in effects)

    viewport.last_known_screen_size = Rect(0, 0, 100, 30)
    viewport.viewport_area = Rect(0, 22, 100, 8)
    size[0] = os.terminal_size((80, 20))
    effects.clear()
    assert viewport.update_inline_viewport_for_resize_reflow(8)
    assert viewport.viewport_area == Rect(0, 12, 80, 8)
    assert not any(effect[0] == "up" for effect in effects)


def test_real_terminal_history_insert_moves_non_bottom_viewport_down() -> None:
    """Rust insert_history.rs standard mode makes room below the viewport."""

    size = [os.terminal_size((80, 24))]
    effects: list[tuple[object, ...]] = []
    viewport = _real_terminal_viewport(size, effects)
    viewport.viewport_area = Rect(0, 10, 80, 4)
    viewport.last_known_screen_size = Rect(0, 0, 80, 24)

    viewport.prepare_history_insert(3)

    assert viewport.viewport_area == Rect(0, 13, 80, 4)
    assert effects == [("down", 10, 24, 3), ("invalidate",)]


def test_resize_reflow_replay_callback_moves_viewport_before_app_replay() -> None:
    """Rust tui.rs updates viewport before flushing app-owned history."""

    size = [os.terminal_size((80, 24))]
    effects: list[tuple[object, ...]] = []
    viewport = _real_terminal_viewport(size, effects)
    runner = TerminalBottomPaneViewportCycleRunner(viewport, resize=lambda: None)
    context = SimpleNamespace(
        popup_height=0,
        active_tail_height=0,
        composer_height=1,
    )
    state = SimpleNamespace(render_context_for_size=lambda _size, _cursor: context)
    replay_observations: list[tuple[Rect | None, tuple[tuple[object, ...], ...]]] = []
    bind_replay = runner.resize_reflow_replay_callback_factory(
        terminal_size=lambda: size[0],
        live_status=lambda: SimpleNamespace(footprint_active=False),
        bottom_pane_state=state,
        composer_cursor_visible=lambda: True,
    )

    bind_replay(
        lambda: replay_observations.append((viewport.viewport_area, tuple(effects)))
    )()

    assert replay_observations == [
        (
            Rect(0, 0, 80, 4),
            (
                ("up", 0, 24, 4),
                ("clear", 20, 0),
                ("invalidate",),
                ("invalidate",),
            ),
        )
    ]
