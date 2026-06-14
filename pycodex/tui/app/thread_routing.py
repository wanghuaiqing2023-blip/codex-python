"""Thread routing predicates for Rust ``codex-tui::app::thread_routing``.

Upstream source: ``codex/codex-rs/tui/src/app/thread_routing.rs``.

The Rust module is mostly App/AppServer routing glue.  This Python slice ports
small module-owned routing predicates and keeps submission/replay/runtime paths
as explicit ``not_ported`` boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::thread_routing",
    source="codex/codex-rs/tui/src/app/thread_routing.rs",
)


class SessionSelectionKind(str, Enum):
    StartFresh = "start_fresh"
    Exit = "exit"
    Resume = "resume"
    Other = "other"


@dataclass(frozen=True)
class SessionSelection:
    kind: SessionSelectionKind | str
    payload: Any | None = None

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
    thread_id: str | None = None


def _selection_kind(selection: Any) -> str:
    if isinstance(selection, SessionSelection):
        kind = selection.kind
    elif isinstance(selection, dict):
        kind = selection.get("kind")
    else:
        kind = getattr(selection, "kind", selection)
    if isinstance(kind, SessionSelectionKind):
        return kind.value
    name = getattr(kind, "name", None)
    if name in {"StartFresh", "Exit", "Resume"}:
        return {
            "StartFresh": SessionSelectionKind.StartFresh.value,
            "Exit": SessionSelectionKind.Exit.value,
            "Resume": SessionSelectionKind.Resume.value,
        }[name]
    return str(kind)


def _is_thread_closed_notification(notification: Any) -> bool:
    if isinstance(notification, ThreadClosedNotification):
        return True
    if isinstance(notification, dict):
        kind = notification.get("type") or notification.get("kind")
        return kind in {"thread_closed", "ThreadClosed", "thread/closed"}
    return notification.__class__.__name__ in {"ThreadClosed", "ThreadClosedNotification"}


def should_wait_for_initial_session(session_selection: Any) -> bool:
    return _selection_kind(session_selection) in {
        SessionSelectionKind.StartFresh.value,
        SessionSelectionKind.Exit.value,
    }


def should_prompt_for_paused_goal_after_startup_resume(
    session_selection: Any,
    initial_prompt: str | None,
    initial_images: list[Any] | tuple[Any, ...],
) -> bool:
    return (
        _selection_kind(session_selection) == SessionSelectionKind.Resume.value
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
    primary_thread_id: str | None,
) -> bool:
    return waiting_for_initial_session_configured and primary_thread_id is not None


def active_non_primary_shutdown_target(
    notification: Any,
    active_thread_id: str | None,
    primary_thread_id: str | None,
    pending_shutdown_exit_thread_id: str | None = None,
) -> tuple[str, str] | None:
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


async def config_with_workspace_profile(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_routing.config_with_workspace_profile test fixture is not ported")


async def turn_permissions_use_active_profile_when_available(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_routing turn permission App/Config integration is not ported")


async def turn_permissions_preserve_server_snapshot_without_local_override(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_routing turn permission App/Config integration is not ported")


async def turn_permissions_send_legacy_sandbox_for_local_override(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::thread_routing turn permission App/Config integration is not ported")


__all__ = [
    "RUST_MODULE",
    "SessionSelection",
    "SessionSelectionKind",
    "ThreadClosedNotification",
    "active_non_primary_shutdown_target",
    "config_with_workspace_profile",
    "should_handle_active_thread_events",
    "should_prompt_for_paused_goal_after_startup_resume",
    "should_stop_waiting_for_initial_session",
    "should_wait_for_initial_session",
    "turn_permissions_preserve_server_snapshot_without_local_override",
    "turn_permissions_send_legacy_sandbox_for_local_override",
    "turn_permissions_use_active_profile_when_available",
]
