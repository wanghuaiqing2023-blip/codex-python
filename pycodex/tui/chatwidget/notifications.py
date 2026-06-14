"""Desktop notification coalescing for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/notifications.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .._porting import RustTuiModule
from ..text_formatting import truncate_text

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::notifications",
    source="codex/codex-rs/tui/src/chatwidget/notifications.rs",
)

AGENT_NOTIFICATION_PREVIEW_GRAPHEMES = 200
APPROVAL_NOTIFICATION_PREVIEW_GRAPHEMES = 30


@dataclass(frozen=True)
class Notifications:
    """Semantic model for Rust ``Notifications`` settings used by this module."""

    enabled: bool | None = True
    custom_allowed: frozenset[str] | None = None

    @classmethod
    def enabled_setting(cls, enabled: bool) -> "Notifications":
        return cls(enabled=bool(enabled), custom_allowed=None)

    @classmethod
    def custom(cls, allowed: Iterable[str]) -> "Notifications":
        return cls(enabled=None, custom_allowed=frozenset(str(item) for item in allowed))

    @classmethod
    def coerce(cls, settings: "Notifications | bool | Iterable[str] | Mapping[str, object]") -> "Notifications":
        if isinstance(settings, Notifications):
            return settings
        if isinstance(settings, bool):
            return cls.enabled_setting(settings)
        if isinstance(settings, Mapping):
            if "custom_allowed" in settings:
                value = settings["custom_allowed"]
                if value is None:
                    return cls.enabled_setting(bool(settings.get("enabled", True)))
                return cls.custom(str(item) for item in value)  # type: ignore[union-attr]
            if "enabled" in settings:
                return cls.enabled_setting(bool(settings["enabled"]))
        return cls.custom(str(item) for item in settings)


@dataclass(frozen=True)
class ToolRequestUserInputQuestion:
    """Minimal semantic boundary for Rust ``ToolRequestUserInputQuestion``."""

    header: str = ""
    question: str = ""


@dataclass(frozen=True)
class Notification:
    """Semantic model for Rust ``chatwidget::notifications::Notification``."""

    kind: str
    response: str = ""
    command: str = ""
    cwd: Path | None = None
    changes: tuple[Path, ...] = ()
    server_name: str = ""
    title: str = ""

    @classmethod
    def agent_turn_complete(cls, response: str) -> "Notification":
        return cls(kind="agent_turn_complete", response=response)

    @classmethod
    def exec_approval_requested(cls, command: str) -> "Notification":
        return cls(kind="exec_approval_requested", command=command)

    @classmethod
    def edit_approval_requested(cls, cwd: str | Path, changes: Sequence[str | Path]) -> "Notification":
        return cls(
            kind="edit_approval_requested",
            cwd=Path(cwd),
            changes=tuple(Path(change) for change in changes),
        )

    @classmethod
    def elicitation_requested(cls, server_name: str) -> "Notification":
        return cls(kind="elicitation_requested", server_name=server_name)

    @classmethod
    def plan_mode_prompt(cls, title: str) -> "Notification":
        return cls(kind="plan_mode_prompt", title=title)

    def display(self) -> str:
        if self.kind == "agent_turn_complete":
            return self.agent_turn_preview(self.response) or "Agent turn complete"
        if self.kind == "exec_approval_requested":
            return (
                "Approval requested: "
                + truncate_text(self.command, APPROVAL_NOTIFICATION_PREVIEW_GRAPHEMES)
            )
        if self.kind == "edit_approval_requested":
            if len(self.changes) == 1:
                cwd = self.cwd if self.cwd is not None else Path()
                target = _display_path_for(self.changes[0], cwd)
            else:
                target = f"{len(self.changes)} files"
            return f"Codex wants to edit {target}"
        if self.kind == "elicitation_requested":
            return f"Approval requested by {self.server_name}"
        if self.kind == "plan_mode_prompt":
            return f"Plan mode prompt: {self.title}"
        raise ValueError(f"unknown notification kind: {self.kind}")

    def type_name(self) -> str:
        if self.kind == "agent_turn_complete":
            return "agent-turn-complete"
        if self.kind in {
            "exec_approval_requested",
            "edit_approval_requested",
            "elicitation_requested",
        }:
            return "approval-requested"
        if self.kind == "plan_mode_prompt":
            return "plan-mode-prompt"
        raise ValueError(f"unknown notification kind: {self.kind}")

    def priority(self) -> int:
        return 0 if self.kind == "agent_turn_complete" else 1

    def allowed_for(self, settings: Notifications | bool | Iterable[str] | Mapping[str, object]) -> bool:
        coerced = Notifications.coerce(settings)
        if coerced.custom_allowed is None:
            return bool(coerced.enabled)
        return self.type_name() in coerced.custom_allowed

    @staticmethod
    def agent_turn_preview(response: str) -> str | None:
        normalized = " ".join(response.split()).strip()
        if not normalized:
            return None
        return truncate_text(normalized, AGENT_NOTIFICATION_PREVIEW_GRAPHEMES)

    @staticmethod
    def user_input_request_summary(
        questions: Sequence[ToolRequestUserInputQuestion | Mapping[str, object]],
    ) -> str | None:
        if not questions:
            return None
        first = questions[0]
        if isinstance(first, Mapping):
            header = str(first.get("header", ""))
            question = str(first.get("question", ""))
        else:
            header = first.header
            question = first.question
        summary = header.strip() or question.strip()
        if not summary:
            return None
        return truncate_text(summary, APPROVAL_NOTIFICATION_PREVIEW_GRAPHEMES)


@dataclass
class NotificationCoalescer:
    """Small semantic stand-in for the ``ChatWidget`` pending-notification fields."""

    settings: Notifications = field(default_factory=lambda: Notifications.enabled_setting(True))
    pending_notification: Notification | None = None
    redraw_requests: int = 0

    def notify(self, notification: Notification) -> bool:
        if not notification.allowed_for(self.settings):
            return False
        if (
            self.pending_notification is not None
            and self.pending_notification.priority() > notification.priority()
        ):
            return False
        self.pending_notification = notification
        self.redraw_requests += 1
        return True

    def maybe_post_pending_notification(self) -> str | None:
        if self.pending_notification is None:
            return None
        notification = self.pending_notification
        self.pending_notification = None
        return notification.display()


def _display_path_for(path: Path, cwd: Path) -> str:
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(cwd))
    except ValueError:
        return str(path)


__all__ = [
    "AGENT_NOTIFICATION_PREVIEW_GRAPHEMES",
    "APPROVAL_NOTIFICATION_PREVIEW_GRAPHEMES",
    "Notification",
    "NotificationCoalescer",
    "Notifications",
    "RUST_MODULE",
    "ToolRequestUserInputQuestion",
]
