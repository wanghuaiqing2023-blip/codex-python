from __future__ import annotations

from pycodex.tui.app.thread_routing import (
    SessionSelection,
    ThreadChannelState,
    ThreadClosedNotification,
    ThreadRoutingPlan,
    ThreadRoutingState,
    TurnPermissionsOverride,
    TurnPermissionsOverrideKind,
    activate_thread_channel,
    active_non_primary_shutdown_target,
    active_thread_event_plan,
    clear_active_thread,
    enqueue_primary_thread_notification,
    enqueue_primary_thread_request,
    pending_inactive_thread_requests,
    should_handle_active_thread_events,
    should_prompt_for_paused_goal_after_startup_resume,
    should_refresh_snapshot_session,
    should_stop_waiting_for_initial_session,
    should_wait_for_initial_session,
    store_active_thread_receiver,
    submit_active_thread_op_plan,
    turn_permissions_override_from_config,
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


def test_activate_store_and_clear_thread_channel_match_rust_state_transitions() -> None:
    """Rust codex-tui app::thread_routing active channel receiver ownership transitions."""

    state = ThreadRoutingState(thread_event_channels={"thread-1": ThreadChannelState(receiver="rx")})

    plan = activate_thread_channel(state, "thread-1")

    assert plan.action == "activate_thread_channel"
    assert state.active_thread_id == "thread-1"
    assert state.active_thread_rx == "rx"
    assert state.thread_event_channels["thread-1"].receiver is None
    assert state.thread_event_channels["thread-1"].active is True

    store_plan = store_active_thread_receiver(state, input_state={"draft": "hi"})

    assert store_plan.action == "store_active_thread_receiver"
    assert state.active_thread_rx is None
    assert state.thread_event_channels["thread-1"].receiver == "rx"
    assert state.thread_event_channels["thread-1"].input_state == {"draft": "hi"}
    assert state.thread_event_channels["thread-1"].active is False

    clear_plan = clear_active_thread(state)

    assert clear_plan == ThreadRoutingPlan(
        action="clear_active_thread",
        thread_id="thread-1",
        updates=(("refresh_pending_thread_approvals", True),),
    )
    assert state.active_thread_id is None
    assert state.active_thread_rx is None


def test_activate_thread_channel_skips_when_active_thread_exists() -> None:
    """Rust activate_thread_channel returns early when active_thread_id is already set."""

    state = ThreadRoutingState(
        active_thread_id="active",
        active_thread_rx="active-rx",
        thread_event_channels={
            "side": ThreadChannelState(receiver="side-rx"),
        },
    )

    plan = activate_thread_channel(state, "side")

    assert plan.action == "activate_thread_channel_skipped"
    assert plan.thread_id == "side"
    assert state.active_thread_id == "active"
    assert state.active_thread_rx == "active-rx"
    assert state.thread_event_channels["side"].receiver == "side-rx"
    assert state.thread_event_channels["side"].active is False


def test_primary_thread_events_buffer_until_primary_thread_exists() -> None:
    """Rust codex-tui app::thread_routing buffers primary requests before primary_thread_id."""

    state = ThreadRoutingState()

    notification_plan = enqueue_primary_thread_notification(state, {"type": "turn_started"})
    request_plan = enqueue_primary_thread_request(state, {"type": "approval"})

    assert notification_plan.action == "buffer_primary_notification"
    assert request_plan.action == "buffer_primary_request"
    assert state.pending_primary_events == [
        ("notification", {"type": "turn_started"}),
        ("request", {"type": "approval"}),
    ]

    state.primary_thread_id = "primary"
    routed = enqueue_primary_thread_request(state, {"type": "next"})

    assert routed.action == "enqueue_thread_request"
    assert routed.thread_id == "primary"


def test_pending_inactive_thread_requests_skips_active_thread() -> None:
    """Rust codex-tui app::thread_routing pending_inactive_thread_requests skips active channel."""

    state = ThreadRoutingState(
        active_thread_id="active",
        thread_event_channels={
            "active": ThreadChannelState(pending_requests=["active-request"]),
            "side": ThreadChannelState(pending_requests=["side-request"]),
        },
    )

    assert pending_inactive_thread_requests(state) == [("side", "side-request")]


def test_submit_active_thread_op_reports_missing_active_thread() -> None:
    """Rust codex-tui app::thread_routing submit_active_thread_op reports missing active thread."""

    state = ThreadRoutingState()

    plan = submit_active_thread_op_plan(state, {"kind": "UserInput"})

    assert plan.action == "submit_active_thread_op_skipped"
    assert plan.error_message == "No active thread is available."
    assert state.errors == ["No active thread is available."]


def test_active_thread_event_plan_failover_and_pending_shutdown_completion() -> None:
    """Rust codex-tui app::thread_routing handle_active_thread_event shutdown routing."""

    state = ThreadRoutingState(active_thread_id="agent", primary_thread_id="primary")

    failover = active_thread_event_plan(state, {"notification": ThreadClosedNotification("agent")})

    assert failover.action == "failover_to_primary_thread"
    assert failover.thread_id == "agent"
    assert failover.target_thread_id == "primary"

    pending = ThreadRoutingState(
        active_thread_id="agent",
        primary_thread_id="primary",
        pending_shutdown_exit_thread_id="agent",
    )

    handled = active_thread_event_plan(pending, {"notification": ThreadClosedNotification("agent")})

    assert handled.action == "handle_thread_event_now"
    assert pending.pending_shutdown_exit_thread_id is None


def test_should_refresh_snapshot_session_matches_rust_predicate() -> None:
    """Rust codex-tui app::thread_routing should_refresh_snapshot_session predicate."""

    assert should_refresh_snapshot_session("main", False, {"session": None})
    assert not should_refresh_snapshot_session("main", True, {"session": None})
    assert not should_refresh_snapshot_session("side", False, {"session": None}, side_threads={"side"})
    assert should_refresh_snapshot_session("main", False, {"session": {"model": "", "rollout_path": "p"}})
    assert should_refresh_snapshot_session("main", False, {"session": {"model": "gpt", "rollout_path": None}})
    assert not should_refresh_snapshot_session("main", False, {"session": {"model": "gpt", "rollout_path": "p"}})


def test_turn_permissions_override_from_config_matches_rust_tests() -> None:
    """Rust codex-tui app::thread_routing turn_permissions_override_from_config tests."""

    assert turn_permissions_override_from_config({}, "workspace", None) == TurnPermissionsOverride(
        TurnPermissionsOverrideKind.ActiveProfile,
        "workspace",
    )
    assert turn_permissions_override_from_config({}, None, None) == TurnPermissionsOverride(
        TurnPermissionsOverrideKind.Preserve,
        None,
    )
    assert turn_permissions_override_from_config(
        {"effective_permission_profile": "workspace_write"},
        None,
        "workspace_write",
    ) == TurnPermissionsOverride(TurnPermissionsOverrideKind.LegacySandbox, "workspace_write")
