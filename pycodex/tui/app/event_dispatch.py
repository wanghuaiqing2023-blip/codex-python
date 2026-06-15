"""Semantic model for Rust ``codex-tui::app::event_dispatch``.

This module is intentionally not a full port of the TUI event loop.  It
captures small, module-owned decision points that can be represented without
ratatui/app-server runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Tuple, Union

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::event_dispatch",
    source="codex/codex-rs/tui/src/app/event_dispatch.rs",
    status="complete",
)

# Rust: const SHUTDOWN_FIRST_EXIT_TIMEOUT: Duration = Duration::from_secs(2)
SHUTDOWN_FIRST_EXIT_TIMEOUT = 2.0


class ExitMode(str, Enum):
    """Semantic counterpart of Rust ``ExitMode`` for this module slice."""

    ShutdownFirst = "shutdown_first"
    Immediate = "immediate"


class ExitReason(str, Enum):
    """Semantic counterpart of Rust ``ExitReason`` values used here."""

    UserRequested = "user_requested"


@dataclass(frozen=True, eq=True)
class AppRunControl:
    """Semantic counterpart for the Rust dispatcher return control."""

    kind: str
    reason: Optional[Union[ExitReason, str]] = None

    @classmethod
    def exit(cls, reason: Union[ExitReason, str] = ExitReason.UserRequested) -> "AppRunControl":
        return cls("exit", reason)

    @classmethod
    def continue_(cls) -> "AppRunControl":
        return cls("continue", None)


@dataclass(eq=True)
class EventDispatchState:
    """Minimal mutable App state touched by Rust ``handle_exit_mode``."""

    active_thread_id: Optional[str] = None
    chat_widget_thread_id: Optional[str] = None
    pending_shutdown_exit_thread_id: Optional[str] = None


@dataclass(frozen=True, eq=True)
class ExitModePlan:
    """Observable decisions made by ``handle_exit_mode``.

    Rust performs the actual async shutdown inline.  Python exposes that as a
    plan so callers can keep the same state-transition contract without
    pretending to own the app-server runtime.
    """

    run_control: AppRunControl
    shutdown_thread_id: Optional[str]
    timeout_seconds: Optional[float]


@dataclass(frozen=True, eq=True)
class EventDispatchPlan:
    """Semantic dispatch result for one Rust ``AppEvent``.

    Rust ``handle_event`` is deliberately a central router: most branches
    delegate to other ``app::*`` modules, mutate widgets, or call app-server
    runtime APIs.  Python keeps that module boundary by exposing the router's
    own observable decision as a stable plan instead of pretending to execute
    those neighboring side effects here.
    """

    action: str
    run_control: AppRunControl = field(default_factory=AppRunControl.continue_)
    updates: Tuple[Tuple[str, Any], ...] = ()
    messages: Tuple[str, ...] = ()
    schedule_frame: bool = False
    enter_alt_screen: bool = False
    forward_event: Optional[str] = None
    exit_mode_plan: Optional[ExitModePlan] = None


def _coerce_exit_mode(mode: Union[ExitMode, str]) -> ExitMode:
    if isinstance(mode, ExitMode):
        return mode
    normalized = mode.replace("-", "_").lower()
    for candidate in ExitMode:
        if normalized in {candidate.value, candidate.name.lower()}:
            return candidate
    raise ValueError("unknown ExitMode: {!r}".format(mode))


def handle_exit_mode_plan(state: EventDispatchState, mode: Union[ExitMode, str]) -> ExitModePlan:
    """Port the Rust ``handle_exit_mode`` state transition as a pure plan.

    Rust behavior:
    - ``ShutdownFirst`` chooses ``active_thread_id`` or falls back to the chat
      widget thread id, stores it as pending, waits up to two seconds when a
      thread exists, clears the pending marker, then exits as user requested.
    - ``Immediate`` clears the pending marker and exits as user requested
      without attempting shutdown.
    """

    exit_mode = _coerce_exit_mode(mode)
    if exit_mode is ExitMode.ShutdownFirst:
        shutdown_thread_id = state.active_thread_id or state.chat_widget_thread_id
        state.pending_shutdown_exit_thread_id = shutdown_thread_id
        timeout_seconds = SHUTDOWN_FIRST_EXIT_TIMEOUT if shutdown_thread_id is not None else None
        state.pending_shutdown_exit_thread_id = None
        return ExitModePlan(
            run_control=AppRunControl.exit(ExitReason.UserRequested),
            shutdown_thread_id=shutdown_thread_id,
            timeout_seconds=timeout_seconds,
        )

    state.pending_shutdown_exit_thread_id = None
    return ExitModePlan(
        run_control=AppRunControl.exit(ExitReason.UserRequested),
        shutdown_thread_id=None,
        timeout_seconds=None,
    )


def _camel_to_snake(value: str) -> str:
    out = []
    for index, char in enumerate(value):
        if char.isupper() and index and (not value[index - 1].isupper()):
            out.append("_")
        out.append(char.lower())
    return "".join(out).replace("__", "_")


def _event_variant(event: Any) -> str:
    if isinstance(event, str):
        return event
    if isinstance(event, dict):
        for key in ("variant", "type", "kind", "event"):
            value = event.get(key)
            if isinstance(value, str):
                return value
        if len(event) == 1:
            return next(iter(event.keys()))
    for attr in ("variant", "type", "kind", "event"):
        value = getattr(event, attr, None)
        if isinstance(value, str):
            return value
    return event.__class__.__name__


def _event_payload(event: Any) -> Any:
    if isinstance(event, dict):
        for key in ("payload", "data", "value"):
            if key in event:
                return event[key]
        if len(event) == 1:
            return next(iter(event.values()))
    return getattr(event, "payload", None)


def _payload_value(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _coerce_event_exit_mode(payload: Any) -> ExitMode:
    mode = _payload_value(payload, "mode", payload)
    if isinstance(mode, dict):
        mode = _payload_value(mode, "mode", ExitMode.ShutdownFirst)
    if mode is None:
        mode = ExitMode.ShutdownFirst
    return _coerce_exit_mode(mode)


def dispatch_event_plan(state: EventDispatchState, event: Any) -> EventDispatchPlan:
    """Return the Rust-style dispatch decision for one ``AppEvent``.

    The function accepts a lightweight event representation: a Rust variant
    name string, a ``{"Variant": payload}`` mapping, a mapping with
    ``variant``/``type``/``kind``, or an object with one of those attributes.
    """

    variant = _event_variant(event)
    payload = _event_payload(event)

    if variant == "NewSession":
        return EventDispatchPlan(
            action="start_fresh_session_with_summary_hint",
            updates=(("start_fresh_session", payload),),
            schedule_frame=True,
        )
    if variant == "StartupThreadStarted":
        return EventDispatchPlan(
            action="handle_startup_thread_started",
            updates=(("startup_thread_started", payload),),
            schedule_frame=True,
        )
    if variant == "ClearUi":
        return EventDispatchPlan(
            action="clear_ui_and_start_fresh_session",
            updates=(
                ("clear_terminal_ui", None),
                ("reset_app_ui_state_after_clear", None),
                ("start_fresh_session_with_summary_hint", payload),
            ),
            schedule_frame=True,
        )
    if variant == "RawOutputModeChanged":
        return EventDispatchPlan(
            action="apply_raw_output_mode",
            updates=(("raw_output_mode_changed", payload),),
            schedule_frame=True,
        )
    if variant == "ClearUiAndSubmitUserMessage":
        return EventDispatchPlan(
            action="clear_ui_and_submit_user_message",
            updates=(
                ("clear_terminal_ui", None),
                ("reset_app_ui_state_after_clear", None),
                ("create_initial_user_message", payload),
                ("submit_user_message", payload),
            ),
            schedule_frame=True,
        )

    history_actions = {
        "BeginInitialHistoryReplayBuffer": "begin_initial_history_replay_buffer",
        "BeginThreadSwitchHistoryReplayBuffer": "begin_thread_switch_history_replay_buffer",
        "InsertHistoryCell": "insert_history_cell",
        "EndInitialHistoryReplayBuffer": "end_initial_history_replay_buffer",
        "EndThreadSwitchHistoryReplayBuffer": "end_thread_switch_history_replay_buffer",
    }
    if variant in history_actions:
        return EventDispatchPlan(
            action=history_actions[variant],
            updates=((history_actions[variant], payload),),
            schedule_frame=variant.startswith("End"),
        )

    if variant == "Exit":
        exit_plan = handle_exit_mode_plan(state, _coerce_event_exit_mode(payload))
        updates = ()
        if exit_plan.shutdown_thread_id is not None:
            updates = (("show_shutdown_feedback", exit_plan.shutdown_thread_id),)
        return EventDispatchPlan(
            action="exit",
            run_control=exit_plan.run_control,
            updates=updates,
            exit_mode_plan=exit_plan,
        )
    if variant == "Logout":
        error = _payload_value(payload, "error", None)
        if error is not None:
            return EventDispatchPlan(
                action="logout_account_failed",
                run_control=AppRunControl.continue_(),
                updates=(("logout_error", error),),
                messages=(str(error),),
                schedule_frame=True,
            )
        exit_plan = handle_exit_mode_plan(state, ExitMode.ShutdownFirst)
        updates = (("logout", payload),)
        if exit_plan.shutdown_thread_id is not None:
            updates = updates + (("show_shutdown_feedback", exit_plan.shutdown_thread_id),)
        return EventDispatchPlan(
            action="logout_account_then_shutdown",
            run_control=exit_plan.run_control,
            updates=updates,
            exit_mode_plan=exit_plan,
        )
    if variant == "FatalExitRequest":
        reason = _payload_value(payload, "reason", _payload_value(payload, "message", "fatal_exit_request"))
        return EventDispatchPlan(
            action="fatal_exit_request",
            run_control=AppRunControl.exit("fatal:{0}".format(reason)),
            messages=(str(reason),),
        )

    delegated_actions = {
        "OpenUrlInBrowser": "open_url_in_browser",
        "OpenResumePicker": "open_resume_picker",
        "ResumeSessionByIdOrName": "resume_session_by_id_or_name",
        "ForkCurrentSession": "fork_current_session",
        "ConsolidateAgentMessage": "consolidate_agent_message",
        "ConsolidateProposedPlan": "consolidate_proposed_plan",
        "ApplyThreadRollback": "apply_thread_rollback",
        "StartCommitAnimation": "start_commit_animation",
        "StopCommitAnimation": "stop_commit_animation",
        "CommitTick": "commit_tick",
        "CodexOp": "handle_codex_op",
        "AppendMessageHistoryEntry": "append_message_history_entry",
        "PetSelected": "handle_pet_selected",
        "PetDisabled": "handle_pet_disabled",
        "PetPreviewRequested": "handle_pet_preview_requested",
        "PetPreviewLoaded": "handle_pet_preview_loaded",
        "PetSelectionLoaded": "handle_pet_selection_loaded",
        "ConfiguredPetLoaded": "handle_configured_pet_loaded",
        "KeyEvent": "handle_key_event",
        "Paste": "handle_paste",
        "Resize": "handle_resize",
        "Redraw": "redraw",
        "RequestRedraw": "request_redraw",
    }
    if variant in delegated_actions:
        return EventDispatchPlan(
            action=delegated_actions[variant],
            updates=((delegated_actions[variant], payload),),
            schedule_frame=True,
            forward_event=variant,
        )

    action = "handle_{0}".format(_camel_to_snake(variant))
    return EventDispatchPlan(
        action=action,
        updates=((action, payload),),
        schedule_frame=True,
        forward_event=variant,
    )


handle_event_plan = dispatch_event_plan


async def handle_event(state: EventDispatchState, event: Any) -> EventDispatchPlan:
    return dispatch_event_plan(state, event)


async def handle_exit_mode(state: EventDispatchState, mode: Union[ExitMode, str]) -> ExitModePlan:
    return handle_exit_mode_plan(state, mode)


__all__ = [
    "RUST_MODULE",
    "SHUTDOWN_FIRST_EXIT_TIMEOUT",
    "AppRunControl",
    "EventDispatchPlan",
    "EventDispatchState",
    "ExitMode",
    "ExitModePlan",
    "ExitReason",
    "dispatch_event_plan",
    "handle_event",
    "handle_event_plan",
    "handle_exit_mode",
    "handle_exit_mode_plan",
]
