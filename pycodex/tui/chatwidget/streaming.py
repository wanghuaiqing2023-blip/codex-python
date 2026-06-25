"""Streaming transcript state helpers for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/streaming.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Optional, Tuple

from .._porting import RustTuiModule
from .status_state import StatusIndicatorState, StatusState, TerminalTitleStatusKind

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::streaming",
    source="codex/codex-rs/tui/src/chatwidget/streaming.rs",
    status="complete",
)


class MessagePhase(str, Enum):
    Commentary = "commentary"
    FinalAnswer = "final_answer"


class ModeKind(str, Enum):
    Chat = "chat"
    Plan = "plan"


class CommitTickScope(str, Enum):
    AnyMode = "any_mode"
    CatchUpOnly = "catch_up_only"


@dataclass
class StreamControllerState:
    queued_lines: int = 0
    live_tail: bool = False
    source: str = ""
    tail_lines: List[str] = field(default_factory=list)
    finalized_cells: List[Tuple[str, str]] = field(default_factory=list)

    def is_idle(self) -> bool:
        return self.queued_lines == 0

    def push(self, delta: str) -> bool:
        self.source += delta
        lines = [line for line in delta.splitlines() if line]
        if not lines and delta:
            lines = [delta]
        self.tail_lines.extend(lines)
        self.queued_lines += len(lines)
        self.live_tail = bool(self.tail_lines)
        return bool(lines)

    def queued_lines_count(self) -> int:
        return self.queued_lines

    def has_live_tail(self) -> bool:
        return self.live_tail

    def current_tail_lines(self) -> List[str]:
        return list(self.tail_lines)

    def current_tail_display_lines(self) -> List[str]:
        return list(self.tail_lines)

    def finalize(self, kind: str) -> Tuple[Optional[Tuple[str, str]], Optional[str]]:
        cell = None if not self.source else (kind, self.source)
        source = self.source or None
        self.queued_lines = 0
        self.live_tail = False
        self.tail_lines = []
        if cell is not None:
            self.finalized_cells.append(cell)
        return cell, source

    def commit_one(self) -> List[Tuple[str, str]]:
        if self.queued_lines <= 0 or not self.tail_lines:
            self.queued_lines = 0
            return []
        line = self.tail_lines.pop(0)
        self.queued_lines -= 1
        self.live_tail = bool(self.tail_lines)
        return [("stream_line", line)]


@dataclass
class StreamingWidgetState:
    """Small semantic stand-in for the streaming fields on Rust ``ChatWidget``."""

    status_state: StatusState = field(default_factory=StatusState)
    reasoning_buffer: str = ""
    full_reasoning_buffer: str = ""
    task_running: bool = False
    status_indicator_visible: bool = True
    stream_controller: StreamControllerState | None = None
    plan_stream_controller: StreamControllerState | None = None
    active_cell_kind: str | None = None
    active_cell_revision: int = 0
    task_complete_pending: bool = False
    input_queue_pending_steers: bool = False
    unified_exec_wait_streak: bool = False
    mode_kind: ModeKind = ModeKind.Chat
    plan_item_active: bool = False
    plan_delta_buffer: str = ""
    saw_plan_item_this_turn: bool = False
    latest_proposed_plan_markdown: Optional[str] = None
    needs_final_message_separator: bool = False
    had_work_activity: bool = False
    active_exec_cell_flushed: int = 0
    unified_exec_wait_flushes: int = 0
    adaptive_chunking_resets: int = 0
    interrupt_queue: List[Callable[["StreamingWidgetState"], None]] = field(default_factory=list)
    task_running_metrics_refreshes: int = 0
    start_commit_animation_events: int = 0
    stop_commit_animation_events: int = 0
    consolidation_events: List[Tuple[str, str]] = field(default_factory=list)
    redraw_requests: int = 0
    history: List[Tuple[str, str]] = field(default_factory=list)

    def restore_reasoning_status_header(self) -> None:
        header = extract_first_bold(self.reasoning_buffer)
        if header is not None:
            self.status_state.terminal_title_status_kind = TerminalTitleStatusKind.Thinking
            self.set_status_header(header)
        elif self.task_running:
            self.status_state.terminal_title_status_kind = TerminalTitleStatusKind.Working
            self.set_status_header("Working")

    def stream_controllers_idle(self) -> bool:
        return (self.stream_controller is None or self.stream_controller.is_idle()) and (
            self.plan_stream_controller is None or self.plan_stream_controller.is_idle()
        )

    def flush_answer_stream_with_separator(self) -> None:
        had_stream_controller = self.stream_controller is not None
        if self.stream_controller is not None:
            scrollback_reflow = "required" if self.stream_controller.has_live_tail() else "if_resize_reflow_ran"
            self.clear_active_stream_tail()
            cell, source = self.stream_controller.finalize("agent_stream")
            if cell is not None and scrollback_reflow != "required":
                self.history.append(cell)
            if source is not None:
                self.consolidation_events.append(("agent_message", source.strip()))
            self.stream_controller = None
        self.adaptive_chunking_resets += 1
        if had_stream_controller and self.stream_controllers_idle():
            self.stop_commit_animation_events += 1

    def maybe_restore_status_indicator_after_stream_idle(self) -> bool:
        if (
            not self.status_state.pending_status_indicator_restore
            or not self.task_running
            or not self.stream_controllers_idle()
        ):
            return False
        self.ensure_status_indicator()
        self.set_status(self.status_state.current_status)
        self.status_state.pending_status_indicator_restore = False
        return True

    def on_agent_reasoning_delta(self, delta: str) -> None:
        self.reasoning_buffer += delta
        if self.unified_exec_wait_streak:
            self.request_redraw()
            return
        header = extract_first_bold(self.reasoning_buffer)
        if header is not None:
            self.status_state.terminal_title_status_kind = TerminalTitleStatusKind.Thinking
            self.set_status_header(header)
        self.request_redraw()

    def on_reasoning_section_break(self) -> None:
        self.full_reasoning_buffer += self.reasoning_buffer
        self.full_reasoning_buffer += "\n\n"
        self.reasoning_buffer = ""

    def on_agent_reasoning_final(self) -> None:
        self.full_reasoning_buffer += self.reasoning_buffer
        if self.full_reasoning_buffer:
            self.history.append(("reasoning_summary", self.full_reasoning_buffer))
        self.reasoning_buffer = ""
        self.full_reasoning_buffer = ""
        self.request_redraw()

    def finalize_completed_assistant_message(self, message: Optional[str]) -> None:
        if self.stream_controller is None and message:
            self.consolidation_events.append(("agent_message", message.strip()))
            self.adaptive_chunking_resets += 1
            self.handle_stream_finished()
            self.request_redraw()
            return
        self.flush_answer_stream_with_separator()
        self.handle_stream_finished()
        self.request_redraw()

    def on_agent_message_delta(self, delta: str) -> None:
        self.handle_streaming_delta(delta)

    def on_plan_delta(self, delta: str) -> None:
        if self.mode_kind is not ModeKind.Plan:
            return
        if not self.plan_item_active:
            self.plan_item_active = True
            self.plan_delta_buffer = ""
        self.plan_delta_buffer += delta
        if self.plan_stream_controller is None:
            self.flush_unified_exec_wait_streak()
            self.flush_active_cell()
            self.plan_stream_controller = StreamControllerState()
        if self.plan_stream_controller.push(delta):
            self.start_commit_animation_events += 1
            self.run_catch_up_commit_tick()
        self.sync_active_stream_tail()
        self.request_redraw()

    def on_plan_item_completed(self, text: str) -> None:
        streamed_plan = self.plan_delta_buffer.strip()
        plan_text = text if text.strip() else streamed_plan
        if plan_text.strip():
            self.history.append(("agent_markdown", plan_text))
            self.latest_proposed_plan_markdown = plan_text
        should_restore_after_stream = self.plan_stream_controller is not None
        self.plan_delta_buffer = ""
        self.plan_item_active = False
        self.saw_plan_item_this_turn = True
        consolidated_source = None
        finalized_cell = None
        if self.plan_stream_controller is not None:
            had_live_tail = self.plan_stream_controller.has_live_tail()
            self.clear_active_stream_tail()
            cell, source = self.plan_stream_controller.finalize("plan_stream")
            consolidated_source = source
            finalized_cell = None if had_live_tail else cell
            self.plan_stream_controller = None
        if finalized_cell is not None:
            self.history.append(finalized_cell)
            if consolidated_source is not None:
                self.consolidation_events.append(("proposed_plan", consolidated_source))
        if plan_text:
            self.history.append(("proposed_plan", plan_text))
        elif consolidated_source is not None:
            self.consolidation_events.append(("proposed_plan", consolidated_source))
        if should_restore_after_stream:
            self.status_state.pending_status_indicator_restore = bool(self.task_running)
            self.maybe_restore_status_indicator_after_stream_idle()

    def on_stream_error(self, message: str, additional_details: str | None = None) -> None:
        self.status_state.remember_retry_status_header()
        self.ensure_status_indicator()
        self.status_state.terminal_title_status_kind = TerminalTitleStatusKind.Thinking
        self.set_status(StatusIndicatorState(header=message, details=additional_details))

    def on_agent_message_item_completed(
        self,
        message: str,
        phase: MessagePhase | None,
        from_replay: bool = False,
    ) -> None:
        visible = message.strip()
        self.finalize_completed_assistant_message(visible or None)
        if (phase is MessagePhase.FinalAnswer or phase is None) and visible:
            self.history.append(("agent_markdown", visible))
        self.status_state.pending_status_indicator_restore = (
            bool(self.input_queue_pending_steers)
            if phase is MessagePhase.FinalAnswer or phase is None
            else True
        )
        self.maybe_restore_status_indicator_after_stream_idle()
        self.request_redraw()

    def on_commit_tick(self) -> None:
        self.run_commit_tick()

    def run_commit_tick(self) -> None:
        self.run_commit_tick_with_scope(CommitTickScope.AnyMode)

    def run_catch_up_commit_tick(self) -> None:
        self.run_commit_tick_with_scope(CommitTickScope.CatchUpOnly)

    def run_commit_tick_with_scope(self, scope: CommitTickScope) -> None:
        had_controller = self.stream_controller is not None or self.plan_stream_controller is not None
        if scope is CommitTickScope.CatchUpOnly:
            self.sync_active_stream_tail()
            if self.task_running:
                self.task_running_metrics_refreshes += 1
            return
        cells: List[Tuple[str, str]] = []
        if self.stream_controller is not None:
            cells.extend(self.stream_controller.commit_one())
        if self.plan_stream_controller is not None:
            cells.extend(self.plan_stream_controller.commit_one())
        for cell in cells:
            self.hide_status_indicator()
            self.history.append(cell)
        self.sync_active_stream_tail()
        if had_controller and self.stream_controllers_idle():
            self.maybe_restore_status_indicator_after_stream_idle()
            self.stop_commit_animation_events += 1
        if self.task_running:
            self.task_running_metrics_refreshes += 1

    def flush_interrupt_queue(self) -> None:
        queued = list(self.interrupt_queue)
        self.interrupt_queue = []
        for callback in queued:
            callback(self)

    def defer_or_handle(
        self,
        push: Callable[[List[Callable[["StreamingWidgetState"], None]]], None],
        handle: Callable[["StreamingWidgetState"], None],
    ) -> None:
        if self.stream_controller is not None or self.interrupt_queue:
            push(self.interrupt_queue)
        else:
            handle(self)

    def handle_stream_finished(self) -> None:
        if self.task_complete_pending:
            self.hide_status_indicator()
            self.task_complete_pending = False
        self.flush_interrupt_queue()

    def handle_streaming_delta(self, delta: str) -> None:
        if self.stream_controller is None:
            self.flush_unified_exec_wait_streak()
            self.flush_active_cell()
            if self.needs_final_message_separator and self.had_work_activity:
                self.history.append(("final_message_separator", ""))
                self.needs_final_message_separator = False
            elif self.needs_final_message_separator:
                self.needs_final_message_separator = False
            self.stream_controller = StreamControllerState()
        if self.stream_controller.push(delta):
            self.start_commit_animation_events += 1
            self.run_catch_up_commit_tick()
        self.sync_active_stream_tail()
        self.request_redraw()

    def active_cell_is_stream_tail(self) -> bool:
        return self.active_cell_kind in {"streaming_agent_tail", "streaming_plan_tail"}

    def has_active_stream_tail(self) -> bool:
        return (
            self.stream_controller is not None or self.plan_stream_controller is not None
        ) and self.active_cell_is_stream_tail()

    def clear_active_stream_tail(self) -> bool:
        if not self.active_cell_is_stream_tail():
            return False
        self.active_cell_kind = None
        self.bump_active_cell_revision()
        return True

    def sync_active_stream_tail(self) -> None:
        if self.stream_controller is not None:
            tail_lines = self.stream_controller.current_tail_lines()
            if not tail_lines:
                self.clear_active_stream_tail()
                return
            self.hide_status_indicator()
            self.active_cell_kind = "streaming_agent_tail"
            self.bump_active_cell_revision()
            return
        if self.plan_stream_controller is not None:
            tail_lines = self.plan_stream_controller.current_tail_display_lines()
            if not tail_lines:
                self.clear_active_stream_tail()
                return
            self.hide_status_indicator()
            self.active_cell_kind = "streaming_plan_tail"
            self.bump_active_cell_revision()
            return
        self.clear_active_stream_tail()

    def flush_unified_exec_wait_streak(self) -> None:
        if self.unified_exec_wait_streak:
            self.unified_exec_wait_streak = False
            self.unified_exec_wait_flushes += 1

    def flush_active_cell(self) -> None:
        if self.active_cell_kind and not self.active_cell_is_stream_tail():
            self.active_cell_kind = None
            self.active_exec_cell_flushed += 1

    def ensure_status_indicator(self) -> None:
        self.status_indicator_visible = True

    def hide_status_indicator(self) -> None:
        self.status_indicator_visible = False

    def set_status_header(self, header: str) -> None:
        self.status_state.current_status.header = header

    def set_status(self, status: StatusIndicatorState) -> None:
        self.status_state.current_status = StatusIndicatorState(
            header=status.header,
            details=status.details,
            details_max_lines=status.details_max_lines,
        )

    def bump_active_cell_revision(self) -> None:
        self.active_cell_revision += 1

    def request_redraw(self) -> None:
        self.redraw_requests += 1


def extract_first_bold(text: str) -> Optional[str]:
    """Extract the first non-empty Markdown ``**bold**`` span like Rust."""

    i = 0
    while i + 1 < len(text):
        if text[i] == "*" and text[i + 1] == "*":
            start = i + 2
            j = start
            while j + 1 < len(text):
                if text[j] == "*" and text[j + 1] == "*":
                    inner = text[start:j].strip()
                    return inner or None
                j += 1
            return None
        i += 1
    return None


__all__ = [
    "CommitTickScope",
    "MessagePhase",
    "ModeKind",
    "RUST_MODULE",
    "StreamControllerState",
    "StreamingWidgetState",
    "extract_first_bold",
]
