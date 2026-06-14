"""Transcript and active-cell bookkeeping for ``ChatWidget``.

This is a direct semantic port of Rust
``codex-tui::chatwidget::transcript``.  ``active_cell`` remains an opaque
Python object because rendering is owned by neighboring history-cell modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::transcript", source="codex/codex-rs/tui/src/chatwidget/transcript.rs")

MAX_AGENT_COPY_HISTORY = 20
U64_MAX = (1 << 64) - 1


@dataclass
class AgentTurnMarkdown:
    user_turn_count: int
    markdown: str


@dataclass
class TranscriptState:
    active_cell: Any | None = None
    active_cell_revision: int = 0
    last_agent_markdown: str | None = None
    agent_turn_markdowns: list[AgentTurnMarkdown] = field(default_factory=list)
    visible_user_turn_count: int = 0
    copy_history_evicted_by_rollback: bool = False
    latest_proposed_plan_markdown: str | None = None
    saw_copy_source_this_turn: bool = False
    needs_final_message_separator: bool = False
    had_work_activity: bool = False
    saw_plan_update_this_turn: bool = False
    saw_plan_item_this_turn: bool = False
    last_plan_progress: tuple[int, int] | None = None
    plan_delta_buffer: str = ""
    plan_item_active: bool = False

    @classmethod
    def new(cls, active_cell: Any | None = None) -> "TranscriptState":
        return cls(active_cell=active_cell)

    def bump_active_cell_revision(self) -> None:
        self.active_cell_revision = (self.active_cell_revision + 1) & U64_MAX

    def record_agent_markdown(self, markdown: str) -> None:
        if (
            self.agent_turn_markdowns
            and self.agent_turn_markdowns[-1].user_turn_count == self.visible_user_turn_count
        ):
            self.agent_turn_markdowns[-1].markdown = markdown
        else:
            self.agent_turn_markdowns.append(
                AgentTurnMarkdown(
                    user_turn_count=self.visible_user_turn_count,
                    markdown=markdown,
                )
            )
            if len(self.agent_turn_markdowns) > MAX_AGENT_COPY_HISTORY:
                del self.agent_turn_markdowns[0]
        self.last_agent_markdown = markdown
        self.copy_history_evicted_by_rollback = False
        self.saw_copy_source_this_turn = True

    def record_visible_user_turn(self) -> None:
        if self.visible_user_turn_count < U64_MAX:
            self.visible_user_turn_count += 1

    def reset_copy_history(self) -> None:
        self.last_agent_markdown = None
        self.agent_turn_markdowns.clear()
        self.visible_user_turn_count = 0
        self.copy_history_evicted_by_rollback = False
        self.saw_copy_source_this_turn = False

    def truncate_copy_history_to_user_turn_count(self, user_turn_count: int) -> None:
        self.visible_user_turn_count = user_turn_count
        had_copy_history = bool(self.agent_turn_markdowns)
        self.agent_turn_markdowns = [
            entry
            for entry in self.agent_turn_markdowns
            if entry.user_turn_count <= user_turn_count
        ]
        self.last_agent_markdown = (
            self.agent_turn_markdowns[-1].markdown
            if self.agent_turn_markdowns
            else None
        )
        self.copy_history_evicted_by_rollback = had_copy_history and self.last_agent_markdown is None
        self.saw_copy_source_this_turn = False

    def reset_turn_flags(self) -> None:
        self.saw_copy_source_this_turn = False
        self.saw_plan_update_this_turn = False
        self.saw_plan_item_this_turn = False
        self.had_work_activity = False
        self.latest_proposed_plan_markdown = None
        self.plan_delta_buffer = ""
        self.plan_item_active = False


def active_cell_revision_wraps() -> int:
    state = TranscriptState(active_cell_revision=U64_MAX)
    state.bump_active_cell_revision()
    return state.active_cell_revision


def copy_history_tracks_latest_visible_turn() -> str | None:
    state = TranscriptState()
    state.record_visible_user_turn()
    state.record_agent_markdown("first")
    state.record_visible_user_turn()
    state.record_agent_markdown("second")
    state.truncate_copy_history_to_user_turn_count(1)
    return state.last_agent_markdown


__all__ = [
    "AgentTurnMarkdown",
    "MAX_AGENT_COPY_HISTORY",
    "RUST_MODULE",
    "TranscriptState",
    "U64_MAX",
    "active_cell_revision_wraps",
    "copy_history_tracks_latest_visible_turn",
]
