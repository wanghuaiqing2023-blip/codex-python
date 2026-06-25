from __future__ import annotations

from collections import deque
from types import SimpleNamespace

from pycodex.tui.app_command import AppCommand
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
from pycodex.tui.chatwidget.input_submission import (
    UserMessage,
    UserMessageHistoryRecord,
    submit_user_message_with_history_record,
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


class _CompositionMode:
    def model(self) -> str:
        return "gpt-5"

    def reasoning_effort(self) -> str:
        return "medium"


class _CompositionFeatures:
    def enabled(self, _feature: str) -> bool:
        return False


class _CompositionPane:
    def skills(self):
        return None


class _CompositionWidget:
    def __init__(self) -> None:
        self.bottom_pane = _CompositionPane()
        self.input_queue = SimpleNamespace(
            user_turn_pending_start=False,
            pending_steers=deque(),
        )
        self.turn_lifecycle = SimpleNamespace(agent_turn_running=False)
        self.transcript = SimpleNamespace(
            needs_final_message_separator=True,
            saw_plan_item_this_turn=True,
        )
        self.config = SimpleNamespace(
            cwd="/repo",
            permissions=SimpleNamespace(
                approval_policy="on-request",
                active_permission_profile=lambda: "workspace-write",
            ),
            features=_CompositionFeatures(),
            personality=None,
        )
        self.active_collaboration_mask = None
        self.ops = []
        self.history = []
        self.displays = []

    def is_session_configured(self) -> bool:
        return True

    def current_model_supports_images(self) -> bool:
        return True

    def effective_collaboration_mode(self) -> _CompositionMode:
        return _CompositionMode()

    def maybe_apply_ide_context(self, _items) -> None:
        return None

    def collaboration_modes_enabled(self) -> bool:
        return True

    def service_tier_update_for_core(self) -> str:
        return "auto"

    def current_model_supports_personality(self) -> bool:
        return False

    def plugins_for_mentions(self):
        return None

    def connectors_for_mentions(self):
        return None

    def submit_op(self, op) -> bool:
        self.ops.append(op)
        return True

    def append_message_history_entry(self, text: str) -> None:
        self.history.append(text)

    def on_user_message_display(self, display) -> None:
        self.displays.append(display)


def test_chatwidget_user_turn_composes_into_active_thread_routing() -> None:
    """Rust-derived composition contract.

    Rust sources:
    - codex-tui::chatwidget::input_submission constructs AppCommand::user_turn.
    - codex-tui::chatwidget::submit_op emits that command to the app.
    - codex-tui::app::thread_routing routes active-thread commands via submit_thread_op.
    - codex-tui::app::tests asserts replay/submit paths carry Op::UserTurn.
    """

    widget = _CompositionWidget()

    accepted = submit_user_message_with_history_record(
        widget,
        UserMessage("hello from composer"),
        UserMessageHistoryRecord.user_message_text(),
    )

    assert accepted
    op = widget.ops[-1]
    assert isinstance(op, AppCommand)
    assert op.kind == "UserTurn"
    assert op.payload["items"][0].kind == "Text"
    assert op.payload["items"][0].payload["text"] == "hello from composer"

    state = ThreadRoutingState(active_thread_id="thread-1")
    plan = submit_active_thread_op_plan(state, op)

    assert plan.action == "submit_thread_op"
    assert plan.thread_id == "thread-1"
    assert plan.app_server_call == (
        "submit_thread_op",
        {"thread_id": "thread-1", "op": op},
    )


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
