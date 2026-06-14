from pycodex.tui.app.event_dispatch import (
    SHUTDOWN_FIRST_EXIT_TIMEOUT,
    AppRunControl,
    EventDispatchState,
    ExitMode,
    ExitModePlan,
    ExitReason,
    handle_exit_mode_plan,
)


def test_shutdown_first_marks_active_thread_for_shutdown_then_clears_pending():
    """Rust codex-tui app::event_dispatch::handle_exit_mode ShutdownFirst active thread branch."""

    state = EventDispatchState(active_thread_id="active", chat_widget_thread_id="chat")

    plan = handle_exit_mode_plan(state, ExitMode.ShutdownFirst)

    assert plan == ExitModePlan(
        run_control=AppRunControl.exit(ExitReason.UserRequested),
        shutdown_thread_id="active",
        timeout_seconds=SHUTDOWN_FIRST_EXIT_TIMEOUT,
    )
    assert state.pending_shutdown_exit_thread_id is None


def test_shutdown_first_uses_chat_widget_thread_when_no_active_thread():
    """Rust codex-tui app::event_dispatch::handle_exit_mode ShutdownFirst fallback branch."""

    state = EventDispatchState(active_thread_id=None, chat_widget_thread_id="chat")

    plan = handle_exit_mode_plan(state, "ShutdownFirst")

    assert plan.shutdown_thread_id == "chat"
    assert plan.timeout_seconds == SHUTDOWN_FIRST_EXIT_TIMEOUT
    assert plan.run_control == AppRunControl.exit(ExitReason.UserRequested)
    assert state.pending_shutdown_exit_thread_id is None


def test_shutdown_first_without_thread_skips_shutdown_timeout():
    """Rust codex-tui app::event_dispatch::handle_exit_mode ShutdownFirst no-thread branch."""

    state = EventDispatchState(active_thread_id=None, chat_widget_thread_id=None)

    plan = handle_exit_mode_plan(state, "shutdown-first")

    assert plan.shutdown_thread_id is None
    assert plan.timeout_seconds is None
    assert plan.run_control == AppRunControl.exit(ExitReason.UserRequested)
    assert state.pending_shutdown_exit_thread_id is None


def test_immediate_exit_clears_pending_without_shutdown():
    """Rust codex-tui app::event_dispatch::handle_exit_mode Immediate branch."""

    state = EventDispatchState(
        active_thread_id="active",
        chat_widget_thread_id="chat",
        pending_shutdown_exit_thread_id="old",
    )

    plan = handle_exit_mode_plan(state, ExitMode.Immediate)

    assert plan == ExitModePlan(
        run_control=AppRunControl.exit(ExitReason.UserRequested),
        shutdown_thread_id=None,
        timeout_seconds=None,
    )
    assert state.pending_shutdown_exit_thread_id is None
