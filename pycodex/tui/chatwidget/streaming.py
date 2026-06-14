"""Streaming transcript state helpers for chat widgets.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/streaming.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .._porting import RustTuiModule
from .status_state import StatusIndicatorState, StatusState, TerminalTitleStatusKind

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::streaming",
    source="codex/codex-rs/tui/src/chatwidget/streaming.rs",
)


class MessagePhase(str, Enum):
    Commentary = "commentary"
    FinalAnswer = "final_answer"


@dataclass
class StreamControllerState:
    queued_lines: int = 0
    live_tail: bool = False

    def is_idle(self) -> bool:
        return self.queued_lines == 0


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
    redraw_requests: int = 0
    history: list[tuple[str, str]] = field(default_factory=list)

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
        if (phase is MessagePhase.FinalAnswer or phase is None) and visible:
            self.history.append(("agent_markdown", visible))
        self.status_state.pending_status_indicator_restore = (
            bool(self.input_queue_pending_steers)
            if phase is MessagePhase.FinalAnswer or phase is None
            else True
        )
        self.maybe_restore_status_indicator_after_stream_idle()
        self.request_redraw()

    def handle_stream_finished(self) -> None:
        if self.task_complete_pending:
            self.hide_status_indicator()
            self.task_complete_pending = False

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


def extract_first_bold(text: str) -> str | None:
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
    "MessagePhase",
    "RUST_MODULE",
    "StreamControllerState",
    "StreamingWidgetState",
    "extract_first_bold",
]
