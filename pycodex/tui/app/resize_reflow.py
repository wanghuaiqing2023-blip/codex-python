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
from typing import Any, Iterable

from .._porting import RustTuiModule, not_ported


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::resize_reflow",
    source="codex/codex-rs/tui/src/app/resize_reflow.rs",
    status="complete_slice",
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
    lines: list[HyperlinkLine]
    is_stream_continuation: bool = False


@dataclass(frozen=True, eq=True)
class ReflowRenderResult:
    lines: list[HyperlinkLine]


@dataclass
class InitialHistoryReplayBuffer:
    retained_lines: deque[HyperlinkLine] = field(default_factory=deque)
    render_from_transcript_tail: bool = False


@dataclass
class HistoryCell:
    lines: list[str]
    cell_type: str = "HistoryCell"
    stream_continuation: bool = False

    def display_hyperlink_lines_for_mode(self, width: int, mode: Any = None) -> list[HyperlinkLine]:
        return [HyperlinkLine.new(line) for line in self.lines]

    def is_stream_continuation(self) -> bool:
        return self.stream_continuation


@dataclass
class ResizeReflowState:
    transcript_cells: list[HistoryCell] = field(default_factory=list)
    has_emitted_history_lines: bool = False
    terminal_resize_reflow: Any = None
    raw_output_mode: bool = False
    resize_reflow_max_rows_value: int | None = None

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


def reset_history_emission_state(state: ResizeReflowState, deferred_history_lines: list[Any] | None = None) -> None:
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
) -> list[HyperlinkLine]:
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
    row_cap: int | None = None,
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
    reflowed: list[HyperlinkLine] = []
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


def _coerce_lines(lines: Iterable[HyperlinkLine | str]) -> list[HyperlinkLine]:
    return [line if isinstance(line, HyperlinkLine) else HyperlinkLine.new(line) for line in lines]


async def maybe_run_resize_reflow(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("app::resize_reflow::maybe_run_resize_reflow requires terminal/TUI runtime")


async def reflow_transcript_now(*args: Any, **kwargs: Any) -> Any:
    raise not_ported("app::resize_reflow::reflow_transcript_now requires terminal/TUI runtime")


__all__ = [
    "HistoryCell",
    "HistoryLineWrapPolicy",
    "HyperlinkLine",
    "InitialHistoryReplayBuffer",
    "RUST_MODULE",
    "ReflowCellDisplay",
    "ReflowRenderResult",
    "ResizeReflowState",
    "buffer_initial_history_replay_display_lines",
    "display_lines_for_history_insert",
    "history_line_wrap_policy",
    "maybe_run_resize_reflow",
    "reflow_transcript_now",
    "render_transcript_lines_for_reflow",
    "reset_history_emission_state",
    "should_mark_reflow_as_stream_time",
    "trailing_run_start",
]
