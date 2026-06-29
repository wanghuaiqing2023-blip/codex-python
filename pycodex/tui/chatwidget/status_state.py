"""Status indicator and terminal-title state for ``ChatWidget``.

Port of Rust ``codex-tui::chatwidget::status_state``.  This module is a pure
state container: no rendering or terminal side effects are modeled here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::status_state",
    source="codex/codex-rs/tui/src/chatwidget/status_state.rs",
    status="complete",
)

STATUS_DETAILS_DEFAULT_MAX_LINES = 4
GUARDIAN_REVIEW_DETAIL_PREFIX = "• "


@dataclass(eq=True)
class StatusIndicatorState:
    header: str
    details: str | None = None
    details_max_lines: int = STATUS_DETAILS_DEFAULT_MAX_LINES

    @classmethod
    def working(cls) -> "StatusIndicatorState":
        return cls(
            header="Working",
            details=None,
            details_max_lines=STATUS_DETAILS_DEFAULT_MAX_LINES,
        )

    def is_guardian_review(self) -> bool:
        return self.header == "Reviewing approval request" or self.header.startswith("Reviewing ")


class TerminalTitleStatusKind(str, Enum):
    Working = "working"
    WaitingForBackgroundTerminal = "waiting_for_background_terminal"
    Thinking = "thinking"


@dataclass(eq=True)
class PendingGuardianReviewStatusEntry:
    id: str
    detail: str


@dataclass(eq=True)
class PendingGuardianReviewStatus:
    entries: list[PendingGuardianReviewStatusEntry] = field(default_factory=list)

    def start_or_update(self, id: str, detail: str) -> None:
        for entry in self.entries:
            if entry.id == id:
                entry.detail = detail
                return
        self.entries.append(PendingGuardianReviewStatusEntry(id=id, detail=detail))

    def finish(self, id: str) -> bool:
        original_len = len(self.entries)
        self.entries = [entry for entry in self.entries if entry.id != id]
        return len(self.entries) != original_len

    def is_empty(self) -> bool:
        return not self.entries

    def status_indicator_state(self) -> StatusIndicatorState | None:
        if not self.entries:
            return None
        if len(self.entries) == 1:
            return StatusIndicatorState(
                header="Reviewing approval request",
                details=self.entries[0].detail,
                details_max_lines=1,
            )

        lines = [f"{GUARDIAN_REVIEW_DETAIL_PREFIX}{entry.detail}" for entry in self.entries[:3]]
        remaining = max(0, len(self.entries) - 3)
        if remaining > 0:
            lines.append(f"+{remaining} more")
        return StatusIndicatorState(
            header=f"Reviewing {len(self.entries)} approval requests",
            details="\n".join(lines),
            details_max_lines=4,
        )


@dataclass(eq=True)
class StatusState:
    current_status: StatusIndicatorState = field(default_factory=StatusIndicatorState.working)
    pending_guardian_review_status: PendingGuardianReviewStatus = field(default_factory=PendingGuardianReviewStatus)
    terminal_title_status_kind: TerminalTitleStatusKind = TerminalTitleStatusKind.Working
    retry_status_header: str | None = None
    pending_status_indicator_restore: bool = False

    def set_status(self, status: StatusIndicatorState) -> None:
        self.current_status = status

    def take_retry_status_header(self) -> str | None:
        value = self.retry_status_header
        self.retry_status_header = None
        return value

    def remember_retry_status_header(self) -> None:
        if self.retry_status_header is None:
            self.retry_status_header = self.current_status.header


# Rust Default for StatusState.
def default() -> StatusState:
    return StatusState()


def guardian_status_aggregates_parallel_reviews() -> bool:
    state = PendingGuardianReviewStatus()
    state.start_or_update("a", "first")
    state.start_or_update("b", "second")
    return state.status_indicator_state() == StatusIndicatorState(
        header="Reviewing 2 approval requests",
        details=f"{GUARDIAN_REVIEW_DETAIL_PREFIX}first\n{GUARDIAN_REVIEW_DETAIL_PREFIX}second",
        details_max_lines=4,
    )


def retry_status_header_is_taken_once() -> bool:
    state = StatusState()
    state.current_status.header = "Thinking"
    state.remember_retry_status_header()
    return state.take_retry_status_header() == "Thinking" and state.take_retry_status_header() is None


__all__ = [
    "GUARDIAN_REVIEW_DETAIL_PREFIX",
    "PendingGuardianReviewStatus",
    "PendingGuardianReviewStatusEntry",
    "RUST_MODULE",
    "STATUS_DETAILS_DEFAULT_MAX_LINES",
    "StatusIndicatorState",
    "StatusState",
    "TerminalTitleStatusKind",
    "default",
    "guardian_status_aggregates_parallel_reviews",
    "retry_status_header_is_taken_once",
]
