from pycodex.tui.tui.job_control import (
    Position,
    PreparedResumeAction,
    Rect,
    ResumeAction,
    SUSPEND_KEY,
    SuspendContext,
    SuspendProcessTrace,
    Terminal,
    prepare_resume_action_consumes_realign_inline,
    prepare_resume_action_restores_alt_and_updates_saved_viewport,
    suspend_process,
    suspend_sets_realign_inline_for_inline_screen,
    suspend_sets_restore_alt_for_alt_screen,
)


def test_suspend_sets_restore_alt_for_alt_screen() -> None:
    # Rust: tui/job_control.rs SuspendContext::suspend alt-screen branch.
    assert suspend_sets_restore_alt_for_alt_screen()


def test_suspend_sets_realign_inline_for_inline_screen() -> None:
    # Rust: SuspendContext::suspend inline branch.
    assert suspend_sets_realign_inline_for_inline_screen()


def test_prepare_resume_action_consumes_realign_inline() -> None:
    # Rust: prepare_resume_action consumes pending RealignInline once.
    assert prepare_resume_action_consumes_realign_inline()


def test_prepare_resume_action_restores_alt_and_updates_saved_viewport() -> None:
    # Rust: RestoreAlt updates saved viewport y from cursor position when available.
    assert prepare_resume_action_restores_alt_and_updates_saved_viewport()


def test_realign_inline_falls_back_to_last_known_cursor_position() -> None:
    ctx = SuspendContext.new()
    terminal = Terminal(last_known_cursor_pos=Position(9, 14), cursor_position=None)
    ctx.set_resume_action(ResumeAction.RealignInline)

    assert ctx.prepare_resume_action(terminal) == PreparedResumeAction.RealignViewport(
        Rect(0, 14, 0, 0)
    )


def test_prepared_resume_action_apply_realign_viewport() -> None:
    terminal = Terminal()

    PreparedResumeAction.RealignViewport(Rect(0, 11, 0, 0)).apply(terminal)

    assert terminal.viewport_area == Rect(0, 11, 0, 0)


def test_prepared_resume_action_apply_restore_alt_screen() -> None:
    terminal = Terminal(size_width=100, size_height=40)

    PreparedResumeAction.RestoreAltScreen().apply(terminal)

    assert terminal.entered_alt_screen == 1
    assert terminal.enabled_alt_scroll == 1
    assert terminal.viewport_area == Rect(0, 0, 100, 40)
    assert terminal.cleared == 1


def test_restore_alt_screen_size_error_skips_viewport_reset_like_rust() -> None:
    terminal = Terminal(size_error="unavailable")

    PreparedResumeAction.RestoreAltScreen().apply(terminal)

    assert terminal.entered_alt_screen == 1
    assert terminal.enabled_alt_scroll == 1
    assert terminal.viewport_history == []
    assert terminal.cleared == 0


def test_cursor_y_is_u16_cached_and_restore_alt_cursor_failure_keeps_saved_viewport() -> None:
    # Rust: SuspendContext::set_cursor_y stores an AtomicU16; RestoreAlt only updates the
    # saved viewport when terminal.get_cursor_position() succeeds.
    ctx = SuspendContext.new()
    ctx.set_cursor_y(0x1FFFF)
    ctx.suspend(False)
    assert ctx.terminal_commands == [("MoveTo", 0, 0xFFFF), "Show"]

    saved = Rect(0, 8, 80, 20)
    terminal = Terminal(cursor_position=None)
    ctx.set_resume_action(ResumeAction.RestoreAlt)

    assert ctx.prepare_resume_action(terminal, saved) == PreparedResumeAction.RestoreAltScreen()
    assert saved == Rect(0, 8, 80, 20)
    assert ctx.prepare_resume_action(terminal, saved) is None


def test_suspend_process_trace_order_and_suspend_key() -> None:
    trace = suspend_process(SuspendProcessTrace())

    assert SUSPEND_KEY == "Ctrl+Z"
    assert trace.restored == 1
    assert trace.stderr_paused == 1
    assert trace.sigtstp_sent == 1
    assert trace.stderr_resumed == 1
    assert trace.modes_set == 1
