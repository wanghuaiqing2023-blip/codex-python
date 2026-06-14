"""Command lifecycle semantic helpers for ``codex-tui::chatwidget::command_lifecycle``.

The Rust module mostly coordinates ``ChatWidget`` runtime state.  This Python
slice ports the independently testable unified-exec tracking state machine:
process begin/end, recent output chunk retention, footer synchronization data,
and terminal wait streak transitions.  ExecCell grouping, transcript insertion,
AppEvent dispatch, and redraw behavior remain caller/runtime boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule
from ..exec_command import split_command_string, strip_bash_lc_and_escape
from .exec_state import UnifiedExecProcessSummary, UnifiedExecWaitStreak

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::command_lifecycle",
    source="codex/codex-rs/tui/src/chatwidget/command_lifecycle.rs",
)

MAX_RECENT_CHUNKS = 3


@dataclass(frozen=True)
class UnifiedExecInteractionCell:
    command_display: str | None
    stdin: str = ""


@dataclass
class CommandLifecycleState:
    unified_exec_processes: list[UnifiedExecProcessSummary] = field(default_factory=list)
    unified_exec_wait_streak: UnifiedExecWaitStreak | None = None
    footer_processes: list[str] = field(default_factory=list)
    flushed_wait_cells: list[UnifiedExecInteractionCell] = field(default_factory=list)

    def flush_unified_exec_wait_streak(self) -> UnifiedExecInteractionCell | None:
        wait = self.unified_exec_wait_streak
        if wait is None:
            return None
        self.unified_exec_wait_streak = None
        cell = UnifiedExecInteractionCell(wait.command_display, "")
        self.flushed_wait_cells.append(cell)
        return cell

    def track_unified_exec_process_begin(self, call_id: str, process_id: str | None, command: str) -> None:
        key = process_id or call_id
        command_display = command_display_from_raw(command)
        for process in self.unified_exec_processes:
            if process.key == key:
                process.call_id = call_id
                process.command_display = command_display
                process.recent_chunks.clear()
                self.sync_unified_exec_footer()
                return
        self.unified_exec_processes.append(
            UnifiedExecProcessSummary(
                key=key,
                call_id=call_id,
                command_display=command_display,
                recent_chunks=[],
            )
        )
        self.sync_unified_exec_footer()

    def track_unified_exec_process_end(self, call_id: str, process_id: str | None) -> bool:
        key = process_id or call_id
        before = len(self.unified_exec_processes)
        self.unified_exec_processes = [process for process in self.unified_exec_processes if process.key != key]
        changed = len(self.unified_exec_processes) != before
        if changed:
            self.sync_unified_exec_footer()
        return changed

    def sync_unified_exec_footer(self) -> list[str]:
        self.footer_processes = [process.command_display for process in self.unified_exec_processes]
        return list(self.footer_processes)

    def track_unified_exec_output_chunk(self, call_id: str, chunk: bytes | str) -> bool:
        process = next((process for process in self.unified_exec_processes if process.call_id == call_id), None)
        if process is None:
            return False
        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        for line in text.splitlines():
            trimmed = line.rstrip()
            if trimmed:
                process.recent_chunks.append(trimmed)
        if len(process.recent_chunks) > MAX_RECENT_CHUNKS:
            del process.recent_chunks[: len(process.recent_chunks) - MAX_RECENT_CHUNKS]
        return True

    def command_display_for_process(self, process_id: str) -> str | None:
        process = next((process for process in self.unified_exec_processes if process.key == process_id), None)
        return None if process is None else process.command_display

    def on_terminal_interaction(self, process_id: str, stdin: str) -> UnifiedExecInteractionCell | None:
        command_display = self.command_display_for_process(process_id)
        if stdin == "" and command_display is None:
            return None
        if stdin == "":
            if self.unified_exec_wait_streak is None:
                self.unified_exec_wait_streak = UnifiedExecWaitStreak.new(process_id, command_display)
            elif self.unified_exec_wait_streak.process_id == process_id:
                self.unified_exec_wait_streak.update_command_display(command_display)
            else:
                self.flush_unified_exec_wait_streak()
                self.unified_exec_wait_streak = UnifiedExecWaitStreak.new(process_id, command_display)
            return None

        if self.unified_exec_wait_streak is not None and self.unified_exec_wait_streak.process_id == process_id:
            self.flush_unified_exec_wait_streak()
        return UnifiedExecInteractionCell(command_display, stdin)


def command_display_from_raw(command: str) -> str:
    return strip_bash_lc_and_escape(split_command_string(command))


__all__ = [
    "CommandLifecycleState",
    "MAX_RECENT_CHUNKS",
    "RUST_MODULE",
    "UnifiedExecInteractionCell",
    "command_display_from_raw",
]
