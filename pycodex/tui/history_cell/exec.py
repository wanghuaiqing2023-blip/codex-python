"""Semantic port of Rust ``codex-tui::history_cell::exec``.

Upstream source: ``codex/codex-rs/tui/src/history_cell/exec.rs``.

Rust renders these cells with ratatui ``Line``/``Span`` values.  The Python
port keeps the same transcript/state behavior using the lightweight history
cell semantic model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .._porting import RustTuiModule
from ..line_truncation import Line, Span, _display_width
from .base import CompositeHistoryCell, PlainHistoryCell, adaptive_wrap_lines, plain_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::exec",
    source="codex/codex-rs/tui/src/history_cell/exec.rs",
)


TRUNCATION_SUFFIX = " [...]"
MAX_PROCESSES = 16
MAX_COMMAND_GRAPHEMES = 80


def _line(text: str) -> Line:
    return Line.from_text(text)


def _raw_lines_from_source(source: str) -> list[Line]:
    if source == "":
        return []
    return [_line(part) for part in source.splitlines()]


def _take_prefix_by_width(text: str, budget: int) -> tuple[str, str]:
    if budget <= 0:
        return "", text

    used = 0
    split_at = 0
    for index, char in enumerate(text):
        char_width = _display_width(char)
        if used + char_width > budget:
            break
        used += char_width
        split_at = index + 1
    return text[:split_at], text[split_at:]


def _first_line_snippet(command: str) -> tuple[str, bool]:
    first_line, separator, _rest = command.partition("\n")
    has_more_lines = bool(separator)
    if len(first_line) > MAX_COMMAND_GRAPHEMES:
        return first_line[:MAX_COMMAND_GRAPHEMES], True
    return first_line, has_more_lines


def _display_truncated(prefix: str, text: str, width: int, already_truncated: bool = False) -> Line:
    prefix_width = _display_width(prefix)
    if width <= prefix_width:
        return _line(prefix)

    budget = max(0, width - prefix_width)
    suffix_width = _display_width(TRUNCATION_SUFFIX)
    head, remainder = _take_prefix_by_width(text, budget)
    needs_suffix = already_truncated or bool(remainder)

    if needs_suffix and budget > suffix_width:
        available = max(0, budget - suffix_width)
        head, _ = _take_prefix_by_width(text, available)
        return _line(f"{prefix}{head}{TRUNCATION_SUFFIX}")

    return _line(f"{prefix}{head}")


@dataclass
class UnifiedExecInteractionCell:
    """Background terminal wait/input transcript cell."""

    command_display: str | None = None
    stdin: str = ""

    @classmethod
    def new(cls, command_display: str | None, stdin: str) -> "UnifiedExecInteractionCell":
        return cls(command_display=command_display, stdin=stdin)

    def _non_empty_command(self) -> str | None:
        if self.command_display:
            return self.command_display
        return None

    def display_lines(self, width: int) -> list[Line]:
        if width == 0:
            return []

        waited_only = self.stdin == ""
        if waited_only:
            header = "• Waited for background terminal"
        else:
            header = "→ Interacted with background terminal"

        command = self._non_empty_command()
        if command is not None:
            header = f"{header} · {command}"

        out = adaptive_wrap_lines([_line(header)], max(1, int(width)))
        if waited_only:
            return out

        input_lines = self.stdin.splitlines()
        if input_lines:
            out.extend(adaptive_wrap_lines([_line(input_lines[0])], max(1, int(width)), _line("  └ "), _line("    ")))
            if len(input_lines) > 1:
                out.extend(adaptive_wrap_lines([_line(part) for part in input_lines[1:]], max(1, int(width)), _line("    "), _line("    ")))
        return out

    def raw_lines(self) -> list[Line]:
        command = self._non_empty_command()
        if self.stdin == "":
            if command is not None:
                return [_line(f"Waited for background terminal: {command}")]
            return [_line("Waited for background terminal")]

        if command is not None:
            out = [_line(f"Interacted with background terminal: {command}")]
        else:
            out = [_line("Interacted with background terminal")]
        out.extend(_raw_lines_from_source(self.stdin))
        return out

    def display_hyperlink_lines(self, width: int):
        from ..terminal_hyperlinks import plain_hyperlink_lines

        return plain_hyperlink_lines(self.display_lines(width))

    def transcript_hyperlink_lines(self, width: int):
        return self.display_hyperlink_lines(width)


def new_unified_exec_interaction(command_display: str | None, stdin: str) -> UnifiedExecInteractionCell:
    return UnifiedExecInteractionCell.new(command_display, stdin)


@dataclass
class UnifiedExecProcessDetails:
    """Details for one background terminal in the ``/ps`` summary."""

    command_display: str
    recent_chunks: list[str] = field(default_factory=list)


@dataclass
class UnifiedExecProcessesCell:
    """Background terminal process summary cell."""

    processes: list[UnifiedExecProcessDetails] = field(default_factory=list)

    @classmethod
    def new(cls, processes: list[UnifiedExecProcessDetails]) -> "UnifiedExecProcessesCell":
        return cls(processes=list(processes))

    def display_lines(self, width: int) -> list[Line]:
        if width == 0:
            return []

        wrap_width = max(1, int(width))
        out = [_line("Background terminals"), _line("")]

        if not self.processes:
            out.append(_line("  • No background terminals running."))
            return out

        prefix = "  • "
        shown = 0
        for process in self.processes:
            if shown >= MAX_PROCESSES:
                break

            snippet, truncated = _first_line_snippet(process.command_display)
            out.append(_display_truncated(prefix, snippet, wrap_width, truncated))

            for index, chunk in enumerate(process.recent_chunks):
                chunk_prefix = "    → " if index == 0 else "      "
                out.append(_display_truncated(chunk_prefix, chunk, wrap_width))

            shown += 1

        remaining = max(0, len(self.processes) - shown)
        if remaining > 0:
            out.append(_display_truncated(prefix, f"... and {remaining} more running", wrap_width))

        return out

    def raw_lines(self) -> list[Line]:
        return plain_lines(self.display_lines(65535))

    def desired_height(self, width: int) -> int:
        return len(self.display_lines(width))

    def display_hyperlink_lines(self, width: int):
        from ..terminal_hyperlinks import plain_hyperlink_lines

        return plain_hyperlink_lines(self.display_lines(width))

    def transcript_hyperlink_lines(self, width: int):
        return self.display_hyperlink_lines(width)


def new_unified_exec_processes_output(
    processes: list[UnifiedExecProcessDetails],
) -> CompositeHistoryCell:
    command = PlainHistoryCell.new([Line.from_spans([Span("/ps", "magenta")])])
    summary = UnifiedExecProcessesCell.new(processes)
    return CompositeHistoryCell.new([command, summary])


def display_lines(cell: UnifiedExecInteractionCell | UnifiedExecProcessesCell, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: UnifiedExecInteractionCell | UnifiedExecProcessesCell) -> list[Line]:
    return cell.raw_lines()


def desired_height(cell: UnifiedExecProcessesCell, width: int) -> int:
    return cell.desired_height(width)


__all__ = [
    "MAX_COMMAND_GRAPHEMES",
    "MAX_PROCESSES",
    "RUST_MODULE",
    "TRUNCATION_SUFFIX",
    "UnifiedExecInteractionCell",
    "UnifiedExecProcessDetails",
    "UnifiedExecProcessesCell",
    "desired_height",
    "display_lines",
    "new_unified_exec_interaction",
    "new_unified_exec_processes_output",
    "raw_lines",
]
