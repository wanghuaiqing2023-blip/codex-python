"""Transcript consolidation for finalized streaming agent messages.

Rust counterpart: ``codex-rs/tui/src/app/agent_message_consolidation.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .._porting import RustTuiModule
from ..app_event import ConsolidationScrollbackReflow


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::agent_message_consolidation",
    source="codex/codex-rs/tui/src/app/agent_message_consolidation.rs",
    status="complete",
)


@dataclass(frozen=True)
class AgentMessageCell:
    """Semantic stand-in for transient streaming ``AgentMessageCell`` values."""

    lines: tuple[Any, ...] = ()
    is_first_line: bool = False


@dataclass(frozen=True)
class AgentMarkdownCell:
    """Source-backed canonical transcript cell produced after consolidation."""

    source: str
    cwd: Path

    @classmethod
    def new(cls, source: str, cwd: Any) -> "AgentMarkdownCell":
        return cls(source=source, cwd=Path(cwd))


@dataclass
class TranscriptOverlay:
    cells: list[Any] = field(default_factory=list)
    inserted_cells: list[Any] = field(default_factory=list)
    consolidated_ranges: list[tuple[int, int, Any]] = field(default_factory=list)

    def insert_cell(self, cell: Any) -> None:
        self.inserted_cells.append(cell)
        self.cells.append(cell)

    def consolidate_cells(self, start: int, end: int, consolidated: Any) -> None:
        self.consolidated_ranges.append((start, end, consolidated))
        self.cells[start:end] = [consolidated]


@dataclass
class FrameRequester:
    scheduled_frames: int = 0

    def schedule_frame(self) -> None:
        self.scheduled_frames += 1


@dataclass
class Tui:
    frame_requester: FrameRequester = field(default_factory=FrameRequester)


@dataclass
class AgentMessageConsolidationApp:
    """Minimal App-shaped state for the module-local consolidation contract."""

    transcript_cells: list[Any] = field(default_factory=list)
    overlay: Optional[TranscriptOverlay] = None
    maybe_finish_stream_reflow_calls: int = 0
    finish_required_stream_reflow_calls: int = 0

    def maybe_finish_stream_reflow(self, tui: Tui) -> None:
        self.maybe_finish_stream_reflow_calls += 1

    def finish_required_stream_reflow(self, tui: Tui) -> None:
        self.finish_required_stream_reflow_calls += 1

    def finish_agent_message_consolidation(
        self,
        tui: Tui,
        scrollback_reflow: ConsolidationScrollbackReflow,
    ) -> None:
        if scrollback_reflow is ConsolidationScrollbackReflow.IF_RESIZE_REFLOW_RAN:
            self.maybe_finish_stream_reflow(tui)
        elif scrollback_reflow is ConsolidationScrollbackReflow.REQUIRED:
            self.finish_required_stream_reflow(tui)
        else:
            raise ValueError(f"unknown scrollback reflow mode: {scrollback_reflow!r}")

    def handle_consolidate_agent_message(
        self,
        tui: Tui,
        source: str,
        cwd: Any,
        scrollback_reflow: ConsolidationScrollbackReflow,
        deferred_history_cell: Optional[Any] = None,
    ) -> Optional[AgentMarkdownCell]:
        return handle_consolidate_agent_message(
            self,
            tui,
            source,
            cwd,
            scrollback_reflow,
            deferred_history_cell,
        )


def _is_agent_message_cell(cell: Any) -> bool:
    if isinstance(cell, AgentMessageCell):
        return True
    if isinstance(cell, dict):
        return cell.get("kind") == "AgentMessageCell"
    return getattr(cell, "kind", None) == "AgentMessageCell"


def trailing_agent_message_run_start(transcript_cells: list[Any]) -> int:
    """Find the start of the trailing contiguous ``AgentMessageCell`` run."""

    idx = len(transcript_cells)
    while idx > 0 and _is_agent_message_cell(transcript_cells[idx - 1]):
        idx -= 1
    return idx


def handle_consolidate_agent_message(
    app: AgentMessageConsolidationApp,
    tui: Tui,
    source: str,
    cwd: Any,
    scrollback_reflow: ConsolidationScrollbackReflow,
    deferred_history_cell: Optional[Any] = None,
) -> Optional[AgentMarkdownCell]:
    """Replace the trailing streaming agent-message run with markdown source."""

    if deferred_history_cell is not None:
        if app.overlay is not None:
            app.overlay.insert_cell(deferred_history_cell)
        app.transcript_cells.append(deferred_history_cell)

    end = len(app.transcript_cells)
    start = trailing_agent_message_run_start(app.transcript_cells)
    if start < end:
        consolidated = AgentMarkdownCell.new(source, cwd)
        app.transcript_cells[start:end] = [consolidated]
        if app.overlay is not None:
            app.overlay.consolidate_cells(start, end, consolidated)
            tui.frame_requester.schedule_frame()
        app.finish_agent_message_consolidation(tui, scrollback_reflow)
        return consolidated

    app.maybe_finish_stream_reflow(tui)
    return None


def consolidates_trailing_agent_message_cells() -> bool:
    app = AgentMessageConsolidationApp(
        transcript_cells=[
            AgentMarkdownCell.new("old", "/tmp/cwd"),
            AgentMessageCell(("hello",), True),
            AgentMessageCell(("world",), False),
        ],
        overlay=TranscriptOverlay(
            [
                AgentMarkdownCell.new("old", "/tmp/cwd"),
                AgentMessageCell(("hello",), True),
                AgentMessageCell(("world",), False),
            ]
        ),
    )
    tui = Tui()

    consolidated = app.handle_consolidate_agent_message(
        tui,
        "hello\nworld",
        "/tmp/cwd",
        ConsolidationScrollbackReflow.REQUIRED,
    )

    return (
        consolidated == AgentMarkdownCell.new("hello\nworld", "/tmp/cwd")
        and app.transcript_cells == [AgentMarkdownCell.new("old", "/tmp/cwd"), consolidated]
        and app.overlay is not None
        and app.overlay.consolidated_ranges == [(1, 3, consolidated)]
        and tui.frame_requester.scheduled_frames == 1
        and app.finish_required_stream_reflow_calls == 1
        and app.maybe_finish_stream_reflow_calls == 0
    )


def deferred_history_cell_is_inserted_before_consolidation() -> bool:
    deferred = AgentMessageCell(("tail",), False)
    app = AgentMessageConsolidationApp(
        transcript_cells=[AgentMessageCell(("head",), True)],
        overlay=TranscriptOverlay([AgentMessageCell(("head",), True)]),
    )
    tui = Tui()

    consolidated = app.handle_consolidate_agent_message(
        tui,
        "head\ntail",
        "/tmp/cwd",
        ConsolidationScrollbackReflow.IF_RESIZE_REFLOW_RAN,
        deferred_history_cell=deferred,
    )

    return (
        app.overlay is not None
        and app.overlay.inserted_cells == [deferred]
        and app.transcript_cells == [consolidated]
        and app.maybe_finish_stream_reflow_calls == 1
    )


def no_trailing_agent_cells_finishes_stream_reflow_only() -> bool:
    app = AgentMessageConsolidationApp(
        transcript_cells=[AgentMarkdownCell.new("old", "/tmp/cwd")],
        overlay=TranscriptOverlay([AgentMarkdownCell.new("old", "/tmp/cwd")]),
    )
    tui = Tui()

    result = app.handle_consolidate_agent_message(
        tui,
        "new",
        "/tmp/cwd",
        ConsolidationScrollbackReflow.REQUIRED,
    )

    return (
        result is None
        and app.maybe_finish_stream_reflow_calls == 1
        and app.finish_required_stream_reflow_calls == 0
        and tui.frame_requester.scheduled_frames == 0
        and app.overlay is not None
        and app.overlay.consolidated_ranges == []
    )


__all__ = [
    "AgentMarkdownCell",
    "AgentMessageCell",
    "AgentMessageConsolidationApp",
    "FrameRequester",
    "RUST_MODULE",
    "TranscriptOverlay",
    "Tui",
    "consolidates_trailing_agent_message_cells",
    "deferred_history_cell_is_inserted_before_consolidation",
    "handle_consolidate_agent_message",
    "no_trailing_agent_cells_finishes_stream_reflow_only",
    "trailing_agent_message_run_start",
]
