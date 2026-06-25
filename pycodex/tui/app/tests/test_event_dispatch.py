import asyncio

from pycodex.tui.app.event_dispatch import (
    SHUTDOWN_FIRST_EXIT_TIMEOUT,
    AppRunControl,
    EventDispatchPlan,
    EventDispatchState,
    ExitMode,
    ExitModePlan,
    ExitReason,
    dispatch_event_plan,
    handle_event,
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


def test_clear_ui_event_dispatches_to_clear_and_fresh_session_plan():
    """Rust codex-tui app::event_dispatch::handle_event AppEvent::ClearUi branch."""

    state = EventDispatchState()

    plan = dispatch_event_plan(state, {"ClearUi": {"summary_hint": "old"}})

    assert plan == EventDispatchPlan(
        action="clear_ui_and_start_fresh_session",
        updates=(
            ("clear_terminal_ui", None),
            ("reset_app_ui_state_after_clear", None),
            ("start_fresh_session_with_summary_hint", {"summary_hint": "old"}),
        ),
        schedule_frame=True,
    )


def test_exit_event_uses_shutdown_first_exit_mode_plan():
    """Rust codex-tui app::event_dispatch::handle_event AppEvent::Exit branch."""

    state = EventDispatchState(active_thread_id="thread-1")

    plan = dispatch_event_plan(state, {"variant": "Exit", "payload": {"mode": "ShutdownFirst"}})

    assert plan.action == "exit"
    assert plan.run_control == AppRunControl.exit(ExitReason.UserRequested)
    assert plan.updates == (("show_shutdown_feedback", "thread-1"),)
    assert plan.exit_mode_plan == ExitModePlan(
        run_control=AppRunControl.exit(ExitReason.UserRequested),
        shutdown_thread_id="thread-1",
        timeout_seconds=SHUTDOWN_FIRST_EXIT_TIMEOUT,
    )


def test_fatal_exit_request_dispatches_to_exit_control():
    """Rust codex-tui app::event_dispatch::handle_event AppEvent::FatalExitRequest branch."""

    state = EventDispatchState()

    plan = dispatch_event_plan(state, {"FatalExitRequest": {"reason": "boom"}})

    assert plan.action == "fatal_exit_request"
    assert plan.run_control == AppRunControl.exit("fatal:boom")
    assert plan.messages == ("boom",)


def test_logout_success_uses_shutdown_first_exit_mode_plan():
    """Rust codex-tui app::event_dispatch::handle_event AppEvent::Logout Ok branch."""

    state = EventDispatchState(active_thread_id="thread-logout")

    plan = dispatch_event_plan(state, {"Logout": {}})

    assert plan.action == "logout_account_then_shutdown"
    assert plan.run_control == AppRunControl.exit(ExitReason.UserRequested)
    assert plan.updates == (
        ("logout", {}),
        ("show_shutdown_feedback", "thread-logout"),
    )
    assert plan.exit_mode_plan == ExitModePlan(
        run_control=AppRunControl.exit(ExitReason.UserRequested),
        shutdown_thread_id="thread-logout",
        timeout_seconds=SHUTDOWN_FIRST_EXIT_TIMEOUT,
    )
    assert state.pending_shutdown_exit_thread_id is None


def test_logout_error_continues_and_reports_message():
    """Rust codex-tui app::event_dispatch::handle_event AppEvent::Logout Err branch."""

    state = EventDispatchState(active_thread_id="thread-logout")

    plan = dispatch_event_plan(state, {"Logout": {"error": "network unavailable"}})

    assert plan.action == "logout_account_failed"
    assert plan.run_control == AppRunControl.continue_()
    assert plan.updates == (("logout_error", "network unavailable"),)
    assert plan.messages == ("network unavailable",)
    assert plan.exit_mode_plan is None
    assert state.pending_shutdown_exit_thread_id is None


def test_known_delegated_event_keeps_rust_variant_name():
    """Rust codex-tui app::event_dispatch delegates pet events to app::pets handlers."""

    state = EventDispatchState()

    plan = dispatch_event_plan(state, {"PetSelected": {"name": "cat"}})

    assert plan.action == "handle_pet_selected"
    assert plan.forward_event == "PetSelected"
    assert plan.updates == (("handle_pet_selected", {"name": "cat"}),)
    assert plan.schedule_frame is True


def test_async_handle_event_returns_dispatch_plan():
    """Rust codex-tui app::event_dispatch async wrapper preserves the same dispatch decision."""

    state = EventDispatchState()

    plan = asyncio.run(handle_event(state, {"type": "OpenUrlInBrowser", "payload": "https://example.test"}))

    assert plan.action == "open_url_in_browser"
    assert plan.forward_event == "OpenUrlInBrowser"
