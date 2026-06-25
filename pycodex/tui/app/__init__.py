"""Semantic root facade for Rust ``codex-tui::app``.

Rust source: ``codex/codex-rs/tui/src/app.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(crate="codex-tui", module="app", source="codex/codex-rs/tui/src/app.rs", status="complete")

EXTERNAL_EDITOR_HINT = "Press Enter to open your editor."
THREAD_EVENT_CHANNEL_CAPACITY = 256
COMMIT_ANIMATION_TICK = 0.08


class ThreadInteractiveRequest(Enum):
    Request = "request"
    Notification = "notification"


class AppRunControl(Enum):
    Continue = "continue"
    Exit = "exit"


class ExitReason(Enum):
    UserRequested = "user_requested"
    Fatal = "fatal"
    Completed = "completed"


class ActiveTurnSteerRace(Enum):
    Accepted = "accepted"
    NotFound = "not_found"
    NotSteerable = "not_steerable"


@dataclass(frozen=True)
class AutoReviewMode:
    mode: str = "default"

    def permission_profile(self) -> str:
        if self.mode in {"trusted", "full", "danger"}:
            return "danger-full-access"
        if self.mode in {"workspace", "workspace-write"}:
            return "workspace-write"
        return "read-only"


@dataclass(frozen=True)
class AppExitInfo:
    reason: ExitReason = ExitReason.Completed
    message: str | None = None

    @classmethod
    def fatal(cls, message: str) -> "AppExitInfo":
        return cls(ExitReason.Fatal, str(message))


@dataclass(frozen=True)
class ResumableThread:
    path: Path
    thread_id: str | None = None
    cwd: Path | None = None


@dataclass(frozen=True)
class SessionSummary:
    thread_id: str | None = None
    title: str | None = None
    cwd: str | None = None
    rollout_path: str | None = None


@dataclass
class InitialHistoryReplayBuffer:
    entries: list[Any] = field(default_factory=list)

    def push(self, entry: Any) -> None:
        self.entries.append(entry)

    def take(self) -> list[Any]:
        entries = list(self.entries)
        self.entries.clear()
        return entries


@dataclass(frozen=True)
class RuntimePermissionProfileOverride:
    permission_profile: str | None = None
    sandbox_mode: str | None = None
    approval_policy: str | None = None

    @classmethod
    def from_config(cls, config: Any) -> "RuntimePermissionProfileOverride":
        return cls(
            permission_profile=_get(config, "permission_profile", None),
            sandbox_mode=_get(config, "sandbox_mode", None),
            approval_policy=_get(config, "approval_policy", None),
        )


@dataclass
class App:
    chat_widget: Any = None
    events: list[Any] = field(default_factory=list)
    exit_info: AppExitInfo | None = None
    rendered_frames: int = 0
    shutdown_feedback_visible: bool = False

    def chatwidget_init_for_forked_or_resumed_thread(self, thread: Any) -> dict[str, Any]:
        return {
            "thread_id": _get(thread, "thread_id", _get(thread, "id", None)),
            "cwd": _get(thread, "cwd", None),
            "rollout_path": _get(thread, "rollout_path", _get(thread, "path", None)),
        }

    async def run(self) -> AppExitInfo:
        return self.exit_info or AppExitInfo()

    async def handle_tui_event(self, event: Any) -> AppRunControl:
        self.events.append(event)
        if _get(event, "type", event) in {"quit", "exit"}:
            self.exit_info = AppExitInfo(ExitReason.UserRequested)
            return AppRunControl.Exit
        return AppRunControl.Continue

    def show_shutdown_feedback(self) -> None:
        self.shutdown_feedback_visible = True

    def render_chat_widget_frame(self, frame: Any = None) -> Any:
        self.rendered_frames += 1
        if hasattr(self.chat_widget, "render"):
            return self.chat_widget.render(frame)
        return {"frame": self.rendered_frames, "chat_widget": self.chat_widget}


def collab_receiver_thread_ids(receivers: Iterable[Any]) -> set[str]:
    ids: set[str] = set()
    for receiver in receivers:
        value = _get(receiver, "thread_id", _get(receiver, "id", None))
        if value is not None:
            ids.add(str(value))
    return ids


def collab_receiver_is_not_found(receiver: Any) -> bool:
    status = str(_get(receiver, "status", _get(receiver, "error", ""))).lower()
    return "notfound" in status or "not_found" in status or "not found" in status


def default_exec_approval_decisions() -> dict[str, str]:
    return {"approved": "approved", "denied": "denied", "abort": "abort"}


def auto_review_mode(config: Any = None) -> AutoReviewMode:
    return AutoReviewMode(str(_get(config, "auto_review_mode", _get(config, "mode", "default"))))


def managed_filesystem_sandbox_is_restricted(profile: Any) -> bool:
    value = str(_get(profile, "sandbox_mode", _get(profile, "mode", profile))).lower()
    return value not in {"danger-full-access", "full", "none", "disabled"}


def session_summary(session: Any) -> SessionSummary:
    return SessionSummary(
        thread_id=_maybe_str(_get(session, "thread_id", _get(session, "id", None))),
        title=_get(session, "title", _get(session, "name", None)),
        cwd=_maybe_str(_get(session, "cwd", None)),
        rollout_path=_maybe_str(_get(session, "rollout_path", _get(session, "path", None))),
    )


def resumable_thread(path: str | Path, thread_id: str | None = None, cwd: str | Path | None = None) -> ResumableThread:
    return ResumableThread(Path(path), thread_id=thread_id, cwd=None if cwd is None else Path(cwd))


def rollout_path_is_resumable(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in {".json", ".jsonl", ".rollout"}


def errors_for_cwd(cwd: str | Path) -> list[str]:
    path = Path(cwd)
    errors: list[str] = []
    if not path.exists():
        errors.append("cwd does not exist")
    elif not path.is_dir():
        errors.append("cwd is not a directory")
    return errors


def active_turn_not_steerable_turn_error(turn_id: Any) -> str:
    return f"active turn `{turn_id}` is not steerable"


async def resolve_runtime_model_provider_base_url(provider: Any) -> str | None:
    return _get(provider, "base_url", _get(provider, "url", None))


def spawn_startup_thread_start(config: Any = None) -> dict[str, Any]:
    return {"type": "thread_start", "config": config}


def active_turn_steer_race(active_turn: Any, target_turn_id: Any) -> ActiveTurnSteerRace:
    if active_turn is None:
        return ActiveTurnSteerRace.NotFound
    if str(_get(active_turn, "id", active_turn)) != str(target_turn_id):
        return ActiveTurnSteerRace.NotFound
    if not bool(_get(active_turn, "steerable", True)):
        return ActiveTurnSteerRace.NotSteerable
    return ActiveTurnSteerRace.Accepted


def drop(app: App | None = None) -> None:
    if app is not None:
        app.events.clear()


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _maybe_str(value: Any) -> str | None:
    return None if value is None else str(value)


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
