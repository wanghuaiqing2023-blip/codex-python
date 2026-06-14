from __future__ import annotations

from pycodex.tui.app.thread_routing import (
    SessionSelection,
    ThreadClosedNotification,
    active_non_primary_shutdown_target,
    should_handle_active_thread_events,
    should_prompt_for_paused_goal_after_startup_resume,
    should_stop_waiting_for_initial_session,
    should_wait_for_initial_session,
)


def test_should_wait_for_initial_session_matches_start_fresh_and_exit() -> None:
    assert should_wait_for_initial_session(SessionSelection.start_fresh())
    assert should_wait_for_initial_session(SessionSelection.exit())
    assert not should_wait_for_initial_session(SessionSelection.resume("thread-1"))


def test_should_prompt_for_paused_goal_after_startup_resume_requires_resume_without_inputs() -> None:
    assert should_prompt_for_paused_goal_after_startup_resume(SessionSelection.resume("thread-1"), None, [])
    assert not should_prompt_for_paused_goal_after_startup_resume(SessionSelection.resume("thread-1"), "hello", [])
    assert not should_prompt_for_paused_goal_after_startup_resume(SessionSelection.resume("thread-1"), None, ["image.png"])
    assert not should_prompt_for_paused_goal_after_startup_resume(SessionSelection.start_fresh(), None, [])


def test_active_thread_event_waiting_predicates() -> None:
    assert should_handle_active_thread_events(False, True)
    assert not should_handle_active_thread_events(True, True)
    assert not should_handle_active_thread_events(False, False)
    assert should_stop_waiting_for_initial_session(True, "primary")
    assert not should_stop_waiting_for_initial_session(True, None)
    assert not should_stop_waiting_for_initial_session(False, "primary")


def test_active_non_primary_shutdown_target_ignores_primary_and_pending_exit() -> None:
    notification = ThreadClosedNotification("agent")

    assert active_non_primary_shutdown_target(notification, "agent", "primary") == ("agent", "primary")
    assert active_non_primary_shutdown_target(notification, "primary", "primary") is None
    assert active_non_primary_shutdown_target(notification, "agent", "primary", "agent") is None
    assert active_non_primary_shutdown_target({"type": "other"}, "agent", "primary") is None
    assert active_non_primary_shutdown_target(notification, None, "primary") is None
    assert active_non_primary_shutdown_target(notification, "agent", None) is None
