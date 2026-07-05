"""Semantic port of Rust ``codex-tui::streaming::controller``.

This module owns the two-region streaming controller contract: complete source
lines are queued into a stable region, table-shaped regions remain mutable tail
until finalization, and resize/render-mode changes rebuild pending queue state
without replaying already emitted lines.  Python keeps markdown rendering as a
semantic plain-line dependency boundary; the controller state machine mirrors
Rust's ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from .._porting import RustTuiModule
from ..history_cell import HistoryRenderMode
from ..history_cell.messages import AgentMessageCell
from ..history_cell.plans import ProposedPlanStreamCell
from ..line_truncation import Line
from ..markdown_stream import MarkdownStreamCollector
from ..terminal_hyperlinks import HyperlinkLine, line_text, plain_hyperlink_lines, visible_lines
from . import StreamState, test_cwd as _streaming_test_cwd
from .table_holdback import TableHoldbackScanner, TableHoldbackState, table_holdback_state


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="streaming::controller",
    source="codex/codex-rs/tui/src/streaming/controller.rs",
    status="complete",
)


@dataclass
class StablePrefixLenCache:
    source_start: int
    width: Optional[int]
    stable_prefix_len: int


@dataclass
class StreamCore:
    state: StreamState
    width: Optional[int]
    raw_source: str
    rendered_lines: list[HyperlinkLine]
    enqueued_stable_len: int
    emitted_stable_len: int
    cwd: Path
    render_mode: HistoryRenderMode
    stable_prefix_len_cache: Optional[StablePrefixLenCache]
    holdback_scanner: TableHoldbackScanner

    @classmethod
    def new(
        cls,
        width: Optional[int],
        cwd: str | Path,
        render_mode: HistoryRenderMode = HistoryRenderMode.RICH,
    ) -> "StreamCore":
        cwd_path = Path(cwd)
        return cls(
            state=StreamState.new(width, cwd_path, collector=MarkdownStreamCollector.new(width, cwd_path)),
            width=width,
            raw_source="",
            rendered_lines=[],
            enqueued_stable_len=0,
            emitted_stable_len=0,
            cwd=cwd_path,
            render_mode=render_mode,
            stable_prefix_len_cache=None,
            holdback_scanner=TableHoldbackScanner.new(),
        )

    def push_delta(self, delta: str) -> bool:
        if delta:
            self.state.has_seen_delta = True
        self.state.collector.push_delta(delta)
        if "\n" not in delta:
            return False
        committed_source = self.state.collector.commit_complete_source()
        if committed_source is None:
            return False
        self.raw_source += committed_source
        self.holdback_scanner.push_source_chunk(committed_source)
        self.recompute_streaming_render()
        return self.sync_stable_queue()

    def finalize_remaining(self) -> list[HyperlinkLine]:
        remainder = self.state.collector.finalize_and_drain_source()
        if remainder:
            self.raw_source += remainder
            self.holdback_scanner.push_source_chunk(remainder)
        rendered = self.render_source(self.raw_source)
        if self.emitted_stable_len >= len(rendered):
            return []
        return rendered[self.emitted_stable_len :]

    def tick(self) -> list[HyperlinkLine]:
        step = self.state.step()
        self.emitted_stable_len += len(step)
        return list(step)

    def tick_batch(self, max_lines: int) -> list[HyperlinkLine]:
        if max_lines <= 0:
            return []
        step = self.state.drain_n(max_lines)
        self.emitted_stable_len += len(step)
        return list(step)

    def is_idle(self) -> bool:
        return self.state.is_idle()

    def queued_lines(self) -> int:
        return self.state.queued_len()

    def oldest_queued_age(self, now: Optional[float] = None) -> Optional[float]:
        return self.state.oldest_queued_age(now)

    def current_tail_lines(self) -> list[HyperlinkLine]:
        start = min(self.enqueued_stable_len, len(self.rendered_lines))
        return self.rendered_lines[start:]

    def has_tail(self) -> bool:
        return self.enqueued_stable_len < len(self.rendered_lines)

    def set_width(self, width: Optional[int]) -> None:
        if self.width == width:
            return
        had_pending_queue = self.state.queued_len() > 0
        had_live_tail = self.has_tail()
        self.width = width
        self.state.collector.set_width(width)
        if not self.raw_source:
            return
        self.recompute_streaming_render()
        self.emitted_stable_len = min(self.emitted_stable_len, len(self.rendered_lines))
        if had_pending_queue and self.emitted_stable_len == len(self.rendered_lines) and self.emitted_stable_len > 0:
            self.emitted_stable_len -= 1
        self.state.clear_queue()
        if self.emitted_stable_len > 0 and not had_pending_queue and not had_live_tail:
            self.enqueued_stable_len = len(self.rendered_lines)
            return
        self.rebuild_stable_queue_from_render()

    def reset(self) -> None:
        self.state.clear()
        self.raw_source = ""
        self.rendered_lines = []
        self.enqueued_stable_len = 0
        self.emitted_stable_len = 0
        self.stable_prefix_len_cache = None
        self.holdback_scanner.reset()

    def render_source(self, source: str) -> list[HyperlinkLine]:
        if self.render_mode is HistoryRenderMode.RAW:
            return plain_hyperlink_lines(_raw_source_lines(source))
        return plain_hyperlink_lines(_semantic_markdown_lines(source))

    def recompute_streaming_render(self) -> None:
        self.rendered_lines = self.render_source(self.raw_source)

    def set_render_mode(self, render_mode: HistoryRenderMode) -> None:
        if self.render_mode == render_mode:
            return
        had_pending_queue = self.state.queued_len() > 0
        had_live_tail = self.has_tail()
        self.render_mode = render_mode
        if not self.raw_source:
            return
        self.recompute_streaming_render()
        self.emitted_stable_len = min(self.emitted_stable_len, len(self.rendered_lines))
        if had_pending_queue and self.emitted_stable_len == len(self.rendered_lines) and self.emitted_stable_len > 0:
            self.emitted_stable_len -= 1
        self.state.clear_queue()
        if self.emitted_stable_len > 0 and not had_pending_queue and not had_live_tail:
            self.enqueued_stable_len = len(self.rendered_lines)
            return
        self.rebuild_stable_queue_from_render()

    def compute_target_stable_len(self) -> int:
        tail_budget = self.active_tail_budget_lines()
        return max(len(self.rendered_lines) - tail_budget, self.emitted_stable_len)

    def sync_stable_queue(self) -> bool:
        target = self.compute_target_stable_len()
        if target < self.enqueued_stable_len:
            self.state.clear_queue()
            if self.emitted_stable_len < target:
                self.state.enqueue(self.rendered_lines[self.emitted_stable_len : target])
            self.enqueued_stable_len = target
            return self.state.queued_len() > 0
        if target == self.enqueued_stable_len:
            return False
        self.state.enqueue(self.rendered_lines[self.enqueued_stable_len : target])
        self.enqueued_stable_len = target
        return True

    def rebuild_stable_queue_from_render(self) -> None:
        target = self.compute_target_stable_len()
        self.state.clear_queue()
        if self.emitted_stable_len < target:
            self.state.enqueue(self.rendered_lines[self.emitted_stable_len : target])
        self.enqueued_stable_len = target

    def active_tail_budget_lines(self) -> int:
        if self.render_mode is HistoryRenderMode.RAW:
            return 0
        state = self.holdback_scanner.state()
        if state.kind == "Confirmed" and state.table_start is not None:
            return self.tail_budget_from_source_start(state.table_start)
        if state.kind == "PendingHeader" and state.header_start is not None:
            return self.tail_budget_from_source_start(state.header_start)
        return 0

    def tail_budget_from_source_start(self, source_start: int) -> int:
        if source_start <= 0:
            return len(self.rendered_lines)
        prefix_len = self.stable_prefix_len_for_source_start(min(source_start, len(self.raw_source.encode("utf-8"))))
        return max(0, len(self.rendered_lines) - prefix_len)

    def stable_prefix_len_for_source_start(self, source_start: int) -> int:
        if (
            self.stable_prefix_len_cache is not None
            and self.stable_prefix_len_cache.source_start == source_start
            and self.stable_prefix_len_cache.width == self.width
        ):
            return self.stable_prefix_len_cache.stable_prefix_len
        prefix = _slice_by_byte_range(self.raw_source, 0, source_start)
        stable_prefix_len = len(self.render_source(prefix))
        self.stable_prefix_len_cache = StablePrefixLenCache(source_start, self.width, stable_prefix_len)
        return stable_prefix_len


@dataclass
class StreamController:
    core: StreamCore
    header_emitted: bool = False

    @classmethod
    def new(
        cls,
        width: Optional[int],
        cwd: str | Path,
        render_mode: HistoryRenderMode = HistoryRenderMode.RICH,
    ) -> "StreamController":
        return cls(StreamCore.new(width, cwd, render_mode))

    def push(self, delta: str) -> bool:
        return self.core.push_delta(delta)

    def finalize(self) -> tuple[Optional[AgentMessageCell], str]:
        remaining = self.core.finalize_remaining()
        raw_source = self.core.raw_source
        self.core.reset()
        if not remaining:
            return None, raw_source
        cell = self.emit(remaining)
        self.header_emitted = False
        return cell, raw_source

    def on_commit_tick(self) -> tuple[Optional[AgentMessageCell], bool]:
        return self._emit_tick(self.core.tick())

    def on_commit_tick_batch(self, max_lines: int) -> tuple[Optional[AgentMessageCell], bool]:
        return self._emit_tick(self.core.tick_batch(max_lines))

    def _emit_tick(self, lines: list[HyperlinkLine]) -> tuple[Optional[AgentMessageCell], bool]:
        cell = self.emit(lines) if lines else None
        return cell, self.core.is_idle()

    def queued_lines(self) -> int:
        return self.core.queued_lines()

    def oldest_queued_age(self, now: Optional[float] = None) -> Optional[float]:
        return self.core.oldest_queued_age(now)

    def current_tail_lines(self) -> list[HyperlinkLine]:
        return self.core.current_tail_lines()

    def tail_starts_stream(self) -> bool:
        return not self.header_emitted and self.core.emitted_stable_len == 0 and self.core.enqueued_stable_len == 0

    def has_live_tail(self) -> bool:
        return self.core.has_tail()

    def clear_queue(self) -> None:
        self.core.state.clear_queue()

    def set_width(self, width: Optional[int]) -> None:
        self.core.set_width(width)

    def set_render_mode(self, render_mode: HistoryRenderMode) -> None:
        self.core.set_render_mode(render_mode)

    def emit(self, lines: Iterable[HyperlinkLine]) -> AgentMessageCell:
        is_first_line = not self.header_emitted
        self.header_emitted = True
        return AgentMessageCell.new_hyperlink_lines(lines, is_first_line)


@dataclass
class PlanStreamController:
    core: StreamCore

    @classmethod
    def new(
        cls,
        width: Optional[int],
        cwd: str | Path,
        render_mode: HistoryRenderMode = HistoryRenderMode.RICH,
    ) -> "PlanStreamController":
        return cls(StreamCore.new(width, cwd, render_mode))

    def push(self, delta: str) -> bool:
        return self.core.push_delta(delta)

    def finalize(self) -> tuple[Optional[ProposedPlanStreamCell], str]:
        remaining = self.core.finalize_remaining()
        raw_source = self.core.raw_source
        self.core.reset()
        if not remaining:
            return None, raw_source
        return self.emit(remaining), raw_source

    def on_commit_tick(self) -> tuple[Optional[ProposedPlanStreamCell], bool]:
        return self._emit_tick(self.core.tick())

    def on_commit_tick_batch(self, max_lines: int) -> tuple[Optional[ProposedPlanStreamCell], bool]:
        return self._emit_tick(self.core.tick_batch(max_lines))

    def _emit_tick(self, lines: list[HyperlinkLine]) -> tuple[Optional[ProposedPlanStreamCell], bool]:
        return (self.emit(lines) if lines else None), self.core.is_idle()

    def queued_lines(self) -> int:
        return self.core.queued_lines()

    def has_live_tail(self) -> bool:
        return self.core.has_tail()

    def current_tail_lines(self) -> list[HyperlinkLine]:
        return self.core.current_tail_lines()

    def tail_starts_stream(self) -> bool:
        return self.core.emitted_stable_len == 0 and self.core.enqueued_stable_len == 0

    def current_tail_display_lines(self) -> list[Line]:
        return self.render_display_lines(self.current_tail_lines())

    def oldest_queued_age(self, now: Optional[float] = None) -> Optional[float]:
        return self.core.oldest_queued_age(now)

    def clear_queue(self) -> None:
        self.core.state.clear_queue()

    def set_width(self, width: Optional[int]) -> None:
        self.core.set_width(width)

    def set_render_mode(self, render_mode: HistoryRenderMode) -> None:
        self.core.set_render_mode(render_mode)

    def emit(self, lines: Iterable[HyperlinkLine]) -> ProposedPlanStreamCell:
        return ProposedPlanStreamCell(list(lines), stream_continuation=not self.tail_starts_stream())

    def render_display_lines(self, lines: Iterable[HyperlinkLine]) -> list[Line]:
        return visible_lines(lines)


def test_cwd() -> Path:
    return _streaming_test_cwd()


test_cwd.__test__ = False


def stream_controller(width: Optional[int] = None) -> StreamController:
    return StreamController.new(width, test_cwd(), HistoryRenderMode.RICH)


def plan_stream_controller(width: Optional[int] = None) -> PlanStreamController:
    return PlanStreamController.new(width, test_cwd(), HistoryRenderMode.RICH)


def lines_to_plain_strings(lines: Iterable[Line]) -> list[str]:
    return [line_text(line) for line in lines]


def hyperlink_lines_to_plain_strings(lines: Iterable[HyperlinkLine]) -> list[str]:
    return [line_text(line) for line in lines]


def collect_streamed_lines(deltas: Sequence[str], width: Optional[int] = None) -> list[str]:
    ctrl = stream_controller(width)
    out: list[str] = []
    for delta in deltas:
        ctrl.push(delta)
        while True:
            cell, idle = ctrl.on_commit_tick()
            if cell is not None:
                out.extend(lines_to_plain_strings(cell.display_lines(65535)))
            if idle:
                break
    cell, _ = ctrl.finalize()
    if cell is not None:
        out.extend(lines_to_plain_strings(cell.display_lines(65535)))
    return [line[2:] if line.startswith(("> ", "  ", "\u2022 ")) else line for line in out]


def collect_plan_streamed_lines(deltas: Sequence[str], width: Optional[int] = None) -> list[str]:
    ctrl = plan_stream_controller(width)
    out: list[str] = []
    for delta in deltas:
        ctrl.push(delta)
        while True:
            cell, idle = ctrl.on_commit_tick()
            if cell is not None:
                out.extend(lines_to_plain_strings(cell.display_lines(65535)))
            if idle:
                break
    cell, _ = ctrl.finalize()
    if cell is not None:
        out.extend(lines_to_plain_strings(cell.display_lines(65535)))
    return out


def _semantic_markdown_lines(source: str) -> list[Line]:
    # This intentionally preserves source-line ordering and table-shaped text.
    # Concrete ratatui Markdown rendering belongs to markdown/history-cell modules.
    return _raw_source_lines(source)


def _raw_source_lines(source: str) -> list[Line]:
    return [Line.from_text(line) for line in source.splitlines()]


def _slice_by_byte_range(text: str, start: int, end: int) -> str:
    encoded = text.encode("utf-8")
    start = max(0, min(start, len(encoded)))
    end = max(start, min(end, len(encoded)))
    return encoded[start:end].decode("utf-8", errors="ignore")


__all__ = [
    "PlanStreamController",
    "RUST_MODULE",
    "StablePrefixLenCache",
    "StreamController",
    "StreamCore",
    "collect_plan_streamed_lines",
    "collect_streamed_lines",
    "hyperlink_lines_to_plain_strings",
    "lines_to_plain_strings",
    "plan_stream_controller",
    "stream_controller",
    "table_holdback_state",
    "TableHoldbackState",
    "test_cwd",
]
