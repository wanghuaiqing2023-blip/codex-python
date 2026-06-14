"""Python interface scaffold for Rust ``codex-tui::app``.

Upstream source: ``codex/codex-rs/tui/src/app.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="app", source="codex/codex-rs/tui/src/app.rs")

EXTERNAL_EDITOR_HINT: Any = None

THREAD_EVENT_CHANNEL_CAPACITY: Any = None

class ThreadInteractiveRequest(Enum):
    """Python boundary for Rust enum ``app::ThreadInteractiveRequest``."""
    UNPORTED = "unported"

def collab_receiver_thread_ids(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::collab_receiver_thread_ids``."""
    return not_ported(RUST_MODULE, "collab_receiver_thread_ids")

def collab_receiver_is_not_found(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::collab_receiver_is_not_found``."""
    return not_ported(RUST_MODULE, "collab_receiver_is_not_found")

def default_exec_approval_decisions(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::default_exec_approval_decisions``."""
    return not_ported(RUST_MODULE, "default_exec_approval_decisions")

@dataclass
class AutoReviewMode:
    """Python boundary for Rust ``app::AutoReviewMode``."""
    _payload: Any = None

    def permission_profile(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "AutoReviewMode.permission_profile")

def auto_review_mode(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::auto_review_mode``."""
    return not_ported(RUST_MODULE, "auto_review_mode")

def managed_filesystem_sandbox_is_restricted(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::managed_filesystem_sandbox_is_restricted``."""
    return not_ported(RUST_MODULE, "managed_filesystem_sandbox_is_restricted")

COMMIT_ANIMATION_TICK: Any = None

@dataclass
class AppExitInfo:
    """Python boundary for Rust ``app::AppExitInfo``."""
    _payload: Any = None

    def fatal(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "AppExitInfo.fatal")

class AppRunControl(Enum):
    """Python boundary for Rust enum ``app::AppRunControl``."""
    UNPORTED = "unported"

class ExitReason(Enum):
    """Python boundary for Rust enum ``app::ExitReason``."""
    UNPORTED = "unported"

def session_summary(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::session_summary``."""
    return not_ported(RUST_MODULE, "session_summary")

@dataclass
class ResumableThread:
    """Python boundary for Rust ``app::ResumableThread``."""
    _payload: Any = None

def resumable_thread(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::resumable_thread``."""
    return not_ported(RUST_MODULE, "resumable_thread")

def rollout_path_is_resumable(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::rollout_path_is_resumable``."""
    return not_ported(RUST_MODULE, "rollout_path_is_resumable")

def errors_for_cwd(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::errors_for_cwd``."""
    return not_ported(RUST_MODULE, "errors_for_cwd")

@dataclass
class SessionSummary:
    """Python boundary for Rust ``app::SessionSummary``."""
    _payload: Any = None

@dataclass
class InitialHistoryReplayBuffer:
    """Python boundary for Rust ``app::InitialHistoryReplayBuffer``."""
    _payload: Any = None

@dataclass
class App:
    """Python boundary for Rust ``app::App``."""
    _payload: Any = None

    def chatwidget_init_for_forked_or_resumed_thread(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "App.chatwidget_init_for_forked_or_resumed_thread")

    async def run(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "App.run")

    async def handle_tui_event(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "App.handle_tui_event")

    def show_shutdown_feedback(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "App.show_shutdown_feedback")

    def render_chat_widget_frame(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "App.render_chat_widget_frame")

@dataclass
class RuntimePermissionProfileOverride:
    """Python boundary for Rust ``app::RuntimePermissionProfileOverride``."""
    _payload: Any = None

    def from_config(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "RuntimePermissionProfileOverride.from_config")

def active_turn_not_steerable_turn_error(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::active_turn_not_steerable_turn_error``."""
    return not_ported(RUST_MODULE, "active_turn_not_steerable_turn_error")

async def resolve_runtime_model_provider_base_url(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::resolve_runtime_model_provider_base_url``."""
    return not_ported(RUST_MODULE, "resolve_runtime_model_provider_base_url")

def spawn_startup_thread_start(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::spawn_startup_thread_start``."""
    return not_ported(RUST_MODULE, "spawn_startup_thread_start")

class ActiveTurnSteerRace(Enum):
    """Python boundary for Rust enum ``app::ActiveTurnSteerRace``."""
    UNPORTED = "unported"

def active_turn_steer_race(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::active_turn_steer_race``."""
    return not_ported(RUST_MODULE, "active_turn_steer_race")

def drop(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``app::drop``."""
    return not_ported(RUST_MODULE, "drop")

__all__ = [
    "ActiveTurnSteerRace",
    "App",
    "AppExitInfo",
    "AppRunControl",
    "AutoReviewMode",
    "COMMIT_ANIMATION_TICK",
    "EXTERNAL_EDITOR_HINT",
    "ExitReason",
    "InitialHistoryReplayBuffer",
    "RUST_MODULE",
    "ResumableThread",
    "RuntimePermissionProfileOverride",
    "SessionSummary",
    "THREAD_EVENT_CHANNEL_CAPACITY",
    "ThreadInteractiveRequest",
    "active_turn_not_steerable_turn_error",
    "active_turn_steer_race",
    "auto_review_mode",
    "collab_receiver_is_not_found",
    "collab_receiver_thread_ids",
    "default_exec_approval_decisions",
    "drop",
    "errors_for_cwd",
    "managed_filesystem_sandbox_is_restricted",
    "resolve_runtime_model_provider_base_url",
    "resumable_thread",
    "rollout_path_is_resumable",
    "session_summary",
    "spawn_startup_thread_start",
]
