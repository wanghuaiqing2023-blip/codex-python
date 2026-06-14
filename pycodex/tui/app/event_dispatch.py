"""Semantic model for Rust ``codex-tui::app::event_dispatch``.

This module is intentionally not a full port of the TUI event loop.  It
captures small, module-owned decision points that can be represented without
ratatui/app-server runtime objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .._porting import RustTuiModule, not_ported


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::event_dispatch",
    source="codex/codex-rs/tui/src/app/event_dispatch.rs",
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
    reason: ExitReason | str | None = None

    @classmethod
    def exit(cls, reason: ExitReason | str = ExitReason.UserRequested) -> "AppRunControl":
        return cls("exit", reason)

    @classmethod
    def continue_(cls) -> "AppRunControl":
        return cls("continue", None)


@dataclass(eq=True)
class EventDispatchState:
    """Minimal mutable App state touched by Rust ``handle_exit_mode``."""

    active_thread_id: str | None = None
    chat_widget_thread_id: str | None = None
    pending_shutdown_exit_thread_id: str | None = None


@dataclass(frozen=True, eq=True)
class ExitModePlan:
    """Observable decisions made by ``handle_exit_mode``.

    Rust performs the actual async shutdown inline.  Python exposes that as a
    plan so callers can keep the same state-transition contract without
    pretending to own the app-server runtime.
    """

    run_control: AppRunControl
    shutdown_thread_id: str | None
    timeout_seconds: float | None


def _coerce_exit_mode(mode: ExitMode | str) -> ExitMode:
    if isinstance(mode, ExitMode):
        return mode
    normalized = mode.replace("-", "_").lower()
    for candidate in ExitMode:
        if normalized in {candidate.value, candidate.name.lower()}:
            return candidate
    raise ValueError(f"unknown ExitMode: {mode!r}")


def handle_exit_mode_plan(state: EventDispatchState, mode: ExitMode | str) -> ExitModePlan:
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


async def handle_event(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("app::event_dispatch::handle_event requires the full TUI event loop")


async def handle_exit_mode(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("app::event_dispatch::handle_exit_mode requires App and AppServer runtime objects; use handle_exit_mode_plan for semantic planning")


__all__ = [
    "RUST_MODULE",
    "SHUTDOWN_FIRST_EXIT_TIMEOUT",
    "AppRunControl",
    "EventDispatchState",
    "ExitMode",
    "ExitModePlan",
    "ExitReason",
    "handle_event",
    "handle_exit_mode",
    "handle_exit_mode_plan",
]
