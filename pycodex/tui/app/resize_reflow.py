"""Semantic resize-reflow helpers for Rust ``codex-tui::app::resize_reflow``.

The Rust module wires terminal resize events to TUI scrollback rebuilding.  This
Python slice ports the framework-free pieces: trailing streaming-run detection,
initial replay row retention, wrap-policy selection, and source-backed tail
rendering with row caps and separator restoration.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from ..transcript_reflow import TranscriptReflowState


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::resize_reflow",
    source="codex/codex-rs/tui/src/app/resize_reflow.rs",
    status="complete",
)


class HistoryLineWrapPolicy(str, Enum):
    Terminal = "terminal"
    PreWrap = "pre_wrap"


@dataclass(frozen=True, eq=True)
class HyperlinkLine:
    text: str

    @classmethod
    def new(cls, value: Any) -> "HyperlinkLine":
        return cls(str(value))


@dataclass(frozen=True, eq=True)
class ReflowCellDisplay:
    lines: List[HyperlinkLine]
    is_stream_continuation: bool = False


@dataclass(frozen=True, eq=True)
class ReflowRenderResult:
    lines: List[HyperlinkLine]


@dataclass
class InitialHistoryReplayBuffer:
    retained_lines: deque[HyperlinkLine] = field(default_factory=deque)
    render_from_transcript_tail: bool = False


@dataclass
class HistoryCell:
    lines: List[str]
    cell_type: str = "HistoryCell"
    stream_continuation: bool = False

    def display_hyperlink_lines_for_mode(self, width: int, mode: Any = None) -> List[HyperlinkLine]:
        return [HyperlinkLine.new(line) for line in self.lines]

    def is_stream_continuation(self) -> bool:
        return self.stream_continuation


@dataclass
class ResizeReflowState:
    transcript_cells: List[HistoryCell] = field(default_factory=list)
    has_emitted_history_lines: bool = False
    terminal_resize_reflow: Any = None
    transcript_reflow: TranscriptReflowState = field(default_factory=TranscriptReflowState)
    raw_output_mode: bool = False
    resize_reflow_max_rows_value: Optional[int] = None

    def history_line_wrap_policy(self) -> HistoryLineWrapPolicy:
        return history_line_wrap_policy(self.raw_output_mode)

    def render_transcript_lines_for_reflow(self, width: int) -> ReflowRenderResult:
        return render_transcript_lines_for_reflow(
            self.transcript_cells,
            width,
            self.resize_reflow_max_rows_value,
            self,
        )


def _cell_type(cell: Any) -> str:
    if isinstance(cell, dict):
        return str(cell.get("cell_type") or cell.get("kind") or cell.get("type") or "")
    return str(getattr(cell, "cell_type", getattr(cell, "kind", getattr(cell, "type", cell.__class__.__name__))))


def _is_stream_continuation(cell: Any) -> bool:
    value = getattr(cell, "is_stream_continuation", None)
    if callable(value):
        return bool(value())
    if isinstance(cell, dict):
        return bool(cell.get("stream_continuation") or cell.get("is_stream_continuation"))
    return bool(getattr(cell, "stream_continuation", False))


def trailing_run_start(transcript_cells: Iterable[Any], cell_type: str | type[Any]) -> int:
    """Port Rust ``trailing_run_start::<T>``.

    Walks backward over trailing stream-continuation cells of type ``T`` and
    includes the first non-continuation cell of the same type when present.
    """

    cells = list(transcript_cells)
    expected = cell_type if isinstance(cell_type, str) else cell_type.__name__
    end = len(cells)
    start = end
    while start > 0 and _is_stream_continuation(cells[start - 1]) and _cell_type(cells[start - 1]) == expected:
        start -= 1
    if start > 0 and _cell_type(cells[start - 1]) == expected and not _is_stream_continuation(cells[start - 1]):
        start -= 1
    return start


def reset_history_emission_state(state: ResizeReflowState, deferred_history_lines: Optional[List[Any]] = None) -> None:
    state.has_emitted_history_lines = False
    if deferred_history_lines is not None:
        deferred_history_lines.clear()


def history_line_wrap_policy(raw_output_mode: bool) -> HistoryLineWrapPolicy:
    return HistoryLineWrapPolicy.Terminal if raw_output_mode else HistoryLineWrapPolicy.PreWrap


def buffer_initial_history_replay_display_lines(
    buffer: InitialHistoryReplayBuffer,
    display: Iterable[HyperlinkLine | str],
    max_rows: int,
) -> None:
    """Retain only newest display rows, dropping oldest first like Rust."""

    buffer.retained_lines.extend(_coerce_lines(display))
    while len(buffer.retained_lines) > max_rows:
        buffer.retained_lines.popleft()


def display_lines_for_history_insert(
    state: ResizeReflowState,
    cell: HistoryCell,
    width: int,
    mode: Any = None,
) -> List[HyperlinkLine]:
    display = cell.display_hyperlink_lines_for_mode(width, mode)
    if display and not cell.is_stream_continuation():
        if state.has_emitted_history_lines:
            display.insert(0, HyperlinkLine.new(""))
        else:
            state.has_emitted_history_lines = True
    return display


def render_transcript_lines_for_reflow(
    transcript_cells: Iterable[HistoryCell],
    width: int,
    row_cap: Optional[int] = None,
    state: ResizeReflowState | None = None,
) -> ReflowRenderResult:
    """Render transcript tail with Rust row-cap and separator semantics."""

    cells = list(transcript_cells)
    cell_displays: deque[ReflowCellDisplay] = deque()
    rendered_rows = 0
    start = len(cells)

    while start > 0:
        start -= 1
        cell = cells[start]
        lines = cell.display_hyperlink_lines_for_mode(width, None)
        rendered_rows += len(lines)
        cell_displays.appendleft(ReflowCellDisplay(lines, cell.is_stream_continuation()))
        if row_cap is not None and rendered_rows > row_cap:
            break

    while start > 0 and cell_displays and cell_displays[0].is_stream_continuation:
        start -= 1
        cell = cells[start]
        cell_displays.appendleft(
            ReflowCellDisplay(
                cell.display_hyperlink_lines_for_mode(width, None),
                cell.is_stream_continuation(),
            )
        )

    emitted = False
    reflowed: List[HyperlinkLine] = []
    for display in cell_displays:
        if display.lines and not display.is_stream_continuation:
            if emitted:
                reflowed.append(HyperlinkLine.new(""))
            else:
                emitted = True
        reflowed.extend(display.lines)

    if row_cap is not None and len(reflowed) > row_cap:
        reflowed = reflowed[len(reflowed) - row_cap :]
    if state is not None:
        state.has_emitted_history_lines = bool(reflowed)
    return ReflowRenderResult(reflowed)


def should_mark_reflow_as_stream_time(
    transcript_cells: Iterable[Any],
    *,
    active_agent_stream: bool = False,
    active_plan_stream: bool = False,
) -> bool:
    cells = list(transcript_cells)
    return (
        active_agent_stream
        or active_plan_stream
        or trailing_run_start(cells, "AgentMessageCell") < len(cells)
        or trailing_run_start(cells, "ProposedPlanStreamCell") < len(cells)
    )


def _coerce_lines(lines: Iterable[Any]) -> List[HyperlinkLine]:
    return [line if isinstance(line, HyperlinkLine) else HyperlinkLine.new(line) for line in lines]


@dataclass(frozen=True, eq=True)
class ResizeReflowPlan:
    action: str
    width: Optional[int] = None
    lines: Tuple[HyperlinkLine, ...] = ()
    wrap_policy: Optional[HistoryLineWrapPolicy] = None
    updates: Tuple[Tuple[str, Any], ...] = ()
    schedule_frame: bool = False
    schedule_frame_in: Optional[str] = None


def insert_history_cell_lines_plan(state: ResizeReflowState, cell: HistoryCell, width: int, overlay_active: bool = False) -> ResizeReflowPlan:
    display = display_lines_for_history_insert(state, cell, width)
    if not display:
        return ResizeReflowPlan(action="skip_empty_history_cell")
    if overlay_active:
        return ResizeReflowPlan(action="defer_history_lines", lines=tuple(display))
    return ResizeReflowPlan(action="insert_history_lines", width=width, lines=tuple(display), wrap_policy=state.history_line_wrap_policy())


def begin_initial_history_replay_buffer_plan(enabled: bool, overlay_active: bool = False) -> ResizeReflowPlan:
    if enabled and not overlay_active:
        return ResizeReflowPlan(action="begin_initial_history_replay_buffer", updates=(("initial_history_replay_buffer", True),))
    return ResizeReflowPlan(action="skip_initial_history_replay_buffer")


def begin_thread_switch_history_replay_buffer_plan(enabled: bool, row_cap: Optional[int], overlay_active: bool = False) -> ResizeReflowPlan:
    if enabled and row_cap is not None and not overlay_active:
        return ResizeReflowPlan(action="begin_thread_switch_history_replay_buffer", updates=(("initial_history_replay_buffer.render_from_transcript_tail", True),))
    return ResizeReflowPlan(action="skip_thread_switch_history_replay_buffer")


def finish_initial_history_replay_buffer_plan(state: ResizeReflowState, buffer: Optional[InitialHistoryReplayBuffer], width: int) -> ResizeReflowPlan:
    if buffer is None:
        return ResizeReflowPlan(action="no_initial_history_replay_buffer")
    if buffer.retained_lines:
        return ResizeReflowPlan(action="flush_initial_history_replay_buffer", width=width, lines=tuple(buffer.retained_lines), wrap_policy=state.history_line_wrap_policy())
    if buffer.render_from_transcript_tail:
        result = state.render_transcript_lines_for_reflow(width)
        return ResizeReflowPlan(action="flush_transcript_tail_replay", width=width, lines=tuple(result.lines), wrap_policy=state.history_line_wrap_policy() if result.lines else None)
    return ResizeReflowPlan(action="empty_initial_history_replay_buffer")


def handle_draw_size_change_plan(state: ResizeReflowState, width: int, height: int, last_width: Optional[int], last_height: int, enabled: bool = True, stream_time: bool = False) -> ResizeReflowPlan:
    initialized = last_width is None
    width_changed = last_width is not None and width != last_width
    height_changed = height != last_height
    should_rebuild = width_changed or height_changed
    updates = (("chat_widget.on_terminal_resize", width),) if initialized or width_changed else ()
    if should_rebuild and enabled:
        extra = (("transcript_reflow.stream_time", True),) if width_changed and stream_time else ()
        return ResizeReflowPlan(action="schedule_resize_reflow", width=width if width_changed else None, updates=updates + extra, schedule_frame=True)
    if should_rebuild and not enabled and width_changed:
        return ResizeReflowPlan(action="clear_disabled_resize_reflow", updates=updates + (("transcript_reflow.clear", True),))
    if width != last_width or height_changed:
        return ResizeReflowPlan(action="refresh_status_line", updates=updates + (("refresh_status_line", True),))
    return ResizeReflowPlan(action="no_resize_reflow", updates=updates)


def maybe_run_resize_reflow(state: ResizeReflowState, width: int, pending_due: bool = True, overlay_active: bool = False, enabled: bool = True, active_stream: bool = False) -> ResizeReflowPlan:
    if not enabled:
        reset_history_emission_state(state)
        return ResizeReflowPlan(action="clear_disabled_resize_reflow", updates=(("transcript_reflow.clear", True),))
    if not pending_due:
        return ResizeReflowPlan(action="defer_resize_reflow", schedule_frame_in="pending_until")
    if overlay_active:
        return ResizeReflowPlan(action="defer_resize_reflow_for_overlay")
    plan = reflow_transcript_now(state, width)
    updates = plan.updates + (("transcript_reflow.mark_reflowed_width", width),)
    if active_stream or should_mark_reflow_as_stream_time(state.transcript_cells):
        updates += (("transcript_reflow.mark_ran_during_stream", True),)
    return ResizeReflowPlan(action="run_resize_reflow", width=width, lines=plan.lines, wrap_policy=plan.wrap_policy, updates=updates, schedule_frame_in="TRANSCRIPT_REFLOW_DEBOUNCE")


def maybe_finish_stream_reflow_plan(
    state: ResizeReflowState,
    width: int,
    *,
    enabled: bool = True,
    pending_due: bool | None = None,
    overlay_active: bool = False,
) -> ResizeReflowPlan:
    """Port Rust ``App::maybe_finish_stream_reflow`` as a semantic plan."""

    if not enabled:
        state.transcript_reflow.clear()
        return ResizeReflowPlan(
            action="clear_disabled_stream_finish_reflow",
            updates=(("transcript_reflow.clear", True),),
        )

    if state.transcript_reflow.take_stream_finish_reflow_needed():
        state.transcript_reflow.schedule_immediate()
        plan = maybe_run_resize_reflow(
            state,
            width,
            pending_due=True,
            overlay_active=overlay_active,
            enabled=True,
            active_stream=False,
        )
        return ResizeReflowPlan(
            action="finish_stream_reflow",
            width=width,
            lines=plan.lines,
            wrap_policy=plan.wrap_policy,
            updates=(
                ("transcript_reflow.schedule_immediate", True),
                ("frame_requester.schedule_frame", True),
            )
            + plan.updates,
            schedule_frame=True,
            schedule_frame_in=plan.schedule_frame_in,
        )

    due = state.transcript_reflow.pending_is_due() if pending_due is None else bool(pending_due)
    if due:
        return ResizeReflowPlan(
            action="stream_finish_pending_reflow_due",
            updates=(("frame_requester.schedule_frame", True),),
            schedule_frame=True,
        )
    return ResizeReflowPlan(action="stream_finish_no_reflow")


def reflow_transcript_now(state: ResizeReflowState, terminal_width: int) -> ResizeReflowPlan:
    width = terminal_width
    if not state.transcript_cells:
        reset_history_emission_state(state)
        return ResizeReflowPlan(action="reflow_empty_transcript", width=terminal_width, updates=(("clear_pending_history_lines", True), ("reset_history_emission_state", True)))
    result = state.render_transcript_lines_for_reflow(width)
    return ResizeReflowPlan(action="reflow_transcript_now", width=terminal_width, lines=tuple(result.lines), wrap_policy=state.history_line_wrap_policy() if result.lines else None, updates=(("clear_pending_history_lines", True), ("clear_terminal_for_resize_replay", True), ("deferred_history_lines.clear", True)))


__all__ = [
    "HistoryCell",
    "HistoryLineWrapPolicy",
    "HyperlinkLine",
    "InitialHistoryReplayBuffer",
    "ResizeReflowPlan",
    "RUST_MODULE",
    "ReflowCellDisplay",
    "ReflowRenderResult",
    "ResizeReflowState",
    "begin_initial_history_replay_buffer_plan",
    "begin_thread_switch_history_replay_buffer_plan",
    "buffer_initial_history_replay_display_lines",
    "display_lines_for_history_insert",
    "finish_initial_history_replay_buffer_plan",
    "handle_draw_size_change_plan",
    "insert_history_cell_lines_plan",
    "history_line_wrap_policy",
    "maybe_run_resize_reflow",
    "maybe_finish_stream_reflow_plan",
    "reflow_transcript_now",
    "render_transcript_lines_for_reflow",
    "reset_history_emission_state",
    "should_mark_reflow_as_stream_time",
    "trailing_run_start",
]
