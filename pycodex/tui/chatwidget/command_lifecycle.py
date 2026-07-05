"""Command lifecycle semantic helpers for ``codex-tui::chatwidget::command_lifecycle``.

The Rust module coordinates ``ChatWidget`` command execution lifecycle state.
This Python port models the module-owned state transitions with semantic data
objects instead of concrete ratatui/history-cell widgets: unified exec process
tracking, terminal wait streak flushing, active exec-cell grouping, output
deltas, suppressed duplicate unified waits, orphan completion handling, and
history insertion boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Union

from .._porting import RustTuiModule
from ..exec_command import split_command_string, strip_bash_lc_and_escape
from .exec_state import (
    RunningCommand,
    UnifiedExecProcessSummary,
    UnifiedExecWaitState,
    UnifiedExecWaitStreak,
    command_execution_command_and_parsed,
    is_unified_exec_source,
)

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::command_lifecycle",
    source="codex/codex-rs/tui/src/chatwidget/command_lifecycle.rs",
    status="complete",
)

MAX_RECENT_CHUNKS = 3
USER_SHELL_SOURCE = "user_shell"
UNIFIED_EXEC_INTERACTION_SOURCE = "unified_exec_interaction"
UNIFIED_EXEC_STARTUP_SOURCE = "unified_exec_startup"


@dataclass(frozen=True)
class UnifiedExecInteractionCell:
    command_display: Optional[str]
    stdin: str = ""


@dataclass
class CommandOutput:
    exit_code: int
    formatted_output: str
    aggregated_output: str


@dataclass
class SemanticExecCall:
    call_id: str
    command: List[str]
    parsed_cmd: List[Any]
    source: str
    output: Optional[CommandOutput] = None
    duration_ms: int = 0
    output_deltas: List[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.output is None


@dataclass
class SemanticExecCell:
    calls: List[SemanticExecCall] = field(default_factory=list)
    inserted_as_orphan: bool = False

    @classmethod
    def new(
        cls,
        call_id: str,
        command: List[str],
        parsed_cmd: List[Any],
        source: str,
    ) -> "SemanticExecCell":
        return cls([SemanticExecCall(call_id, list(command), list(parsed_cmd), source)])

    def contains_call(self, call_id: str) -> bool:
        return any(call.call_id == call_id for call in self.calls)

    def is_active(self) -> bool:
        return any(call.is_active for call in self.calls)

    def with_added_call(
        self,
        call_id: str,
        command: List[str],
        parsed_cmd: List[Any],
        source: str,
    ) -> bool:
        if not self.is_active() or self.contains_call(call_id):
            return False
        self.calls.append(SemanticExecCall(call_id, list(command), list(parsed_cmd), source))
        return True

    def append_output(self, call_id: str, delta: str) -> bool:
        for call in self.calls:
            if call.call_id == call_id and call.is_active:
                call.output_deltas.append(delta)
                return True
        return False

    def complete_call(self, call_id: str, output: CommandOutput, duration_ms: int) -> bool:
        for call in self.calls:
            if call.call_id == call_id:
                call.output = output
                call.duration_ms = max(0, int(duration_ms))
                return True
        return False

    def should_flush(self) -> bool:
        return not self.is_active()


@dataclass
class CommandExecutionItem:
    id: str
    command: str
    source: str
    process_id: Optional[str] = None
    command_actions: Iterable[Any] = field(default_factory=list)
    aggregated_output: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None


@dataclass
class CommandLifecycleState:
    bottom_pane_task_running: bool = True
    unified_exec_processes: List[UnifiedExecProcessSummary] = field(default_factory=list)
    unified_exec_wait_streak: Optional[UnifiedExecWaitStreak] = None
    footer_processes: List[str] = field(default_factory=list)
    flushed_wait_cells: List[UnifiedExecInteractionCell] = field(default_factory=list)
    running_commands: Dict[str, RunningCommand] = field(default_factory=dict)
    suppressed_exec_calls: Set[str] = field(default_factory=set)
    last_unified_wait: Optional[UnifiedExecWaitState] = None
    active_exec_cell: Optional[SemanticExecCell] = None
    history_cells: List[Union[SemanticExecCell, UnifiedExecInteractionCell]] = field(default_factory=list)
    status_indicator_visible: bool = False
    interrupt_hint_visible: bool = False
    terminal_title_status_kind: Optional[str] = None
    status: Optional[str] = None
    status_details: Optional[str] = None
    redraw_requested: bool = False
    active_cell_revision: int = 0
    answer_stream_flushes: int = 0
    had_work_activity: bool = False
    queued_input_sent: bool = False

    def flush_unified_exec_wait_streak(self) -> Optional[UnifiedExecInteractionCell]:
        wait = self.unified_exec_wait_streak
        if wait is None:
            return None
        self.unified_exec_wait_streak = None
        cell = UnifiedExecInteractionCell(wait.command_display, "")
        self.flushed_wait_cells.append(cell)
        return cell

    def track_unified_exec_process_begin(self, call_id: str, process_id: Optional[str], command: str) -> None:
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

    def track_unified_exec_process_end(self, call_id: str, process_id: Optional[str]) -> bool:
        key = process_id or call_id
        before = len(self.unified_exec_processes)
        self.unified_exec_processes = [process for process in self.unified_exec_processes if process.key != key]
        changed = len(self.unified_exec_processes) != before
        if changed:
            self.sync_unified_exec_footer()
        return changed

    def sync_unified_exec_footer(self) -> List[str]:
        self.footer_processes = [process.command_display for process in self.unified_exec_processes]
        return list(self.footer_processes)

    def track_unified_exec_output_chunk(self, call_id: str, chunk: Union[bytes, str]) -> bool:
        process = next((process for process in self.unified_exec_processes if process.call_id == call_id), None)
        if process is None:
            return False
        text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, (bytes, bytearray)) else str(chunk)
        for line in text.splitlines():
            trimmed = line.strip()
            if trimmed:
                process.recent_chunks.append(trimmed)
        if len(process.recent_chunks) > MAX_RECENT_CHUNKS:
            del process.recent_chunks[: len(process.recent_chunks) - MAX_RECENT_CHUNKS]
        return True

    def command_display_for_process(self, process_id: str) -> Optional[str]:
        process = next((process for process in self.unified_exec_processes if process.key == process_id), None)
        return None if process is None else process.command_display

    def on_terminal_interaction(self, process_id: str, stdin: str) -> Optional[UnifiedExecInteractionCell]:
        if not self.bottom_pane_task_running:
            return None
        command_display = self.command_display_for_process(process_id)
        if stdin == "" and command_display is None:
            return None
        self.flush_answer_stream_with_separator()
        if stdin == "":
            self.ensure_status_indicator()
            self.interrupt_hint_visible = True
            self.terminal_title_status_kind = "waiting_for_background_terminal"
            self.status = "Waiting for background terminal"
            self.status_details = command_display
            if self.unified_exec_wait_streak is None:
                self.unified_exec_wait_streak = UnifiedExecWaitStreak.new(process_id, command_display)
            elif self.unified_exec_wait_streak.process_id == process_id:
                self.unified_exec_wait_streak.update_command_display(command_display)
            else:
                self.flush_unified_exec_wait_streak()
                self.unified_exec_wait_streak = UnifiedExecWaitStreak.new(process_id, command_display)
            self.request_redraw()
            return None

        if self.unified_exec_wait_streak is not None and self.unified_exec_wait_streak.process_id == process_id:
            self.flush_unified_exec_wait_streak()
        cell = UnifiedExecInteractionCell(command_display, stdin)
        self.history_cells.append(cell)
        return cell

    def on_command_execution_started(self, item: Union[CommandExecutionItem, Dict[str, Any]]) -> None:
        item = coerce_command_execution_item(item)
        command, parsed_cmd = command_execution_command_and_parsed(item.command, item.command_actions)
        self.flush_answer_stream_with_separator()
        if is_unified_exec_source(item.source):
            if normalize_source(item.source) == UNIFIED_EXEC_STARTUP_SOURCE:
                self.track_unified_exec_process_begin(item.id, item.process_id, item.command)
            if not self.bottom_pane_task_running:
                return
            self.ensure_status_indicator()
            if not parsed_cmd:
                return
        self.handle_command_execution_started_now(item)

    def on_exec_command_output_delta(self, call_id: str, delta: str) -> bool:
        self.track_unified_exec_output_chunk(call_id, delta)
        if not self.bottom_pane_task_running or self.active_exec_cell is None:
            return False
        if self.active_exec_cell.append_output(call_id, delta):
            self.bump_active_cell_revision()
            self.request_redraw()
            return True
        return False

    def on_command_execution_completed(self, item: Union[CommandExecutionItem, Dict[str, Any]]) -> None:
        item = coerce_command_execution_item(item)
        if is_unified_exec_source(item.source):
            if (
                item.process_id is not None
                and self.unified_exec_wait_streak is not None
                and self.unified_exec_wait_streak.process_id == item.process_id
            ):
                self.flush_unified_exec_wait_streak()
            self.track_unified_exec_process_end(item.id, item.process_id)
            if not self.bottom_pane_task_running:
                return
        self.handle_command_execution_completed_now(item)

    def handle_command_execution_started_now(self, item: Union[CommandExecutionItem, Dict[str, Any]]) -> None:
        item = coerce_command_execution_item(item)
        command, parsed_cmd = command_execution_command_and_parsed(item.command, item.command_actions)
        source = normalize_source(item.source)
        self.ensure_status_indicator()
        self.running_commands[item.id] = RunningCommand(command=list(command), parsed_cmd=list(parsed_cmd), source=source)

        command_display = " ".join(command)
        is_wait_interaction = source == UNIFIED_EXEC_INTERACTION_SOURCE
        should_suppress = (
            is_wait_interaction
            and self.last_unified_wait is not None
            and self.last_unified_wait.is_duplicate(command_display)
        )
        if is_wait_interaction:
            self.last_unified_wait = UnifiedExecWaitState.new(command_display)
        else:
            self.last_unified_wait = None
        if should_suppress:
            self.suppressed_exec_calls.add(item.id)
            return

        if self.active_exec_cell is not None and self.active_exec_cell.with_added_call(item.id, command, parsed_cmd, source):
            self.bump_active_cell_revision()
        else:
            self.flush_active_cell()
            self.active_exec_cell = SemanticExecCell.new(item.id, command, parsed_cmd, source)
            self.bump_active_cell_revision()
        self.request_redraw()

    def handle_command_execution_completed_now(self, item: Union[CommandExecutionItem, Dict[str, Any]]) -> None:
        item = coerce_command_execution_item(item)
        event_command = split_command_string(item.command)
        event_parsed = list(command_execution_command_and_parsed(item.command, item.command_actions)[1])
        duration_ms = max(0, int(item.duration_ms or 0))
        exit_code = int(item.exit_code or 0)
        aggregated_output = item.aggregated_output or ""

        running = self.running_commands.pop(item.id, None)
        if item.id in self.suppressed_exec_calls:
            self.suppressed_exec_calls.remove(item.id)
            return
        if running is None:
            command = event_command
            parsed = event_parsed
            source = normalize_source(item.source)
        else:
            command = list(running.command)
            parsed = list(running.parsed_cmd)
            source = normalize_source(running.source)

        is_unified_exec_interaction = source == UNIFIED_EXEC_INTERACTION_SOURCE
        is_user_shell = source == USER_SHELL_SOURCE
        if is_unified_exec_interaction:
            output = CommandOutput(exit_code, "", "")
        else:
            output = CommandOutput(exit_code, aggregated_output, aggregated_output)

        if self.active_exec_cell is not None and self.active_exec_cell.contains_call(item.id):
            self.active_exec_cell.complete_call(item.id, output, duration_ms)
            if self.active_exec_cell.should_flush():
                self.flush_active_cell()
            else:
                self.bump_active_cell_revision()
                self.request_redraw()
        elif self.active_exec_cell is not None and self.active_exec_cell.is_active():
            orphan = SemanticExecCell.new(item.id, command, parsed, source)
            orphan.inserted_as_orphan = True
            orphan.complete_call(item.id, output, duration_ms)
            self.history_cells.append(orphan)
            self.request_redraw()
        else:
            self.flush_active_cell()
            cell = SemanticExecCell.new(item.id, command, parsed, source)
            cell.complete_call(item.id, output, duration_ms)
            if cell.should_flush():
                self.history_cells.append(cell)
            else:
                self.active_exec_cell = cell
                self.bump_active_cell_revision()
                self.request_redraw()

        self.had_work_activity = True
        if is_user_shell:
            self.queued_input_sent = True

    def flush_active_cell(self) -> None:
        if self.active_exec_cell is not None:
            self.history_cells.append(self.active_exec_cell)
            self.active_exec_cell = None

    def ensure_status_indicator(self) -> None:
        self.status_indicator_visible = True

    def flush_answer_stream_with_separator(self) -> None:
        self.answer_stream_flushes += 1

    def bump_active_cell_revision(self) -> None:
        self.active_cell_revision += 1

    def request_redraw(self) -> None:
        self.redraw_requested = True


def command_display_from_raw(command: str) -> str:
    return strip_bash_lc_and_escape(split_command_string(command))


def command_text_from_notification(event: Any) -> str:
    """Extract command text from an ItemStarted/ItemCompleted notification."""

    payload = getattr(event, "payload", {}) or {}
    item = _payload_field(payload, "item", payload)
    command = _payload_field(item, "command", None)
    if isinstance(command, (list, tuple)):
        return " ".join(str(part) for part in command)
    return "" if command is None else str(command)


def _payload_field(payload: Any, key: str, default: Any = None) -> Any:
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def normalize_source(source: Any) -> str:
    value = getattr(source, "value", None)
    if value is not None:
        return str(value)
    return str(source)


def coerce_command_execution_item(value: Union[CommandExecutionItem, Dict[str, Any]]) -> CommandExecutionItem:
    if isinstance(value, CommandExecutionItem):
        return value
    if not isinstance(value, dict):
        raise TypeError("command execution item must be CommandExecutionItem or mapping")
    return CommandExecutionItem(
        id=str(value.get("id", "")),
        command=str(value.get("command", "")),
        source=normalize_source(value.get("source", "")),
        process_id=value.get("process_id"),
        command_actions=value.get("command_actions", ()),
        aggregated_output=value.get("aggregated_output"),
        exit_code=value.get("exit_code"),
        duration_ms=value.get("duration_ms"),
    )


__all__ = [
    "CommandExecutionItem",
    "CommandLifecycleState",
    "CommandOutput",
    "MAX_RECENT_CHUNKS",
    "RUST_MODULE",
    "SemanticExecCall",
    "SemanticExecCell",
    "UnifiedExecInteractionCell",
    "command_display_from_raw",
    "command_text_from_notification",
    "coerce_command_execution_item",
    "normalize_source",
]
