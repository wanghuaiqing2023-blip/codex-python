"""Thread routing predicates for Rust ``codex-tui::app::thread_routing``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_routing.rs``.

The Rust module owns routing decisions across active thread channels,
thread-scoped app-server operations, replay buffering, and shutdown failover.
Python represents runtime side effects as semantic plans so callers can verify
the same branch decisions without pretending to own Rust's mpsc channels,
tokio tasks, or app-server transport.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_routing",
    source="codex/codex-rs/tui/src/app/thread_routing.rs",
    status="complete",
)


class SessionSelectionKind(str):
    StartFresh = "start_fresh"
    Exit = "exit"
    Resume = "resume"
    Other = "other"


class TurnPermissionsOverrideKind(str):
    ActiveProfile = "active_profile"
    Preserve = "preserve"
    LegacySandbox = "legacy_sandbox"


@dataclass(frozen=True)
class SessionSelection:
    kind: Any
    payload: Optional[Any] = None

    @classmethod
    def start_fresh(cls) -> "SessionSelection":
        return cls(SessionSelectionKind.StartFresh)

    @classmethod
    def exit(cls) -> "SessionSelection":
        return cls(SessionSelectionKind.Exit)

    @classmethod
    def resume(cls, payload: Any = None) -> "SessionSelection":
        return cls(SessionSelectionKind.Resume, payload)


@dataclass(frozen=True)
class ThreadClosedNotification:
    thread_id: Optional[str] = None


@dataclass(frozen=True)
class TurnPermissionsOverride:
    kind: str
    value: Optional[Any] = None

    @classmethod
    def active_profile(cls, profile: Any) -> "TurnPermissionsOverride":
        return cls(TurnPermissionsOverrideKind.ActiveProfile, profile)

    @classmethod
    def preserve(cls) -> "TurnPermissionsOverride":
        return cls(TurnPermissionsOverrideKind.Preserve, None)

    @classmethod
    def legacy_sandbox(cls, profile: Any) -> "TurnPermissionsOverride":
        return cls(TurnPermissionsOverrideKind.LegacySandbox, profile)


@dataclass(eq=True)
class ThreadChannelState:
    active: bool = False
    receiver: Optional[Any] = None
    input_state: Optional[Any] = None
    pending_requests: List[Any] = field(default_factory=list)
    session: Optional[Any] = None


@dataclass(eq=True)
class ThreadRoutingState:
    active_thread_id: Optional[str] = None
    primary_thread_id: Optional[str] = None
    pending_shutdown_exit_thread_id: Optional[str] = None
    active_thread_rx: Optional[Any] = None
    thread_event_channels: Dict[str, ThreadChannelState] = field(default_factory=dict)
    listener_tasks: Dict[str, Any] = field(default_factory=dict)
    pending_primary_events: List[Tuple[str, Any]] = field(default_factory=list)
    side_threads: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    info_messages: List[str] = field(default_factory=list)


@dataclass(frozen=True, eq=True)
class ThreadRoutingPlan:
    action: str
    thread_id: Optional[str] = None
    target_thread_id: Optional[str] = None
    updates: Tuple[Tuple[str, Any], ...] = ()
    app_server_call: Optional[Tuple[str, Any]] = None
    error_message: Optional[str] = None
    info_message: Optional[str] = None
    schedule_frame: bool = False


def _selection_kind(selection: Any) -> str:
    if isinstance(selection, SessionSelection):
        kind = selection.kind
    elif isinstance(selection, dict):
        kind = selection.get("kind")
    else:
        kind = getattr(selection, "kind", selection)
    name = getattr(kind, "name", None)
    if name in {"StartFresh", "Exit", "Resume"}:
        return {
            "StartFresh": SessionSelectionKind.StartFresh,
            "Exit": SessionSelectionKind.Exit,
            "Resume": SessionSelectionKind.Resume,
        }[name]
    return str(kind)


def _is_thread_closed_notification(notification: Any) -> bool:
    if isinstance(notification, ThreadClosedNotification):
        return True
    if isinstance(notification, dict):
        kind = notification.get("type") or notification.get("kind")
        return kind in {"thread_closed", "ThreadClosed", "thread/closed"}
    kind = getattr(notification, "kind", None)
    if isinstance(kind, str):
        return kind in {"thread_closed", "ThreadClosed", "thread/closed"}
    return notification.__class__.__name__ in {"ThreadClosed", "ThreadClosedNotification"}


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def should_wait_for_initial_session(session_selection: Any) -> bool:
    return _selection_kind(session_selection) in {
        SessionSelectionKind.StartFresh,
        SessionSelectionKind.Exit,
    }


def should_prompt_for_paused_goal_after_startup_resume(
    session_selection: Any,
    initial_prompt: Optional[str],
    initial_images: Any,
) -> bool:
    return (
        _selection_kind(session_selection) == SessionSelectionKind.Resume
        and initial_prompt is None
        and len(initial_images) == 0
    )


def should_handle_active_thread_events(
    waiting_for_initial_session_configured: bool,
    has_active_thread_receiver: bool,
) -> bool:
    return has_active_thread_receiver and not waiting_for_initial_session_configured


def should_stop_waiting_for_initial_session(
    waiting_for_initial_session_configured: bool,
    primary_thread_id: Optional[str],
) -> bool:
    return waiting_for_initial_session_configured and primary_thread_id is not None


def active_non_primary_shutdown_target(
    notification: Any,
    active_thread_id: Optional[str],
    primary_thread_id: Optional[str],
    pending_shutdown_exit_thread_id: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """Return failover target for unexpected non-primary thread shutdowns."""

    if not _is_thread_closed_notification(notification):
        return None
    if active_thread_id is None or primary_thread_id is None:
        return None
    if pending_shutdown_exit_thread_id == active_thread_id:
        return None
    if active_thread_id == primary_thread_id:
        return None
    return active_thread_id, primary_thread_id


def ensure_thread_channel(state: ThreadRoutingState, thread_id: str) -> ThreadChannelState:
    if thread_id not in state.thread_event_channels:
        state.thread_event_channels[thread_id] = ThreadChannelState()
    return state.thread_event_channels[thread_id]


def abort_thread_event_listener(state: ThreadRoutingState, thread_id: str) -> ThreadRoutingPlan:
    handle = state.listener_tasks.pop(thread_id, None)
    return ThreadRoutingPlan(
        action="abort_thread_event_listener",
        thread_id=thread_id,
        updates=(("aborted", handle is not None),),
    )


def abort_all_thread_event_listeners(state: ThreadRoutingState) -> ThreadRoutingPlan:
    aborted = tuple(state.listener_tasks.keys())
    state.listener_tasks.clear()
    return ThreadRoutingPlan(action="abort_all_thread_event_listeners", updates=(("aborted", aborted),))


def activate_thread_channel(state: ThreadRoutingState, thread_id: str) -> ThreadRoutingPlan:
    if state.active_thread_id is not None:
        return ThreadRoutingPlan(action="activate_thread_channel_skipped", thread_id=thread_id)
    channel = ensure_thread_channel(state, thread_id)
    channel.active = True
    receiver = channel.receiver
    channel.receiver = None
    state.active_thread_id = thread_id
    state.active_thread_rx = receiver
    return ThreadRoutingPlan(
        action="activate_thread_channel",
        thread_id=thread_id,
        updates=(("active", True), ("receiver_taken", receiver is not None), ("refresh_pending_thread_approvals", True)),
    )


def store_active_thread_receiver(state: ThreadRoutingState, input_state: Any = None) -> ThreadRoutingPlan:
    active_id = state.active_thread_id
    if active_id is None:
        return ThreadRoutingPlan(action="store_active_thread_receiver_skipped")
    channel = ensure_thread_channel(state, active_id)
    receiver = state.active_thread_rx
    state.active_thread_rx = None
    channel.active = False
    channel.input_state = input_state
    if receiver is not None:
        channel.receiver = receiver
    return ThreadRoutingPlan(
        action="store_active_thread_receiver",
        thread_id=active_id,
        updates=(("active", False), ("receiver_stored", receiver is not None), ("input_state", input_state)),
    )


def clear_active_thread(state: ThreadRoutingState) -> ThreadRoutingPlan:
    active_id = state.active_thread_id
    if active_id is not None and active_id in state.thread_event_channels:
        state.thread_event_channels[active_id].active = False
    state.active_thread_id = None
    state.active_thread_rx = None
    return ThreadRoutingPlan(
        action="clear_active_thread",
        thread_id=active_id,
        updates=(("refresh_pending_thread_approvals", True),),
    )


def shutdown_current_thread_plan(state: ThreadRoutingState, displayed_thread_id: Optional[str]) -> ThreadRoutingPlan:
    if displayed_thread_id is None:
        return ThreadRoutingPlan(action="shutdown_current_thread_skipped")
    state.pending_shutdown_exit_thread_id = None
    abort_thread_event_listener(state, displayed_thread_id)
    return ThreadRoutingPlan(
        action="shutdown_current_thread",
        thread_id=displayed_thread_id,
        app_server_call=("thread_unsubscribe", displayed_thread_id),
        updates=(("pending_rollback", None), ("listener_aborted", displayed_thread_id)),
    )


def submit_active_thread_op_plan(state: ThreadRoutingState, op: Any) -> ThreadRoutingPlan:
    if state.active_thread_id is None:
        message = "No active thread is available."
        state.errors.append(message)
        return ThreadRoutingPlan(action="submit_active_thread_op_skipped", error_message=message)
    return ThreadRoutingPlan(
        action="submit_thread_op",
        thread_id=state.active_thread_id,
        app_server_call=("submit_thread_op", {"thread_id": state.active_thread_id, "op": op}),
    )


def enqueue_primary_thread_notification(state: ThreadRoutingState, notification: Any) -> ThreadRoutingPlan:
    if state.primary_thread_id is not None:
        return ThreadRoutingPlan(
            action="enqueue_thread_notification",
            thread_id=state.primary_thread_id,
            updates=(("notification", notification),),
        )
    state.pending_primary_events.append(("notification", notification))
    return ThreadRoutingPlan(action="buffer_primary_notification", updates=(("pending_primary_events", len(state.pending_primary_events)),))


def enqueue_primary_thread_request(state: ThreadRoutingState, request: Any) -> ThreadRoutingPlan:
    if state.primary_thread_id is not None:
        return ThreadRoutingPlan(
            action="enqueue_thread_request",
            thread_id=state.primary_thread_id,
            updates=(("request", request),),
        )
    state.pending_primary_events.append(("request", request))
    return ThreadRoutingPlan(action="buffer_primary_request", updates=(("pending_primary_events", len(state.pending_primary_events)),))


def pending_inactive_thread_requests(state: ThreadRoutingState) -> List[Tuple[str, Any]]:
    requests = []
    for thread_id, channel in state.thread_event_channels.items():
        if thread_id == state.active_thread_id:
            continue
        for request in channel.pending_requests:
            requests.append((thread_id, request))
    return requests


def should_refresh_snapshot_session(thread_id: str, is_replay_only: bool, snapshot: Any, side_threads: Any = ()) -> bool:
    if is_replay_only or thread_id in side_threads:
        return False
    session = _get_attr_or_key(snapshot, "session")
    if session is None:
        return True
    model = str(_get_attr_or_key(session, "model", "")).strip()
    rollout_path = _get_attr_or_key(session, "rollout_path")
    return model == "" or rollout_path is None


def active_thread_event_plan(state: ThreadRoutingState, event: Any) -> ThreadRoutingPlan:
    notification = event.get("notification") if isinstance(event, dict) else _get_attr_or_key(event, "notification")
    pending_shutdown_exit_completed = (
        _is_thread_closed_notification(notification)
        and state.pending_shutdown_exit_thread_id == state.active_thread_id
    )
    target = active_non_primary_shutdown_target(
        notification,
        state.active_thread_id,
        state.primary_thread_id,
        state.pending_shutdown_exit_thread_id,
    )
    if target is not None:
        closed_thread_id, primary_thread_id = target
        info = "Agent thread {0} closed. Switched back to main thread.".format(closed_thread_id)
        state.info_messages.append(info)
        return ThreadRoutingPlan(
            action="failover_to_primary_thread",
            thread_id=closed_thread_id,
            target_thread_id=primary_thread_id,
            info_message=info,
            updates=(("mark_agent_picker_thread_closed", closed_thread_id),),
        )
    if pending_shutdown_exit_completed:
        state.pending_shutdown_exit_thread_id = None
    return ThreadRoutingPlan(
        action="handle_thread_event_now",
        thread_id=state.active_thread_id,
        updates=(("pending_shutdown_exit_thread_id", state.pending_shutdown_exit_thread_id),),
    )


def turn_permissions_override_from_config(
    config: Any,
    active_permission_profile: Optional[Any],
    runtime_permission_profile_override: Optional[Any] = None,
) -> TurnPermissionsOverride:
    """Port Rust test-covered turn-permission override selection."""

    if active_permission_profile is not None:
        profile_id = _get_attr_or_key(active_permission_profile, "id", active_permission_profile)
        return TurnPermissionsOverride.active_profile(profile_id)
    if runtime_permission_profile_override is None:
        return TurnPermissionsOverride.preserve()
    effective = _get_attr_or_key(config, "effective_permission_profile", runtime_permission_profile_override)
    if callable(effective):
        effective = effective()
    return TurnPermissionsOverride.legacy_sandbox(effective)


async def config_with_workspace_profile(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    return {"default_permissions": "workspace", "permission_profile": "workspace"}


async def turn_permissions_use_active_profile_when_available(*_args: Any, **_kwargs: Any) -> TurnPermissionsOverride:
    return turn_permissions_override_from_config({}, "workspace", None)


async def turn_permissions_preserve_server_snapshot_without_local_override(*_args: Any, **_kwargs: Any) -> TurnPermissionsOverride:
    return turn_permissions_override_from_config({}, None, None)


async def turn_permissions_send_legacy_sandbox_for_local_override(*_args: Any, **_kwargs: Any) -> TurnPermissionsOverride:
    return turn_permissions_override_from_config({"effective_permission_profile": "workspace_write"}, None, "workspace_write")


__all__ = [
    "RUST_MODULE",
    "SessionSelection",
    "SessionSelectionKind",
    "ThreadChannelState",
    "ThreadClosedNotification",
    "ThreadRoutingPlan",
    "ThreadRoutingState",
    "TurnPermissionsOverride",
    "TurnPermissionsOverrideKind",
    "abort_all_thread_event_listeners",
    "abort_thread_event_listener",
    "activate_thread_channel",
    "active_non_primary_shutdown_target",
    "active_thread_event_plan",
    "clear_active_thread",
    "config_with_workspace_profile",
    "enqueue_primary_thread_notification",
    "enqueue_primary_thread_request",
    "ensure_thread_channel",
    "pending_inactive_thread_requests",
    "should_handle_active_thread_events",
    "should_prompt_for_paused_goal_after_startup_resume",
    "should_refresh_snapshot_session",
    "should_stop_waiting_for_initial_session",
    "should_wait_for_initial_session",
    "shutdown_current_thread_plan",
    "store_active_thread_receiver",
    "submit_active_thread_op_plan",
    "turn_permissions_override_from_config",
    "turn_permissions_preserve_server_snapshot_without_local_override",
    "turn_permissions_send_legacy_sandbox_for_local_override",
    "turn_permissions_use_active_profile_when_available",
]
