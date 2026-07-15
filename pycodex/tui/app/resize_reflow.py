"""Semantic resize-reflow helpers for Rust ``codex-tui::app::resize_reflow``.

The Rust module wires terminal resize events to TUI scrollback rebuilding.  This
Python slice ports the framework-free pieces: trailing streaming-run detection,
initial replay row retention, wrap-policy selection, and source-backed tail
rendering with row caps and separator restoration.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, List, Optional, Sequence, TextIO, Tuple, TypeVar

from .._porting import RustTuiModule
from ..custom_terminal import (
    clear_line_at,
    clear_scrollback_and_visible_screen_ansi,
    display_width,
    reset_scroll_region,
    write_at,
)
from ..history_cell import HistoryRenderMode, display_hyperlink_lines_for_mode
from ..insert_history import TerminalHistoryState, terminal_history_cell_lines
from ..terminal_hyperlinks import line_text as terminal_line_text
from ..transcript_reflow import TranscriptReflowState


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::resize_reflow",
    source="codex/codex-rs/tui/src/app/resize_reflow.rs",
    status="complete",
)

_ExternalRepaintResult = TypeVar("_ExternalRepaintResult")
TerminalExternalRepaintRunner = Callable[
    [Callable[[], _ExternalRepaintResult]],
    _ExternalRepaintResult,
]


def _run_external_repaint_inline(
    repaint: Callable[[], _ExternalRepaintResult],
) -> _ExternalRepaintResult:
    return repaint()


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


def _display_cell_lines(cell: Any, width: int, mode: Any = None) -> List[HyperlinkLine]:
    legacy = getattr(cell, "display_hyperlink_lines_for_mode", None)
    if callable(legacy):
        return _coerce_lines(legacy(width, mode))
    render_mode = HistoryRenderMode.RAW if mode is HistoryRenderMode.RAW else HistoryRenderMode.RICH
    return [
        HyperlinkLine.new(terminal_line_text(line))
        for line in display_hyperlink_lines_for_mode(cell, width, render_mode)
    ]


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
    display = _display_cell_lines(cell, width, mode)
    if display and not _is_stream_continuation(cell):
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
        lines = _display_cell_lines(cell, width, None)
        rendered_rows += len(lines)
        cell_displays.appendleft(ReflowCellDisplay(lines, _is_stream_continuation(cell)))
        if row_cap is not None and rendered_rows > row_cap:
            break

    while start > 0 and cell_displays and cell_displays[0].is_stream_continuation:
        start -= 1
        cell = cells[start]
        cell_displays.appendleft(
            ReflowCellDisplay(
                _display_cell_lines(cell, width, None),
                _is_stream_continuation(cell),
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


@dataclass(frozen=True, eq=True)
class TerminalResizeReflowPlan:
    action: str
    pending: bool = False


@dataclass(frozen=True, eq=True)
class TerminalSizeChangeReflowPlan:
    """Plan terminal-size driven resize reflow for the scrollback product path."""

    reflow: TerminalResizeReflowPlan
    last_terminal_size: os.terminal_size
    changed: bool = False
    initialized: bool = False


@dataclass(frozen=True, eq=True)
class TerminalResizeRuntimeState:
    """Track terminal resize state for the scrollback product path.

    Rust keeps draw-size state on ``App`` while resize decisions live in
    ``app::resize_reflow``.  The Python terminal runner has no ratatui frame, so
    this small value object keeps the same app-owned boundary while leaving the
    runner responsible only for observing terminal size and executing plans.
    """

    last_terminal_size: os.terminal_size | None = None
    handling_resize: bool = False

    @classmethod
    def inactive(cls) -> "TerminalResizeRuntimeState":
        return cls()

    def activated(self, size: os.terminal_size) -> "TerminalResizeRuntimeState":
        return TerminalResizeRuntimeState(last_terminal_size=size)

    def deactivated(self) -> "TerminalResizeRuntimeState":
        return TerminalResizeRuntimeState()

    def begin_handling(self) -> "TerminalResizeRuntimeState":
        return TerminalResizeRuntimeState(
            last_terminal_size=self.last_terminal_size,
            handling_resize=True,
        )

    def end_handling(self) -> "TerminalResizeRuntimeState":
        return TerminalResizeRuntimeState(
            last_terminal_size=self.last_terminal_size,
            handling_resize=False,
        )

    def after_size_plan(
        self,
        plan: TerminalSizeChangeReflowPlan,
    ) -> "TerminalResizeRuntimeState":
        return TerminalResizeRuntimeState(
            last_terminal_size=plan.last_terminal_size,
            handling_resize=self.handling_resize,
        )


@dataclass
class TerminalResizeCoordinator:
    """Stateful resize/layout adapter for the terminal product path.

    Rust ``app::resize_reflow`` owns resize-state transitions and replay
    planning.  The terminal runner supplies the observed terminal environment
    and concrete repaint/replay callbacks.
    """

    terminal_active: Callable[[], bool]
    current_size: Callable[[], os.terminal_size]
    active_stream: Callable[[], bool]
    reset_terminal_scroll_region: Callable[[], None]
    render_bottom_pane: Callable[[], None]
    repaint_history_viewport: Callable[[], None]
    replay_history_scrollback: Callable[[], None]
    run_external_repaint: TerminalExternalRepaintRunner = _run_external_repaint_inline
    render_after_external_repaint: Callable[[], None] | None = None
    on_width_change: Callable[[int], None] | None = None
    layout_active: bool = False
    state: TerminalResizeRuntimeState = field(default_factory=TerminalResizeRuntimeState.inactive)
    transcript_reflow: TranscriptReflowState = field(default_factory=TranscriptReflowState)
    pending: bool = False

    @property
    def terminal_layout_active(self) -> bool:
        return self.terminal_active() and self.layout_active

    def terminal_layout_active_state(self) -> bool:
        """Return the current terminal layout-active state for runtime bindings."""

        return self.terminal_layout_active

    def activate_layout(self) -> None:
        self.layout_active, self.state = run_terminal_layout_activation(
            terminal_active=self.terminal_active(),
            state=self.state,
            current_size=self.current_size(),
            render_bottom_pane=self.render_bottom_pane,
        )
        if self.layout_active:
            self.transcript_reflow.note_width(self.state.last_terminal_size.columns)

    def deactivate_layout(self) -> None:
        self.layout_active, self.state = run_terminal_layout_deactivation(
            terminal_active=self.terminal_active(),
            state=self.state,
            reset_terminal_scroll_region=self.reset_terminal_scroll_region,
        )
        self.transcript_reflow.clear()
        self.pending = False

    def check_size_change(self) -> None:
        if not self.terminal_layout_active or self.state.handling_resize:
            return
        current_size = self.current_size()
        previous_size = self.state.last_terminal_size
        width_change = self.transcript_reflow.note_width(current_size.columns)
        if previous_size is None:
            self.state = self.state.activated(current_size)
            return
        if previous_size != current_size:
            if width_change.changed and self.on_width_change is not None:
                self.on_width_change(current_size.columns)
            self.state = TerminalResizeRuntimeState(last_terminal_size=current_size)
            self.transcript_reflow.schedule_debounced(
                current_size.columns if width_change.changed else None
            )
            self.pending = True
            if self.active_stream():
                self.transcript_reflow.mark_resize_requested_during_stream()
                return
        self._run_due_resize_reflow()

    def run_reflow_plan(self, plan: TerminalResizeReflowPlan) -> bool:
        self.pending = plan.pending
        return run_terminal_resize_reflow_plan(
            plan,
            repaint_history_viewport=lambda: self._run_external_history_action(
                self.repaint_history_viewport,
                render_after=False,
            ),
            replay_history_scrollback=self._run_replay_history_scrollback,
        )

    def _run_replay_history_scrollback(self) -> None:
        self._run_external_history_action(self.replay_history_scrollback)

    def _run_external_history_action(
        self,
        action: Callable[[], None],
        *,
        render_after: bool = True,
    ) -> None:
        self.run_external_repaint(action)
        if render_after:
            render = self.render_after_external_repaint or self.render_bottom_pane
            render()

    def _run_due_resize_reflow(self) -> bool:
        if not self.transcript_reflow.pending_is_due() or self.active_stream():
            return False
        handling_state = self.state.begin_handling()
        self._apply_resize_state(handling_state)
        try:
            self.reset_terminal_scroll_region()
            self.run_reflow_plan(TerminalResizeReflowPlan("replay_history_scrollback"))
            width = self.state.last_terminal_size.columns if self.state.last_terminal_size else self.current_size().columns
            self.transcript_reflow.mark_reflowed_width(width)
            self.transcript_reflow.clear_pending_reflow()
            self.pending = False
        finally:
            self._apply_resize_state(self.state.end_handling())
        return True

    def run_stream_finish_reflow(self) -> bool:
        """Compatibility alias for Rust required stream consolidation reflow."""

        return self.run_required_stream_reflow()

    def run_required_stream_reflow(self) -> bool:
        self.transcript_reflow.take_stream_finish_reflow_needed()
        self.transcript_reflow.schedule_immediate()
        self.pending = True
        return self._run_due_resize_reflow()

    def run_conditional_stream_reflow(self) -> bool:
        needs_resize_reflow = self.transcript_reflow.take_stream_finish_reflow_needed()
        if needs_resize_reflow or self.pending:
            self.transcript_reflow.schedule_immediate()
            self.pending = True
            return self._run_due_resize_reflow()
        return False

    def apply_pending(self, pending: bool) -> None:
        self.pending = bool(pending)
        if not self.pending:
            self.transcript_reflow.clear_pending_reflow()

    def _apply_resize_state(self, state: TerminalResizeRuntimeState) -> None:
        self.state = state


@dataclass
class TerminalResizeHistoryReplayer:
    """Stateful retained-history repaint/replay adapter for terminal resize.

    Rust ``app::resize_reflow`` owns the clear/rebuild ordering while ``tui.rs``
    supplies terminal effects.  This adapter keeps the Python runner from
    spelling out history-state and bottom-pane wiring for each resize action.
    """

    writer: TextIO
    history_state: Callable[[], TerminalHistoryState]
    history_wrap_width: Callable[[], int]
    terminal_active: Callable[[], bool]
    live_status_footprint_active: Callable[[], bool]
    history_bottom_row: Callable[[], int]
    terminal_columns: Callable[[], int]
    insert_replayed_history_lines: Callable[[list[str], bool], None]
    apply_history_state: Callable[[TerminalHistoryState], None]
    render_bottom_pane: Callable[[], None]
    transcript_cells: Callable[[], Sequence[Any]] | None = None

    def repaint_viewport(self) -> bool:
        return self._repaint_viewport(reserve_active_bottom_pane=False)

    def _repaint_viewport(self, *, reserve_active_bottom_pane: bool) -> bool:
        def bottom_row() -> int:
            try:
                return self.history_bottom_row(reserve_active_bottom_pane)
            except TypeError:
                return self.history_bottom_row()
        if self.transcript_cells is not None:
            return run_terminal_typed_transcript_viewport_repaint(
                self.writer,
                self.transcript_cells(),
                self.history_wrap_width(),
                terminal_active=self.terminal_active(),
                history_bottom_row=bottom_row,
                terminal_columns=self.terminal_columns,
            )
        state = self.history_state()
        painted = run_terminal_history_state_viewport_repaint_for_width(
            self.writer,
            state,
            self.history_wrap_width(),
            terminal_active=self.terminal_active(),
            history_bottom_row=bottom_row,
            terminal_columns=self.terminal_columns,
        )
        return painted

    def replay_scrollback(self) -> bool:
        if self.transcript_cells is not None:
            return run_terminal_typed_transcript_scrollback_replay(
                self.writer,
                self.transcript_cells(),
                self.history_wrap_width(),
                live_status_footprint_active=self.live_status_footprint_active(),
                insert_replayed_history_lines=self.insert_replayed_history_lines,
                apply_history_state=self.apply_history_state,
                history_state=self.history_state(),
            )
        return run_terminal_history_state_scrollback_replay_insert_for_resize_width(
            self.writer,
            self.history_state(),
            self.history_wrap_width(),
            live_status_footprint_active=self.live_status_footprint_active(),
            insert_replayed_history_lines=self.insert_replayed_history_lines,
            apply_history_state=self.apply_history_state,
            render_bottom_pane=None,
        )


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


def clear_terminal_for_resize_replay(writer: TextIO) -> None:
    """Clear visible screen and scrollback before replaying retained history."""

    clear_scrollback_and_visible_screen_ansi(writer)


def plan_terminal_resize_reflow(
    *,
    trigger: str,
    changed: bool,
    active_stream: bool,
    pending: bool = False,
) -> TerminalResizeReflowPlan:
    """Plan real-terminal size-change reflow for the scrollback path."""

    if not changed:
        return TerminalResizeReflowPlan("none", pending=pending)
    if active_stream:
        return TerminalResizeReflowPlan("defer_until_stream_finish", pending=True)
    if trigger == "terminal_resize":
        return TerminalResizeReflowPlan("replay_history_scrollback", pending=False)
    return TerminalResizeReflowPlan("none", pending=pending)


def plan_terminal_size_change_reflow(
    *,
    previous_size: os.terminal_size | None,
    current_size: os.terminal_size,
    active_stream: bool,
    pending: bool = False,
) -> TerminalSizeChangeReflowPlan:
    """Port the size-change gate from Rust ``App::handle_draw_size_change``.

    The real-terminal scrollback path has no ratatui ``Frame`` to own this
    decision, so the runner reports observed sizes and app::resize_reflow
    decides whether this is initialization, no-op, immediate replay, or a
    stream-time deferred replay.
    """

    if previous_size is None:
        return TerminalSizeChangeReflowPlan(
            TerminalResizeReflowPlan("none", pending=pending),
            current_size,
            initialized=True,
        )
    if previous_size == current_size:
        return TerminalSizeChangeReflowPlan(
            TerminalResizeReflowPlan("none", pending=pending),
            previous_size,
        )
    return TerminalSizeChangeReflowPlan(
        plan_terminal_resize_reflow(
            trigger="terminal_resize",
            changed=True,
            active_stream=active_stream,
            pending=pending,
        ),
        current_size,
        changed=True,
    )


def plan_terminal_stream_finish_reflow(*, pending: bool) -> TerminalResizeReflowPlan:
    """Plan stream-finalization repair for the real-terminal history surface.

    A deferred stream-time resize requires a source-backed scrollback rebuild.
    Python retains the whole assistant stream as one mutable live tail. This
    corresponds to Rust ``ConsolidationScrollbackReflow::Required``: after
    consolidation, rebuild scrollback from the canonical source-backed cells.
    """

    return TerminalResizeReflowPlan("replay_history_scrollback", pending=False)


def run_terminal_resize_reflow_plan(
    plan: TerminalResizeReflowPlan,
    *,
    repaint_history_viewport: Callable[[], None],
    replay_history_scrollback: Callable[[], None],
) -> bool:
    """Execute the terminal resize/reflow action chosen by app planning."""

    if plan.action == "repaint_history_viewport":
        repaint_history_viewport()
        return True
    if plan.action == "replay_history_scrollback":
        replay_history_scrollback()
        return True
    return False


def run_terminal_layout_activation(
    *,
    terminal_active: bool,
    state: TerminalResizeRuntimeState,
    current_size: os.terminal_size,
    render_bottom_pane: Callable[[], None],
) -> tuple[bool, TerminalResizeRuntimeState]:
    """Activate the terminal layout surface for the scrollback product path."""

    if not terminal_active:
        return False, state
    next_state = state.activated(current_size)
    render_bottom_pane()
    return True, next_state


def run_terminal_layout_deactivation(
    *,
    terminal_active: bool,
    state: TerminalResizeRuntimeState,
    reset_terminal_scroll_region: Callable[[], None],
) -> tuple[bool, TerminalResizeRuntimeState]:
    """Deactivate the terminal layout surface and reset terminal scroll state."""

    if not terminal_active:
        return False, state
    next_state = state.deactivated()
    reset_terminal_scroll_region()
    return False, next_state


def run_terminal_size_change_reflow(
    *,
    terminal_active: bool,
    state: TerminalResizeRuntimeState,
    current_size: os.terminal_size,
    active_stream: bool,
    pending: bool,
    reset_terminal_scroll_region: Callable[[], None],
    run_reflow_plan: Callable[[TerminalResizeReflowPlan], None],
    enter_resize_handling: Callable[[TerminalResizeRuntimeState], None] | None = None,
    exit_resize_handling: Callable[[TerminalResizeRuntimeState], None] | None = None,
) -> tuple[TerminalResizeRuntimeState, bool]:
    """Execute the terminal-size resize path for the scrollback product route."""

    if not terminal_active or state.handling_resize:
        return state, pending

    size_plan = plan_terminal_size_change_reflow(
        previous_size=state.last_terminal_size,
        current_size=current_size,
        active_stream=active_stream,
        pending=pending,
    )
    next_state = state.after_size_plan(size_plan)
    if not size_plan.changed:
        return next_state, pending

    plan = size_plan.reflow
    if plan.action == "defer_until_stream_finish":
        run_reflow_plan(plan)
        return next_state, plan.pending

    handling_state = next_state.begin_handling()
    if enter_resize_handling is not None:
        enter_resize_handling(handling_state)
    try:
        reset_terminal_scroll_region()
        run_reflow_plan(plan)
    finally:
        handling_state = handling_state.end_handling()
        if exit_resize_handling is not None:
            exit_resize_handling(handling_state)
    return handling_state, plan.pending


def render_history_projection_lines(
    history_projection_cells: Iterable[str],
    wrap_cell: Callable[[str], Iterable[str]],
) -> list[str]:
    """Render retained source-backed terminal history cells for resize replay."""

    lines: list[str] = []
    for cell in history_projection_cells:
        if lines and lines[-1] != "":
            lines.append("")
        lines.extend(str(line) for line in wrap_cell(cell))
    return lines


def render_terminal_typed_transcript_lines(
    transcript_cells: Sequence[Any],
    width: int,
) -> list[str]:
    """Render app-owned typed HistoryCell values for terminal replay."""

    state = ResizeReflowState(transcript_cells=list(transcript_cells))
    rendered = state.render_transcript_lines_for_reflow(max(1, int(width)))
    return [str(line.text) for line in rendered.lines]


def run_terminal_typed_transcript_viewport_repaint(
    writer: TextIO,
    transcript_cells: Sequence[Any],
    width: int,
    *,
    terminal_active: bool,
    history_bottom_row: Callable[[], int],
    terminal_columns: Callable[[], int],
) -> bool:
    if not terminal_active:
        return False
    painted = repaint_terminal_history_viewport(
        writer,
        render_terminal_typed_transcript_lines(transcript_cells, width),
        bottom_row=history_bottom_row(),
        columns=terminal_columns(),
    )
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()
    return painted


def run_terminal_typed_transcript_scrollback_replay(
    writer: TextIO,
    transcript_cells: Sequence[Any],
    width: int,
    *,
    live_status_footprint_active: bool,
    insert_replayed_history_lines: Callable[[list[str], bool], None],
    apply_history_state: Callable[[TerminalHistoryState], None],
    history_state: TerminalHistoryState,
) -> bool:
    replay_state = terminal_history_state_for_resize_replay(history_state)
    apply_history_state(replay_state)
    clear_terminal_for_resize_replay(writer)
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()
    lines = render_terminal_typed_transcript_lines(transcript_cells, width)
    if not lines:
        return False
    insert_replayed_history_lines(lines, live_status_footprint_active)
    return True


def replay_terminal_history_projection(
    lines: Sequence[str],
    insert_lines: Callable[[list[str]], None],
) -> bool:
    """Replay retained terminal history lines, returning whether anything drew."""

    materialized = list(lines)
    if not materialized:
        return False
    insert_lines(materialized)
    return True


def replay_terminal_history_projection_cells(
    history_projection_cells: Iterable[str],
    wrap_cell: Callable[[str], Iterable[str]],
    insert_lines: Callable[[list[str]], None],
) -> bool:
    """Replay retained terminal history cells into ordinary scrollback."""

    return replay_terminal_history_projection(
        render_history_projection_lines(history_projection_cells, wrap_cell),
        insert_lines,
    )


def replay_terminal_history_projection_cells_for_width(
    history_projection_cells: Iterable[str],
    wrap_width: int,
    insert_lines: Callable[[list[str]], None],
) -> bool:
    """Replay retained terminal history cells using insert_history wrapping."""

    return replay_terminal_history_projection_cells(
        history_projection_cells,
        lambda cell: terminal_history_cell_lines(cell, wrap_width),
        insert_lines,
    )


def repaint_terminal_history_viewport(
    writer: TextIO,
    lines: Sequence[str],
    *,
    bottom_row: int,
    columns: int,
) -> bool:
    """Repaint retained transcript tail above the live bottom pane."""

    if bottom_row < 1:
        return False
    reset_scroll_region(writer)
    for row in range(1, bottom_row + 1):
        clear_line_at(writer, row)
    visible_lines = list(lines)[-bottom_row:]
    start_row = max(1, bottom_row - len(visible_lines) + 1)
    width = max(1, columns - 1)
    for offset, line in enumerate(visible_lines):
        write_at(writer, start_row + offset, 1, _truncate_display_width(line, width))
    return True


def repaint_terminal_history_projection_viewport(
    writer: TextIO,
    history_projection_cells: Iterable[str],
    wrap_cell: Callable[[str], Iterable[str]],
    *,
    bottom_row: int,
    columns: int,
) -> bool:
    """Repaint retained terminal history cells above the live bottom pane."""

    return repaint_terminal_history_viewport(
        writer,
        render_history_projection_lines(history_projection_cells, wrap_cell),
        bottom_row=bottom_row,
        columns=columns,
    )


def repaint_terminal_history_projection_viewport_and_flush(
    writer: TextIO,
    history_projection_cells: Iterable[str],
    wrap_cell: Callable[[str], Iterable[str]],
    *,
    bottom_row: int,
    columns: int,
) -> bool:
    """Repaint retained terminal history cells and flush the terminal writer."""

    painted = repaint_terminal_history_projection_viewport(
        writer,
        history_projection_cells,
        wrap_cell,
        bottom_row=bottom_row,
        columns=columns,
    )
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()
    return painted


def repaint_terminal_history_projection_viewport_for_width_and_flush(
    writer: TextIO,
    history_projection_cells: Iterable[str],
    wrap_width: int,
    *,
    bottom_row: int,
    columns: int,
) -> bool:
    """Repaint retained terminal history cells using insert_history wrapping."""

    return repaint_terminal_history_projection_viewport_and_flush(
        writer,
        history_projection_cells,
        lambda cell: terminal_history_cell_lines(cell, wrap_width),
        bottom_row=bottom_row,
        columns=columns,
    )


def terminal_history_state_for_resize_replay(
    history_state: TerminalHistoryState,
) -> TerminalHistoryState:
    """Reset terminal history write markers before resize scrollback replay.

    The retained projection cells remain the source of truth, but the ordinary
    terminal scrollback is about to be cleared and rebuilt.  Resetting the
    insert-history write markers before replay avoids preserving stale gap or
    blank-line state from the pre-resize terminal surface.
    """

    return history_state.with_write_markers(
        history_has_content=False,
        history_ended_with_blank=False,
    )


def repaint_terminal_history_state_viewport_for_width_and_flush(
    writer: TextIO,
    history_state: TerminalHistoryState,
    wrap_width: int,
    *,
    bottom_row: int,
    columns: int,
) -> bool:
    """Repaint retained terminal history state above the live bottom pane."""

    return repaint_terminal_history_projection_viewport_for_width_and_flush(
        writer,
        history_state.projection_cells,
        wrap_width,
        bottom_row=bottom_row,
        columns=columns,
    )


def run_terminal_history_state_viewport_repaint_for_width(
    writer: TextIO,
    history_state: TerminalHistoryState,
    wrap_width: int,
    *,
    terminal_active: bool,
    history_bottom_row: Callable[[], int],
    terminal_columns: Callable[[], int],
) -> bool:
    """Repaint retained history viewport when the terminal layout is active."""

    if not terminal_active:
        return False
    return repaint_terminal_history_state_viewport_for_width_and_flush(
        writer,
        history_state,
        wrap_width,
        bottom_row=history_bottom_row(),
        columns=terminal_columns(),
    )


def replay_terminal_history_scrollback_for_resize(
    writer: TextIO,
    history_projection_cells: Iterable[str],
    wrap_cell: Callable[[str], Iterable[str]],
    insert_lines: Callable[[list[str]], None],
    *,
    render_bottom_pane: Callable[[], None] | None = None,
) -> bool:
    """Clear and rebuild terminal scrollback from retained projection cells."""

    clear_terminal_for_resize_replay(writer)
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()
    replayed = replay_terminal_history_projection_cells(
        history_projection_cells,
        wrap_cell,
        insert_lines,
    )
    if render_bottom_pane is not None:
        render_bottom_pane()
    return replayed


def replay_terminal_history_scrollback_for_resize_width(
    writer: TextIO,
    history_projection_cells: Iterable[str],
    wrap_width: int,
    insert_lines: Callable[[list[str]], None],
    *,
    render_bottom_pane: Callable[[], None] | None = None,
) -> bool:
    """Clear and rebuild terminal scrollback using insert_history wrapping."""

    clear_terminal_for_resize_replay(writer)
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()
    replayed = replay_terminal_history_projection_cells_for_width(
        history_projection_cells,
        wrap_width,
        insert_lines,
    )
    if render_bottom_pane is not None:
        render_bottom_pane()
    return replayed


def replay_terminal_history_state_scrollback_for_resize_width(
    writer: TextIO,
    history_state: TerminalHistoryState,
    wrap_width: int,
    insert_lines: Callable[[list[str]], None],
    *,
    render_bottom_pane: Callable[[], None] | None = None,
) -> bool:
    """Clear and rebuild terminal scrollback from retained history state."""

    return replay_terminal_history_scrollback_for_resize_width(
        writer,
        history_state.projection_cells,
        wrap_width,
        insert_lines,
        render_bottom_pane=render_bottom_pane,
    )


def run_terminal_history_state_scrollback_replay_for_resize_width(
    writer: TextIO,
    history_state: TerminalHistoryState,
    wrap_width: int,
    insert_lines: Callable[[list[str]], None],
    *,
    apply_history_state: Callable[[TerminalHistoryState], None],
    render_bottom_pane: Callable[[], None] | None = None,
) -> bool:
    """Reset history markers, clear scrollback, and replay retained history."""

    replay_state = terminal_history_state_for_resize_replay(history_state)
    apply_history_state(replay_state)
    return replay_terminal_history_state_scrollback_for_resize_width(
        writer,
        replay_state,
        wrap_width,
        insert_lines,
        render_bottom_pane=render_bottom_pane,
    )


def run_terminal_history_state_scrollback_replay_insert_for_resize_width(
    writer: TextIO,
    history_state: TerminalHistoryState,
    wrap_width: int,
    *,
    live_status_footprint_active: bool,
    apply_history_state: Callable[[TerminalHistoryState], None],
    insert_replayed_history_lines: Callable[[list[str], bool], None],
    render_bottom_pane: Callable[[], None] | None = None,
) -> bool:
    """Replay retained history through insert-history after resize.

    Rust ``app::resize_reflow`` owns the clear/rebuild ordering for resize
    replay. The terminal runner supplies the insert-history callback, while
    this boundary decides that replayed rows should not clear or render the
    bottom pane mid-batch and should reserve the active live-status footprint.
    """

    return run_terminal_history_state_scrollback_replay_for_resize_width(
        writer,
        history_state,
        wrap_width,
        lambda lines: insert_replayed_history_lines(lines, live_status_footprint_active),
        apply_history_state=apply_history_state,
        render_bottom_pane=render_bottom_pane,
    )


def _truncate_display_width(text: str, width: int) -> str:
    if width <= 0:
        return ""
    current = 0
    out: list[str] = []
    for char in str(text):
        char_width = display_width(char)
        if current + char_width > width:
            break
        out.append(char)
        current += char_width
    return "".join(out)


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
    "TerminalExternalRepaintRunner",
    "TerminalResizeReflowPlan",
    "TerminalResizeRuntimeState",
    "TerminalResizeCoordinator",
    "TerminalResizeHistoryReplayer",
    "TerminalSizeChangeReflowPlan",
    "begin_initial_history_replay_buffer_plan",
    "begin_thread_switch_history_replay_buffer_plan",
    "buffer_initial_history_replay_display_lines",
    "clear_terminal_for_resize_replay",
    "display_lines_for_history_insert",
    "finish_initial_history_replay_buffer_plan",
    "handle_draw_size_change_plan",
    "insert_history_cell_lines_plan",
    "history_line_wrap_policy",
    "maybe_run_resize_reflow",
    "maybe_finish_stream_reflow_plan",
    "plan_terminal_resize_reflow",
    "plan_terminal_size_change_reflow",
    "plan_terminal_stream_finish_reflow",
    "repaint_terminal_history_viewport",
    "repaint_terminal_history_projection_viewport",
    "repaint_terminal_history_projection_viewport_and_flush",
    "repaint_terminal_history_projection_viewport_for_width_and_flush",
    "repaint_terminal_history_state_viewport_for_width_and_flush",
    "reflow_transcript_now",
    "render_history_projection_lines",
    "render_transcript_lines_for_reflow",
    "replay_terminal_history_projection",
    "replay_terminal_history_projection_cells",
    "replay_terminal_history_projection_cells_for_width",
    "replay_terminal_history_scrollback_for_resize",
    "replay_terminal_history_scrollback_for_resize_width",
    "replay_terminal_history_state_scrollback_for_resize_width",
    "reset_history_emission_state",
    "run_terminal_layout_activation",
    "run_terminal_layout_deactivation",
    "run_terminal_history_state_viewport_repaint_for_width",
    "run_terminal_history_state_scrollback_replay_for_resize_width",
    "run_terminal_history_state_scrollback_replay_insert_for_resize_width",
    "run_terminal_resize_reflow_plan",
    "run_terminal_size_change_reflow",
    "should_mark_reflow_as_stream_time",
    "terminal_history_state_for_resize_replay",
    "trailing_run_start",
]
