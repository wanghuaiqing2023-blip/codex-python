"""Semantic slice for Rust ``codex-tui::exec_cell::render``."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from .model import CommandOutput, ExecCall, ExecCell, UNIFIED_EXEC_INTERACTION, USER_SHELL

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="exec_cell::render",
    source="codex/codex-rs/tui/src/exec_cell/render.rs",
    status="complete",
)

TOOL_CALL_MAX_LINES = 5
USER_SHELL_TOOL_CALL_MAX_LINES = 50
MAX_INTERACTION_PREVIEW_CHARS = 80
TRANSCRIPT_HINT = "ctrl + t to view transcript"
DIM_STYLE = {"dim": True}
BOLD_STYLE = {"bold": True}
GREEN_BOLD_STYLE = {"fg": "green", "bold": True}
RED_BOLD_STYLE = {"fg": "red", "bold": True}
MAGENTA_STYLE = {"fg": "magenta"}
CYAN_STYLE = {"fg": "cyan"}


@dataclass(frozen=True)
class OutputLinesParams:
    line_limit: int
    only_err: bool = False
    include_angle_pipe: bool = False
    include_prefix: bool = True


@dataclass(frozen=True)
class OutputLines:
    lines: tuple[Line, ...]
    omitted: Optional[int] = None


@dataclass(frozen=True)
class PrefixedBlock:
    initial_prefix: str
    subsequent_prefix: str

    def wrap_width(self, total_width: int) -> int:
        return max(int(total_width) - max(len(self.initial_prefix), len(self.subsequent_prefix)), 1)


@dataclass(frozen=True)
class ExecDisplayLayout:
    command_continuation: PrefixedBlock
    command_continuation_max_lines: int
    output_block: PrefixedBlock
    output_max_lines: int


EXEC_DISPLAY_LAYOUT = ExecDisplayLayout(
    command_continuation=PrefixedBlock("  ┃", "  ┃"),
    command_continuation_max_lines=2,
    output_block=PrefixedBlock("  ┃", "    "),
    output_max_lines=5,
)


def new_active_exec_command(
    call_id: str,
    command: Iterable[str],
    parsed: Iterable[Any],
    source: Any,
    interaction_input: Optional[str],
    animations_enabled: bool,
) -> ExecCell:
    return ExecCell.new(
        ExecCall(
            call_id=str(call_id),
            command=[str(part) for part in command],
            parsed=list(parsed),
            output=None,
            source=source,
            start_time=0.0,
            duration=None,
            interaction_input=interaction_input,
        ),
        animations_enabled,
    )


def format_unified_exec_interaction(command: Iterable[str], input: Optional[str] = None) -> str:
    command_list = [str(part) for part in command]
    command_display = _strip_bash_lc(command_list)
    if input:
        return f"Interacted with `{command_display}`, sent `{summarize_interaction_input(input)}`"
    return f"Waited for `{command_display}`"


def summarize_interaction_input(input: str) -> str:
    sanitized = str(input).replace("\n", "\\n").replace("`", "\\`")
    if len(sanitized) <= MAX_INTERACTION_PREVIEW_CHARS:
        return sanitized
    return sanitized[:MAX_INTERACTION_PREVIEW_CHARS] + "..."


def output_lines(output: CommandOutput | None, params: OutputLinesParams) -> OutputLines:
    if output is None:
        return OutputLines(())
    if params.only_err and output.exit_code == 0:
        return OutputLines(())

    raw_lines = output.aggregated_output.splitlines()
    total = len(raw_lines)
    line_limit = max(int(params.line_limit), 0)
    out: list[Line] = []

    head_end = min(total, line_limit)
    for index, raw in enumerate(raw_lines[:head_end]):
        prefix = ""
        if params.include_prefix:
            prefix = "  ┃" if index == 0 and params.include_angle_pipe else "    "
        out.append(_dim_line(prefix + raw))

    show_ellipsis = total > 2 * line_limit
    omitted = total - 2 * line_limit if show_ellipsis else None
    if show_ellipsis:
        out.append(ExecCellRenderMixin.output_ellipsis_line(omitted or 0))

    tail_start = total - line_limit if show_ellipsis else head_end
    for raw in raw_lines[tail_start:]:
        prefix = "    " if params.include_prefix else ""
        out.append(_dim_line(prefix + raw))

    return OutputLines(tuple(out), omitted)


def activity_marker(_start_time: Optional[float], animations_enabled: bool) -> Span:
    return Span("•" if not animations_enabled else "◐", DIM_STYLE)


class ExecCellRenderMixin:
    @staticmethod
    def output_ellipsis_text(omitted: int) -> str:
        return f"...+{omitted} lines ({TRANSCRIPT_HINT})"

    @staticmethod
    def output_ellipsis_line(omitted: int) -> Line:
        return _dim_line(ExecCellRenderMixin.output_ellipsis_text(omitted))

    @staticmethod
    def ellipsis_line(omitted: int) -> Line:
        return _dim_line(f"...+{omitted} lines")

    @staticmethod
    def output_ellipsis_line_with_prefix(omitted: int, prefix: Optional[Line] = None) -> Line:
        spans = list(prefix.spans) if prefix is not None else []
        spans.append(Span(ExecCellRenderMixin.output_ellipsis_text(omitted), DIM_STYLE))
        return Line.from_spans(spans)

    @staticmethod
    def output_ellipsis_row_count(omitted: int, width: int, prefix: Optional[Line] = None) -> int:
        return _screen_rows(ExecCellRenderMixin.output_ellipsis_line_with_prefix(omitted, prefix), width)

    @staticmethod
    def limit_lines_from_start(lines: Iterable[Line], keep: int) -> list[Line]:
        source = list(lines)
        keep = int(keep)
        if len(source) <= keep:
            return source
        if keep == 0:
            return [ExecCellRenderMixin.ellipsis_line(len(source))]
        return [*source[:keep], ExecCellRenderMixin.ellipsis_line(len(source) - keep)]

    @staticmethod
    def truncate_lines_middle(
        lines: Iterable[Line],
        max_rows: int,
        width: int,
        omitted_hint: Optional[int] = None,
        ellipsis_prefix: Optional[Line] = None,
    ) -> list[Line]:
        source = list(lines)
        max_rows = int(max_rows)
        width = max(int(width), 1)
        if max_rows == 0:
            return []
        line_rows = [_screen_rows(line, width) for line in source]
        if sum(line_rows) <= max_rows:
            return source

        estimated_omitted = (omitted_hint or 0) + len(source) - (1 if omitted_hint is not None else 0)
        ellipsis_rows = ExecCellRenderMixin.output_ellipsis_row_count(estimated_omitted, width, ellipsis_prefix)
        if ellipsis_rows >= max_rows:
            return [ExecCellRenderMixin.output_ellipsis_line_with_prefix(estimated_omitted, ellipsis_prefix)]

        available_rows = max_rows - ellipsis_rows
        head_budget = available_rows // 2
        tail_budget = available_rows - head_budget
        head: list[Line] = []
        used = 0
        head_end = 0
        while head_end < len(source) and used + line_rows[head_end] <= head_budget:
            used += line_rows[head_end]
            head.append(source[head_end])
            head_end += 1

        tail_reversed: list[Line] = []
        used = 0
        tail_start = len(source)
        while tail_start > head_end and used + line_rows[tail_start - 1] <= tail_budget:
            tail_start -= 1
            used += line_rows[tail_start]
            tail_reversed.append(source[tail_start])

        additional = len(source) - len(head) - len(tail_reversed) - (1 if omitted_hint is not None else 0)
        return [
            *head,
            ExecCellRenderMixin.output_ellipsis_line_with_prefix((omitted_hint or 0) + max(additional, 0), ellipsis_prefix),
            *reversed(tail_reversed),
        ]


def display_lines(cell: ExecCell, width: int) -> tuple[Line, ...]:
    return tuple(exploring_display_lines(cell, width) if cell.is_exploring_cell() else command_display_lines(cell, width))


def transcript_lines(cell: ExecCell, width: int) -> tuple[Line, ...]:
    lines: list[Line] = []
    for index, call in enumerate(cell.iter_calls()):
        if index > 0:
            lines.append(Line(()))
        lines.append(Line.from_spans([Span("$ ", MAGENTA_STYLE), Span(_strip_bash_lc(call.command))]))
        if call.output is not None:
            if not call.is_unified_exec_interaction():
                for raw in call.output.formatted_output.splitlines():
                    lines.extend(_wrap_line_text(raw, width))
            duration = "unknown" if call.duration is None else _format_duration(call.duration)
            result = "✓" if call.output.exit_code == 0 else f"✗ ({call.output.exit_code})"
            style = GREEN_BOLD_STYLE if call.output.exit_code == 0 else RED_BOLD_STYLE
            lines.append(Line.from_spans([Span(result, style), Span(f" – {duration}", DIM_STYLE)]))
    return tuple(lines)


def raw_lines(cell: ExecCell) -> tuple[Line, ...]:
    return tuple(Line.from_text(render_line_text(line)) for line in transcript_lines(cell, 2**16 - 1))


def exploring_display_lines(cell: ExecCell, width: int) -> list[Line]:
    title = "Exploring" if cell.is_active() else "Explored"
    lines = [Line.from_spans([activity_marker(cell.active_start_time(), cell.animations_enabled()), Span(" "), Span(title, BOLD_STYLE)])]
    for title, text in _exploring_rows(cell):
        for index, wrapped in enumerate(_wrap_preserving_long_tokens(text, max(width - len(title) - 1, 1))):
            if index == 0:
                line = Line.from_spans([Span(title, CYAN_STYLE), Span(" "), Span(wrapped)])
            else:
                line = Line.from_spans([Span(" " * (len(title) + 1)), Span(wrapped)])
            lines.append(Line.from_spans([Span("  ┃", DIM_STYLE), *line.spans]))
    return lines


def command_display_lines(cell: ExecCell, width: int) -> list[Line]:
    if len(cell.calls) != 1:
        raise ValueError("Expected exactly one call in a command display cell")
    call = cell.calls[0]
    success = None if call.output is None else call.output.exit_code == 0
    bullet = (
        Span("•", GREEN_BOLD_STYLE)
        if success is True
        else Span("•", RED_BOLD_STYLE)
        if success is False
        else activity_marker(call.start_time, cell.animations_enabled())
    )
    is_interaction = call.is_unified_exec_interaction()
    title = "" if is_interaction else "Running" if cell.is_active() else "You ran" if call.is_user_shell_command() else "Ran"
    command_text = format_unified_exec_interaction(call.command, call.interaction_input) if is_interaction else _strip_bash_lc(call.command)
    prefix = "" if is_interaction else f"{title} "
    header_spans = [bullet, Span(" "), Span(prefix, BOLD_STYLE)]
    header_width = sum(len(span.content) for span in header_spans)
    command_lines = command_text.splitlines() or [""]
    first_wrapped = _wrap_preserving_long_tokens(command_lines[0], max(width - header_width, 1))
    lines = [Line.from_spans([*header_spans, Span(first_wrapped[0])])]

    continuation: list[Line] = [Line.from_text(part) for part in first_wrapped[1:]]
    continuation_width = EXEC_DISPLAY_LAYOUT.command_continuation.wrap_width(width)
    for raw_line in command_lines[1:]:
        continuation.extend(Line.from_text(part) for part in _wrap_preserving_long_tokens(raw_line, continuation_width))
    continuation = ExecCellRenderMixin.limit_lines_from_start(
        continuation,
        EXEC_DISPLAY_LAYOUT.command_continuation_max_lines,
    )
    lines.extend(
        _prefix_lines(
            continuation,
            EXEC_DISPLAY_LAYOUT.command_continuation.initial_prefix,
            EXEC_DISPLAY_LAYOUT.command_continuation.subsequent_prefix,
        )
    )

    if call.output is not None:
        line_limit = USER_SHELL_TOOL_CALL_MAX_LINES if call.is_user_shell_command() else TOOL_CALL_MAX_LINES
        raw = output_lines(call.output, OutputLinesParams(line_limit=line_limit, only_err=False, include_angle_pipe=False, include_prefix=False))
        display_limit = USER_SHELL_TOOL_CALL_MAX_LINES if call.is_user_shell_command() else EXEC_DISPLAY_LAYOUT.output_max_lines
        if not raw.lines:
            if not call.is_unified_exec_interaction():
                lines.append(Line.from_spans([Span(EXEC_DISPLAY_LAYOUT.output_block.initial_prefix, DIM_STYLE), Span("(no output)", DIM_STYLE)]))
        else:
            wrapped: list[Line] = []
            wrap_width = EXEC_DISPLAY_LAYOUT.output_block.wrap_width(width)
            for line in raw.lines:
                wrapped.extend(_wrap_line_text(render_line_text(line), wrap_width))
            prefixed = _prefix_lines(wrapped, EXEC_DISPLAY_LAYOUT.output_block.initial_prefix, EXEC_DISPLAY_LAYOUT.output_block.subsequent_prefix)
            lines.extend(ExecCellRenderMixin.truncate_lines_middle(prefixed, display_limit, width, raw.omitted, Line.from_spans([Span(EXEC_DISPLAY_LAYOUT.output_block.subsequent_prefix, DIM_STYLE)])))
    return lines


def terminal_command_status_text(command: str, *, active: bool) -> str:
    """Return the single-line terminal scrollback summary for a command cell."""

    title = "Running" if active else "Ran"
    return f"\u2022 {title} {command}"


def render_line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def desired_transcript_height(cell: ExecCell, width: int) -> int:
    return sum(_screen_rows(line, width) for line in transcript_lines(cell, width))


def _exploring_rows(cell: ExecCell) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    read_names: list[str] = []
    for call in cell.iter_calls():
        for parsed in call.parsed:
            kind = _parsed_kind(parsed)
            if kind == "Read":
                read_names.append(_parsed_value(parsed, "name") or _parsed_value(parsed, "cmd") or "")
            else:
                if read_names:
                    rows.append(("Read", ", ".join(dict.fromkeys(read_names))))
                    read_names = []
                if kind == "ListFiles":
                    rows.append(("List", _parsed_value(parsed, "path") or _parsed_value(parsed, "cmd") or ""))
                elif kind == "Search":
                    query = _parsed_value(parsed, "query")
                    path = _parsed_value(parsed, "path")
                    cmd = _parsed_value(parsed, "cmd") or ""
                    rows.append(("Search", f"{query} in {path}" if query and path else query or cmd))
                else:
                    rows.append(("Run", _parsed_value(parsed, "cmd") or ""))
    if read_names:
        rows.append(("Read", ", ".join(dict.fromkeys(read_names))))
    return rows


def _dim_line(text: str) -> Line:
    return Line.from_spans([Span(text, DIM_STYLE)])


def _prefix_lines(lines: Iterable[Line], initial: str, subsequent: str) -> list[Line]:
    out: list[Line] = []
    for index, line in enumerate(lines):
        prefix = initial if index == 0 else subsequent
        out.append(Line.from_spans([Span(prefix, DIM_STYLE), *line.spans]))
    return out


def _wrap_line_text(text: str, width: int) -> list[Line]:
    return [Line.from_text(part) for part in _wrap_preserving_long_tokens(text, max(width, 1))]


def _wrap_preserving_long_tokens(text: str, width: int) -> list[str]:
    width = max(width, 1)
    words = str(text).split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= width or len(word) > width:
            if current and len(word) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]


def _screen_rows(line: Line, width: int) -> int:
    text = render_line_text(line)
    width = max(int(width), 1)
    if text == "":
        return 1
    return max((len(text) + width - 1) // width, 1)


def _strip_bash_lc(command: Iterable[str]) -> str:
    from ..exec_command import strip_bash_lc_and_escape

    return strip_bash_lc_and_escape(command)


def _format_duration(duration: float) -> str:
    seconds = float(duration)
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.1f}s"


def _parsed_kind(parsed: Any) -> str:
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict):
        if "kind" in parsed:
            return str(parsed["kind"])
        if len(parsed) == 1:
            return str(next(iter(parsed)))
    return str(getattr(parsed, "kind", type(parsed).__name__))


def _parsed_value(parsed: Any, key: str) -> Optional[str]:
    if isinstance(parsed, dict):
        if key in parsed:
            return None if parsed[key] is None else str(parsed[key])
        if len(parsed) == 1:
            value = next(iter(parsed.values()))
            if isinstance(value, dict) and key in value:
                return None if value[key] is None else str(value[key])
    value = getattr(parsed, key, None)
    return None if value is None else str(value)


# Mirror Rust's HistoryCell impl methods on the Python ExecCell model.
ExecCell.display_lines = display_lines  # type: ignore[attr-defined]
ExecCell.transcript_lines = transcript_lines  # type: ignore[attr-defined]
ExecCell.raw_lines = raw_lines  # type: ignore[attr-defined]
ExecCell.command_display_lines = command_display_lines  # type: ignore[attr-defined]
ExecCell.exploring_display_lines = exploring_display_lines  # type: ignore[attr-defined]
ExecCell.desired_transcript_height = desired_transcript_height  # type: ignore[attr-defined]
ExecCell.output_ellipsis_text = staticmethod(ExecCellRenderMixin.output_ellipsis_text)  # type: ignore[attr-defined]
ExecCell.output_ellipsis_line = staticmethod(ExecCellRenderMixin.output_ellipsis_line)  # type: ignore[attr-defined]
ExecCell.limit_lines_from_start = staticmethod(ExecCellRenderMixin.limit_lines_from_start)  # type: ignore[attr-defined]
ExecCell.truncate_lines_middle = staticmethod(ExecCellRenderMixin.truncate_lines_middle)  # type: ignore[attr-defined]


__all__ = [
    "EXEC_DISPLAY_LAYOUT",
    "ExecDisplayLayout",
    "MAX_INTERACTION_PREVIEW_CHARS",
    "OutputLines",
    "OutputLinesParams",
    "PrefixedBlock",
    "RUST_MODULE",
    "TOOL_CALL_MAX_LINES",
    "TRANSCRIPT_HINT",
    "USER_SHELL_TOOL_CALL_MAX_LINES",
    "activity_marker",
    "command_display_lines",
    "desired_transcript_height",
    "display_lines",
    "exploring_display_lines",
    "format_unified_exec_interaction",
    "new_active_exec_command",
    "output_lines",
    "raw_lines",
    "render_line_text",
    "summarize_interaction_input",
    "terminal_command_status_text",
    "transcript_lines",
]
