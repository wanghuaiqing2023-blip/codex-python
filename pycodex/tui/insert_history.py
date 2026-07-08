"""Semantic history insertion helpers for the TUI port.

Rust counterpart: ``codex-rs/tui/src/insert_history.rs``.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum, IntFlag
from io import StringIO
from typing import Callable, Iterable, Sequence, TextIO

from .custom_terminal import display_width, move_cursor, reset_scroll_region, set_scroll_region


class HistoryLineWrapPolicy(str, Enum):
    PRE_WRAP = "pre_wrap"
    TERMINAL = "terminal"


class InsertHistoryMode(str, Enum):
    STANDARD = "standard"
    ZELLIJ_RAW = "zellij_raw"


class Modifier(IntFlag):
    REVERSED = 1 << 0
    BOLD = 1 << 1
    ITALIC = 1 << 2
    UNDERLINED = 1 << 3
    DIM = 1 << 4
    CROSSED_OUT = 1 << 5
    SLOW_BLINK = 1 << 6
    RAPID_BLINK = 1 << 7


@dataclass(frozen=True)
class Style:
    fg: str | None = None
    bg: str | None = None
    add_modifier: Modifier = Modifier(0)
    sub_modifier: Modifier = Modifier(0)

    def patch(self, other: "Style") -> "Style":
        return Style(
            fg=other.fg if other.fg is not None else self.fg,
            bg=other.bg if other.bg is not None else self.bg,
            add_modifier=(self.add_modifier | other.add_modifier) & ~other.sub_modifier,
            sub_modifier=self.sub_modifier | other.sub_modifier,
        )


@dataclass(frozen=True)
class Span:
    content: str
    style: Style = Style()


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...]
    style: Style = Style()

    @classmethod
    def from_text(cls, text: str, style: Style = Style()) -> "Line":
        return cls((Span(str(text)),), style)

    @property
    def text(self) -> str:
        return "".join(span.content for span in self.spans)

    def width(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class Hyperlink:
    start: int
    end: int
    uri: str


@dataclass(frozen=True)
class HyperlinkLine:
    line: Line
    hyperlinks: tuple[Hyperlink, ...] = ()

    @property
    def text(self) -> str:
        return self.line.text

    def width(self) -> int:
        return self.line.width()


@dataclass(frozen=True)
class SetScrollRegion:
    range: range | tuple[int, int]

    def write_ansi(self) -> str:
        start, end = _range_bounds(self.range)
        return f"\x1b[{start};{end}r"


@dataclass(frozen=True)
class ResetScrollRegion:
    def write_ansi(self) -> str:
        return "\x1b[r"


@dataclass(frozen=True)
class ModifierDiff:
    from_modifier: Modifier
    to_modifier: Modifier

    def ansi(self) -> str:
        parts: list[str] = []
        removed = self.from_modifier & ~self.to_modifier
        if removed & Modifier.REVERSED:
            parts.append("\x1b[27m")
        if removed & Modifier.BOLD:
            parts.append("\x1b[22m")
            if self.to_modifier & Modifier.DIM:
                parts.append("\x1b[2m")
        if removed & Modifier.ITALIC:
            parts.append("\x1b[23m")
        if removed & Modifier.UNDERLINED:
            parts.append("\x1b[24m")
        if removed & Modifier.DIM:
            parts.append("\x1b[22m")
        if removed & Modifier.CROSSED_OUT:
            parts.append("\x1b[29m")
        if removed & (Modifier.SLOW_BLINK | Modifier.RAPID_BLINK):
            parts.append("\x1b[25m")

        added = self.to_modifier & ~self.from_modifier
        if added & Modifier.REVERSED:
            parts.append("\x1b[7m")
        if added & Modifier.BOLD:
            parts.append("\x1b[1m")
        if added & Modifier.ITALIC:
            parts.append("\x1b[3m")
        if added & Modifier.UNDERLINED:
            parts.append("\x1b[4m")
        if added & Modifier.DIM:
            parts.append("\x1b[2m")
        if added & Modifier.CROSSED_OUT:
            parts.append("\x1b[9m")
        if added & Modifier.SLOW_BLINK:
            parts.append("\x1b[5m")
        if added & Modifier.RAPID_BLINK:
            parts.append("\x1b[6m")
        return "".join(parts)

    def queue(self, writer: TextIO) -> None:
        writer.write(self.ansi())


@dataclass
class TerminalModel:
    width: int
    height: int
    viewport_y: int = 0
    viewport_height: int = 1
    history_rows_inserted: int = 0
    output: StringIO = field(default_factory=StringIO)

    def write(self, text: str) -> int:
        self.output.write(text)
        return len(text)

    def note_history_rows_inserted(self, rows: int) -> None:
        self.history_rows_inserted += rows


def _range_bounds(value: range | tuple[int, int]) -> tuple[int, int]:
    if isinstance(value, range):
        return value.start, value.stop
    return int(value[0]), int(value[1])


def _coerce_line(value: str | Line | HyperlinkLine) -> Line:
    if isinstance(value, HyperlinkLine):
        return value.line
    if isinstance(value, Line):
        return value
    return Line.from_text(str(value))


def _coerce_hyperlink_line(value: str | Line | HyperlinkLine) -> HyperlinkLine:
    if isinstance(value, HyperlinkLine):
        return value
    return HyperlinkLine(_coerce_line(value))


def line_contains_url_like(line: Line) -> bool:
    return bool(re.search(r"(?:https?://|\b[\w.-]+\.[A-Za-z]{2,}/)", line.text))


def line_has_mixed_url_and_non_url_tokens(line: Line) -> bool:
    text = line.text.strip()
    if not line_contains_url_like(line):
        return False
    tokens = text.split()
    url_tokens = [token for token in tokens if line_contains_url_like(Line.from_text(token))]
    return bool(url_tokens and len(url_tokens) < len(tokens))


def leading_whitespace_prefix(line: str | Line | HyperlinkLine) -> Line:
    source = _coerce_line(line)
    spans: list[Span] = []
    for span in source.spans:
        match = re.match(r"\s*", span.content)
        prefix_end = match.end() if match else 0
        if prefix_end > 0:
            spans.append(Span(span.content[:prefix_end], span.style))
        if prefix_end < len(span.content):
            break
    return Line(tuple(spans), source.style)


def _wrap_text_preserving_prefix(text: str, width: int, prefix: str) -> list[str]:
    if width <= 0:
        return [text]
    if len(text) <= width:
        return [text]
    body = text[len(prefix) :] if prefix and text.startswith(prefix) else text
    words = body.split(" ")
    rows: list[str] = []
    current = prefix
    continuation_prefix = prefix
    for word in words:
        if current == prefix:
            candidate = current + word
        else:
            candidate = word if current == "" else current + " " + word
        limit = width if not rows else max(width - len(continuation_prefix), 1)
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            rows.append((continuation_prefix if rows else "") + current)
            current = word
        else:
            for start in range(0, len(word), limit):
                chunk = word[start : start + limit]
                rows.append((continuation_prefix if rows else "") + chunk)
            current = ""
    if current or not rows:
        rows.append((continuation_prefix if rows else "") + current)
    return rows


def wrap_history_line(line: HyperlinkLine, wrap_width: int, wrap_policy: HistoryLineWrapPolicy) -> list[HyperlinkLine]:
    if wrap_policy == HistoryLineWrapPolicy.TERMINAL:
        return [line]
    if line_contains_url_like(line.line) and not line_has_mixed_url_and_non_url_tokens(line.line):
        return [line]
    prefix = leading_whitespace_prefix(line).text
    rows = _wrap_text_preserving_prefix(line.text, max(wrap_width, 1), prefix)
    return [HyperlinkLine(Line.from_text(row, line.line.style), line.hyperlinks if idx == 0 else ()) for idx, row in enumerate(rows)]


def terminal_history_wrap_width(columns: int) -> int:
    """Return the real-terminal history wrap width used before scrollback insert."""

    return max(10, columns - 1)


def terminal_history_cell_lines(text: str, wrap_width: int) -> list[str]:
    """Materialize one transcript cell into terminal-display rows.

    Rust ``insert_history`` owns the pre-wrapped history lines that are inserted
    above the bottom pane.  The Python real-terminal path stores cells as plain
    text, so this helper is the text-only counterpart used before
    ``insert_terminal_history_lines`` writes the rows into scrollback.
    """

    if not text:
        return [""]
    lines: list[str] = []
    for raw_line in text.split("\n"):
        prefix, content = _split_terminal_history_prefix(raw_line)
        continuation_prefix = " " * display_width(prefix)
        lines.extend(_wrap_terminal_history_line(content, prefix, continuation_prefix, wrap_width))
    return lines


def terminal_history_cell_insert_lines(
    text: str,
    wrap_width: int,
    *,
    history_has_content: bool,
    history_ended_with_blank: bool,
) -> list[str]:
    """Materialize a finalized transcript cell with the preceding cell gap."""

    lines: list[str] = []
    if history_has_content and not history_ended_with_blank:
        lines.append("")
    lines.extend(terminal_history_cell_lines(text, wrap_width))
    return lines


@dataclass(frozen=True)
class TerminalHistoryCellInsertPlan:
    """Prepared finalized transcript cell insertion for terminal scrollback."""

    lines: tuple[str, ...]
    state: "TerminalHistoryState"


@dataclass(frozen=True)
class TerminalHistoryLinesInsertPlan:
    """Prepared terminal history row insertion and state advancement."""

    lines: tuple[str, ...]
    state: "TerminalHistoryState"


@dataclass(frozen=True)
class TerminalHistoryInlineWritePlan:
    """Prepared inline history write and state advancement."""

    text: str
    end: str
    state: "TerminalHistoryState"


@dataclass(frozen=True)
class TerminalHistoryStreamOpenPlan:
    """Prepared assistant stream opening for terminal scrollback."""

    gap_lines: tuple[str, ...]
    state: "TerminalHistoryState"


@dataclass(frozen=True)
class TerminalHistoryStreamFinishPlan:
    """Prepared assistant stream finalization state for terminal scrollback."""

    state: "TerminalHistoryState"


@dataclass(frozen=True)
class TerminalHistoryState:
    """Retained state for the terminal scrollback product path.

    Rust ``insert_history`` owns the finalized transcript insertion boundary.
    The lightweight Python terminal runner still stores the state, but the
    insert-history module owns how row writes, blank separators, and retained
    projection cells advance it.
    """

    history_has_content: bool = False
    history_ended_with_blank: bool = False
    projection_cells: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> "TerminalHistoryState":
        return cls()

    def with_projection_cell(self, text: str) -> "TerminalHistoryState":
        return TerminalHistoryState(
            history_has_content=self.history_has_content,
            history_ended_with_blank=self.history_ended_with_blank,
            projection_cells=(*self.projection_cells, str(text)),
        )

    def with_write_markers(
        self,
        *,
        history_has_content: bool,
        history_ended_with_blank: bool,
    ) -> "TerminalHistoryState":
        return TerminalHistoryState(
            history_has_content=bool(history_has_content),
            history_ended_with_blank=bool(history_ended_with_blank),
            projection_cells=self.projection_cells,
        )

    def after_write(self, text: str, end: str) -> "TerminalHistoryState":
        has_content, ended_with_blank = terminal_history_write_state_after_write(
            history_has_content=self.history_has_content,
            history_ended_with_blank=self.history_ended_with_blank,
            text=text,
            end=end,
        )
        return self.with_write_markers(
            history_has_content=has_content,
            history_ended_with_blank=ended_with_blank,
        )

    def after_insert_lines(self, lines: Sequence[str]) -> "TerminalHistoryState":
        has_content, ended_with_blank = terminal_history_write_state_after_insert_lines(
            history_has_content=self.history_has_content,
            history_ended_with_blank=self.history_ended_with_blank,
            lines=lines,
        )
        return self.with_write_markers(
            history_has_content=has_content,
            history_ended_with_blank=ended_with_blank,
        )

    def after_stream_open(self) -> "TerminalHistoryState":
        return self.with_write_markers(
            history_has_content=True,
            history_ended_with_blank=False,
        )


@dataclass
class TerminalHistoryWriter:
    """Stateful terminal history output adapter owned by insert_history.

    Rust ``insert_history`` owns the transcript insertion surface and retained
    history state.  The terminal runner supplies only environment callbacks:
    whether the live terminal surface is active, how wide it is, and where the
    history viewport ends above the bottom pane.
    """

    writer: TextIO
    state: TerminalHistoryState = field(default_factory=TerminalHistoryState.empty)
    terminal_active: Callable[[], bool] = lambda: False
    terminal_columns: Callable[[], int] = lambda: 80
    check_resize: Callable[[], None] | None = None
    history_bottom_row: Callable[[bool], int] | None = None
    clear_bottom_pane: Callable[[], None] | None = None
    render_bottom_pane: Callable[[], None] | None = None

    def wrap_width(self) -> int:
        return terminal_history_wrap_width(self.terminal_columns())

    def apply_state(self, state: TerminalHistoryState) -> None:
        self.state = state

    def write(
        self,
        text: str = "",
        *,
        end: str = "\n",
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        self.state = run_terminal_history_output_and_flush(
            self.writer,
            self.state,
            text,
            end,
            terminal_active=self.terminal_active(),
            check_resize=self.check_resize,
            history_bottom_row=lambda: self._history_bottom_row(reserve_active_bottom_pane),
            clear_bottom_pane=self.clear_bottom_pane,
            render_bottom_pane=self.render_bottom_pane,
        )

    def write_cell(
        self,
        text: str = "",
        *,
        end: str = "\n",
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        self.state = run_terminal_history_cell_output_and_flush(
            self.writer,
            self.state,
            text,
            end,
            self.wrap_width(),
            terminal_active=self.terminal_active(),
            check_resize=self.check_resize,
            history_bottom_row=lambda: self._history_bottom_row(reserve_active_bottom_pane),
            clear_bottom_pane=self.clear_bottom_pane,
            render_bottom_pane=self.render_bottom_pane,
        )

    def insert_lines(
        self,
        lines: Sequence[str],
        *,
        clear_bottom_pane: bool = True,
        reserve_active_bottom_pane: bool = False,
        render_bottom_pane: bool = True,
    ) -> None:
        self.state = run_terminal_history_lines_output_and_flush(
            self.writer,
            self.state,
            lines,
            terminal_active=self.terminal_active(),
            check_resize=self.check_resize,
            history_bottom_row=lambda: self._history_bottom_row(reserve_active_bottom_pane),
            clear_bottom_pane=self.clear_bottom_pane if clear_bottom_pane else None,
            render_bottom_pane=self.render_bottom_pane if render_bottom_pane else None,
        )

    def insert_replayed_lines(
        self,
        lines: Sequence[str],
        reserve_active_bottom_pane: bool,
    ) -> None:
        """Insert resize-replayed history rows without live-pane side effects.

        Rust ``insert_history`` owns the actual scrollback insertion sequence,
        while ``app::resize_reflow`` decides when replay happens and whether
        the active bottom-pane footprint must be reserved.  The terminal
        runtime should pass this method as a callback instead of rebuilding the
        insert-history flag combination itself.
        """

        self.insert_lines(
            lines,
            clear_bottom_pane=False,
            reserve_active_bottom_pane=reserve_active_bottom_pane,
            render_bottom_pane=False,
        )

    def open_stream(
        self,
        prefix: str,
        *,
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        self.state = run_terminal_history_stream_open_and_flush(
            self.writer,
            self.state,
            prefix,
            terminal_active=self.terminal_active(),
            check_resize=self.check_resize,
            history_bottom_row=lambda: self._history_bottom_row(reserve_active_bottom_pane),
            render_bottom_pane=self.render_bottom_pane,
        )

    def write_stream_delta(self, text: str) -> None:
        write_terminal_history_stream_delta_and_flush(self.writer, text)

    def finish_stream_projection(self, projection: str | None) -> TerminalHistoryState:
        self.state = finish_history_stream_projection_and_flush(
            self.writer,
            self.state,
            projection,
            terminal_active=self.terminal_active(),
            render_bottom_pane=self.render_bottom_pane,
        )
        return self.state

    def _history_bottom_row(self, reserve_active_bottom_pane: bool) -> int:
        if self.history_bottom_row is None:
            raise ValueError("history_bottom_row callback is required for terminal history insertion")
        return self.history_bottom_row(reserve_active_bottom_pane)


def terminal_history_cell_insert_plan(
    state: TerminalHistoryState,
    text: str,
    wrap_width: int,
) -> TerminalHistoryCellInsertPlan:
    """Prepare a finalized transcript cell and retained projection update.

    Rust ``insert_history`` owns finalized transcript insertion semantics.  The
    terminal runner performs the actual terminal writes, but it should not need
    to know how projection cells and separator rows are derived.
    """

    lines = terminal_history_cell_insert_lines(
        text,
        wrap_width,
        history_has_content=state.history_has_content,
        history_ended_with_blank=state.history_ended_with_blank,
    )
    return TerminalHistoryCellInsertPlan(
        lines=tuple(lines),
        state=state.with_projection_cell(text),
    )


def terminal_history_lines_insert_plan(
    state: TerminalHistoryState,
    lines: Sequence[str],
) -> TerminalHistoryLinesInsertPlan:
    """Prepare history rows for insertion and advance write markers.

    The terminal runner owns the actual terminal/plain writer side effects, but
    the insert-history boundary owns how emitted rows affect transcript gap and
    blank-line state.
    """

    materialized = tuple(str(line) for line in lines)
    if not materialized:
        return TerminalHistoryLinesInsertPlan(lines=(), state=state)
    return TerminalHistoryLinesInsertPlan(
        lines=materialized,
        state=state.after_insert_lines(materialized),
    )


def terminal_history_inline_write_plan(
    state: TerminalHistoryState,
    text: str,
    end: str,
) -> TerminalHistoryInlineWritePlan:
    """Prepare a non-row history write and advance write markers."""

    materialized_text = str(text)
    materialized_end = str(end)
    return TerminalHistoryInlineWritePlan(
        text=materialized_text,
        end=materialized_end,
        state=state.after_write(materialized_text, materialized_end),
    )


def write_history_inline_output_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    text: str,
    end: str,
) -> TerminalHistoryState:
    """Write non-row history output and return the advanced history state."""

    plan = terminal_history_inline_write_plan(state, text, end)
    writer.write(plan.text + plan.end)
    _flush_writer(writer)
    return plan.state


def insert_history_lines_output_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    lines: Sequence[str],
    *,
    terminal_active: bool,
    history_bottom_row: int | None = None,
    scroll_region_bottom: int | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Insert finalized history rows on the active surface and advance state."""

    plan = terminal_history_lines_insert_plan(state, lines)
    if not plan.lines:
        return plan.state
    if terminal_active:
        if history_bottom_row is None:
            raise ValueError("history_bottom_row is required for terminal history insertion")
        insert_terminal_history_lines_and_flush(
            writer,
            plan.lines,
            history_bottom_row=int(history_bottom_row),
            scroll_region_bottom=scroll_region_bottom,
            clear_bottom_pane=clear_bottom_pane,
            render_bottom_pane=render_bottom_pane,
        )
    else:
        insert_plain_history_lines_and_flush(writer, plan.lines)
    return plan.state


def run_terminal_history_lines_output_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    lines: Sequence[str],
    *,
    terminal_active: bool,
    check_resize: Callable[[], None] | None = None,
    history_bottom_row: Callable[[], int] | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Insert finalized history rows through the Rust insert_history boundary."""

    materialized = tuple(str(line) for line in lines)
    if not materialized:
        return state
    bottom = None
    if terminal_active:
        if check_resize is not None:
            check_resize()
        if history_bottom_row is None:
            raise ValueError("history_bottom_row callback is required for terminal history insertion")
        bottom = history_bottom_row()
    return insert_history_lines_output_and_flush(
        writer,
        state,
        materialized,
        terminal_active=terminal_active,
        history_bottom_row=bottom,
        scroll_region_bottom=bottom,
        clear_bottom_pane=clear_bottom_pane,
        render_bottom_pane=render_bottom_pane,
    )


def run_terminal_history_output_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    text: str = "",
    end: str = "\n",
    *,
    terminal_active: bool,
    check_resize: Callable[[], None] | None = None,
    history_bottom_row: Callable[[], int] | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Write terminal history output through the insert-history boundary.

    Newline-terminated output is finalized transcript row insertion; other
    endings are inline writes that only advance write markers.
    """

    if end == "\n":
        return run_terminal_history_lines_output_and_flush(
            writer,
            state,
            [text],
            terminal_active=terminal_active,
            check_resize=check_resize,
            history_bottom_row=history_bottom_row,
            clear_bottom_pane=clear_bottom_pane,
            render_bottom_pane=render_bottom_pane,
        )
    return write_history_inline_output_and_flush(writer, state, text, end)


def write_history_cell_output_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    text: str,
    wrap_width: int,
    *,
    terminal_active: bool,
    history_bottom_row: int | None = None,
    scroll_region_bottom: int | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Materialize and insert one finalized transcript cell on the active surface."""

    plan = terminal_history_cell_insert_plan(state, text, wrap_width)
    return insert_history_lines_output_and_flush(
        writer,
        plan.state,
        plan.lines,
        terminal_active=terminal_active,
        history_bottom_row=history_bottom_row,
        scroll_region_bottom=scroll_region_bottom,
        clear_bottom_pane=clear_bottom_pane,
        render_bottom_pane=render_bottom_pane,
    )


def run_terminal_history_cell_output_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    text: str,
    end: str,
    wrap_width: int,
    *,
    terminal_active: bool,
    check_resize: Callable[[], None] | None = None,
    history_bottom_row: Callable[[], int] | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Write one terminal history cell through the Rust insert_history boundary."""

    if end != "\n":
        return write_history_inline_output_and_flush(writer, state, text, end)
    bottom = None
    if terminal_active:
        if check_resize is not None:
            check_resize()
        if history_bottom_row is None:
            raise ValueError("history_bottom_row callback is required for terminal history cells")
        bottom = history_bottom_row()
    return write_history_cell_output_and_flush(
        writer,
        state,
        text,
        wrap_width,
        terminal_active=terminal_active,
        history_bottom_row=bottom,
        scroll_region_bottom=bottom,
        clear_bottom_pane=clear_bottom_pane,
        render_bottom_pane=render_bottom_pane,
    )


def terminal_history_stream_open_plan(
    state: TerminalHistoryState,
) -> TerminalHistoryStreamOpenPlan:
    """Prepare separator rows and state advancement for assistant streaming.

    Rust ``insert_history`` owns the boundary between finalized transcript cells
    and streaming history output.  When finalized content exists and did not
    already end in a blank row, opening a streaming assistant cell first needs a
    separator row; after the stream opens, history write markers reflect an
    active non-blank history surface.
    """

    gap_lines = ("",) if state.history_has_content and not state.history_ended_with_blank else ()
    return TerminalHistoryStreamOpenPlan(
        gap_lines=gap_lines,
        state=state.after_stream_open(),
    )


def terminal_history_stream_finish_plan(
    state: TerminalHistoryState,
    projection: str | None,
) -> TerminalHistoryStreamFinishPlan:
    """Advance retained history projection after assistant stream finalization."""

    if projection is None:
        return TerminalHistoryStreamFinishPlan(state=state)
    return TerminalHistoryStreamFinishPlan(state=state.with_projection_cell(projection))


def terminal_history_write_state_after_write(
    *,
    history_has_content: bool,
    history_ended_with_blank: bool,
    text: str,
    end: str,
) -> tuple[bool, bool]:
    """Advance terminal history insertion state after one written row."""

    if text == "" and "\n" in end:
        if history_has_content:
            return True, True
        return history_has_content, history_ended_with_blank
    if text or end:
        return True, False
    return history_has_content, history_ended_with_blank


def terminal_history_write_state_after_insert_lines(
    *,
    history_has_content: bool,
    history_ended_with_blank: bool,
    lines: Sequence[str],
) -> tuple[bool, bool]:
    """Advance terminal history insertion state after finalized rows."""

    for line in lines:
        history_has_content, history_ended_with_blank = terminal_history_write_state_after_write(
            history_has_content=history_has_content,
            history_ended_with_blank=history_ended_with_blank,
            text=str(line),
            end="\n",
        )
    return history_has_content, history_ended_with_blank


def _split_terminal_history_prefix(text: str) -> tuple[str, str]:
    for prefix in ("\u203a ", "\u2022 ", "\u25a0 "):
        if text.startswith(prefix):
            return prefix, text[len(prefix) :]
    return "", text


def _wrap_terminal_history_line(text: str, prefix: str, continuation_prefix: str, wrap_width: int) -> list[str]:
    width = max(1, wrap_width)
    if text == "":
        return [prefix.rstrip()]
    lines: list[str] = []
    current_prefix = prefix
    remaining = text
    while remaining:
        budget = max(1, width - display_width(current_prefix))
        chunk, remaining = _take_display_width(remaining, budget)
        lines.append(f"{current_prefix}{chunk}")
        current_prefix = continuation_prefix
    return lines


def _take_display_width(text: str, budget: int) -> tuple[str, str]:
    width = 0
    last_break_index: int | None = None
    last_break_width = 0
    for index, char in enumerate(text):
        char_width = _char_display_width(char)
        if width + char_width > budget:
            if last_break_index is not None and last_break_width >= max(1, budget // 2):
                return text[:last_break_index].rstrip(), text[last_break_index + 1 :].lstrip()
            return text[:index], text[index:]
        width += char_width
        if char.isspace():
            last_break_index = index
            last_break_width = width
    return text, ""


def _char_display_width(char: str) -> int:
    if char == "\t":
        return 4
    if char in {"\r", "\n"}:
        return 0
    if unicodedata.combining(char):
        return 0
    category = unicodedata.category(char)
    if category.startswith("C"):
        return 0
    if unicodedata.east_asian_width(char) in {"F", "W"}:
        return 2
    return 1


def _ansi_color(name: str | None, foreground: bool) -> str:
    if name is None or name.lower() == "reset":
        return "\x1b[39m" if foreground else "\x1b[49m"
    table = {
        "black": 30,
        "red": 31,
        "green": 32,
        "yellow": 33,
        "blue": 34,
        "magenta": 35,
        "cyan": 36,
        "white": 37,
    }
    code = table.get(name.lower(), 39 if foreground else 49)
    if not foreground and code < 40:
        code += 10
    return f"\x1b[{code}m"


def _decorate_hyperlinks(line: HyperlinkLine, text: str) -> str:
    if not line.hyperlinks:
        return text
    out = text
    for link in sorted(line.hyperlinks, key=lambda item: item.start, reverse=True):
        visible = out[link.start : link.end]
        out = out[: link.start] + f"\x1b]8;;{link.uri}\x07{visible}\x1b]8;;\x07" + out[link.end :]
    return out


def write_spans(writer: TextIO, content: Iterable[Span]) -> None:
    fg: str | None = "reset"
    bg: str | None = "reset"
    last_modifier = Modifier(0)
    for span in content:
        modifier = (span.style.add_modifier & ~span.style.sub_modifier)
        if modifier != last_modifier:
            ModifierDiff(last_modifier, modifier).queue(writer)
            last_modifier = modifier
        next_fg = span.style.fg or "reset"
        next_bg = span.style.bg or "reset"
        if next_fg != fg:
            writer.write(_ansi_color(next_fg, True))
            fg = next_fg
        if next_bg != bg:
            writer.write(_ansi_color(next_bg, False))
            bg = next_bg
        writer.write(span.content)
    writer.write("\x1b[39m\x1b[49m\x1b[0m")


def write_history_line(writer: TextIO, line: HyperlinkLine | Line | str, wrap_width: int) -> None:
    hline = _coerce_hyperlink_line(line)
    physical_rows = math.ceil(max(hline.width(), 1) / max(wrap_width, 1))
    if physical_rows > 1:
        writer.write("\x1b[s")
        for _ in range(1, physical_rows):
            writer.write("\x1b[B\x1b[1G\x1b[K")
        writer.write("\x1b[u")
    writer.write(_ansi_color(hline.line.style.fg, True))
    writer.write(_ansi_color(hline.line.style.bg, False))
    writer.write("\x1b[K")
    merged = [Span(span.content, span.style.patch(hline.line.style)) for span in hline.line.spans]
    if hline.hyperlinks:
        plain = "".join(span.content for span in merged)
        writer.write(_decorate_hyperlinks(hline, plain))
        writer.write("\x1b[39m\x1b[49m\x1b[0m")
    else:
        write_spans(writer, merged)


def insert_history_hyperlink_lines_with_mode_and_wrap_policy(
    terminal: TerminalModel,
    lines: Sequence[HyperlinkLine | Line | str],
    mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    wrap_policy: HistoryLineWrapPolicy = HistoryLineWrapPolicy.PRE_WRAP,
) -> list[HyperlinkLine]:
    wrap_width = max(terminal.width, 1)
    wrapped: list[HyperlinkLine] = []
    wrapped_rows = 0
    for raw_line in lines:
        hline = _coerce_hyperlink_line(raw_line)
        line_wrapped = wrap_history_line(hline, wrap_width, wrap_policy)
        wrapped_rows += sum(math.ceil(max(item.width(), 1) / wrap_width) for item in line_wrapped)
        wrapped.extend(line_wrapped)

    if mode == InsertHistoryMode.ZELLIJ_RAW:
        terminal.write(f"\x1b[{max(terminal.viewport_y + 1, 1)};1H\x1b[J")
    else:
        terminal.write(SetScrollRegion(range(1, max(terminal.viewport_y, 1))).write_ansi())
    for line in wrapped:
        terminal.write("\r\n")
        write_history_line(terminal.output, line, wrap_width)
    terminal.write(ResetScrollRegion().write_ansi())
    if wrapped_rows > 0:
        terminal.note_history_rows_inserted(wrapped_rows)
    return wrapped


def insert_history_lines_with_mode_and_wrap_policy(
    terminal: TerminalModel,
    lines: Sequence[Line | str],
    mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    wrap_policy: HistoryLineWrapPolicy = HistoryLineWrapPolicy.PRE_WRAP,
) -> list[HyperlinkLine]:
    return insert_history_hyperlink_lines_with_mode_and_wrap_policy(terminal, list(lines), mode, wrap_policy)


def insert_history_lines_with_wrap_policy(
    terminal: TerminalModel,
    lines: Sequence[Line | str],
    wrap_policy: HistoryLineWrapPolicy = HistoryLineWrapPolicy.PRE_WRAP,
) -> list[HyperlinkLine]:
    return insert_history_lines_with_mode_and_wrap_policy(terminal, lines, InsertHistoryMode.STANDARD, wrap_policy)


def insert_history_lines(terminal: TerminalModel, lines: Sequence[Line | str]) -> list[HyperlinkLine]:
    return insert_history_lines_with_wrap_policy(terminal, lines, HistoryLineWrapPolicy.PRE_WRAP)


def insert_terminal_history_lines(
    writer: TextIO,
    lines: Sequence[str],
    *,
    history_bottom_row: int,
    scroll_region_bottom: int | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> None:
    """Insert finalized transcript rows into ordinary terminal scrollback.

    This is the real-terminal companion to the structured ``TerminalModel``
    helpers above.  It mirrors Rust ``insert_history`` at the terminal surface:
    constrain the scroll region above the live bottom pane, move to the bottom
    of that region, emit CRLF, write each prepared line, then reset the region.
    """

    if not lines:
        return
    if clear_bottom_pane is not None:
        clear_bottom_pane()
    region_bottom = history_bottom_row if scroll_region_bottom is None else scroll_region_bottom
    prepare_terminal_history_insert(
        writer,
        history_bottom_row=history_bottom_row,
        scroll_region_bottom=region_bottom,
    )
    for line in lines:
        writer.write("\r\n")
        writer.write(line)
    reset_scroll_region(writer)
    if render_bottom_pane is not None:
        render_bottom_pane()


def insert_terminal_history_lines_and_flush(
    writer: TextIO,
    lines: Sequence[str],
    *,
    history_bottom_row: int,
    scroll_region_bottom: int | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> None:
    """Insert finalized terminal history rows and flush the terminal writer."""

    insert_terminal_history_lines(
        writer,
        lines,
        history_bottom_row=history_bottom_row,
        scroll_region_bottom=scroll_region_bottom,
        clear_bottom_pane=clear_bottom_pane,
        render_bottom_pane=render_bottom_pane,
    )
    _flush_writer(writer)


def insert_plain_history_lines_and_flush(writer: TextIO, lines: Sequence[str]) -> None:
    """Write finalized history rows for non-TTY output and flush the writer."""

    for line in lines:
        writer.write(str(line) + "\n")
    _flush_writer(writer)


def open_terminal_history_stream_and_flush(
    writer: TextIO,
    prefix: str,
    *,
    history_bottom_row: int,
    scroll_region_bottom: int | None = None,
) -> None:
    """Open a streaming history cell in the real-terminal history surface."""

    prepare_terminal_history_insert(
        writer,
        history_bottom_row=history_bottom_row,
        scroll_region_bottom=scroll_region_bottom,
    )
    writer.write("\r\n")
    writer.write(prefix)
    _flush_writer(writer)


def open_plain_history_stream_and_flush(writer: TextIO, prefix: str) -> None:
    """Open a streaming history cell for non-TTY output and flush the writer."""

    writer.write(prefix)
    _flush_writer(writer)


def open_history_stream_output_and_flush(
    writer: TextIO,
    prefix: str,
    *,
    gap_lines: Sequence[str] = (),
    terminal_active: bool,
    history_bottom_row: int | None = None,
    scroll_region_bottom: int | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> None:
    """Open streaming history output on the active terminal/plain surface.

    Rust ``insert_history`` owns the terminal scrollback insertion surface.
    The terminal runner supplies the current viewport row and bottom-pane
    repaint effect, while this boundary owns the output sequence for optional
    separator rows followed by the streaming cell prefix.
    """

    if terminal_active and history_bottom_row is None:
        raise ValueError("history_bottom_row is required for terminal streaming history output")
    if gap_lines:
        if terminal_active:
            insert_terminal_history_lines_and_flush(
                writer,
                gap_lines,
                history_bottom_row=int(history_bottom_row),
                scroll_region_bottom=scroll_region_bottom,
                render_bottom_pane=render_bottom_pane,
            )
        else:
            insert_plain_history_lines_and_flush(writer, gap_lines)
    if terminal_active:
        open_terminal_history_stream_and_flush(
            writer,
            prefix,
            history_bottom_row=int(history_bottom_row),
            scroll_region_bottom=scroll_region_bottom,
        )
    else:
        open_plain_history_stream_and_flush(writer, prefix)


def open_history_stream_plan_output_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    prefix: str,
    *,
    terminal_active: bool,
    history_bottom_row: int | None = None,
    scroll_region_bottom: int | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Open streaming history output and return the advanced history state."""

    plan = terminal_history_stream_open_plan(state)
    open_history_stream_output_and_flush(
        writer,
        prefix,
        gap_lines=plan.gap_lines,
        terminal_active=terminal_active,
        history_bottom_row=history_bottom_row,
        scroll_region_bottom=scroll_region_bottom,
        render_bottom_pane=render_bottom_pane if terminal_active and plan.gap_lines else None,
    )
    return plan.state


def run_terminal_history_stream_open_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    prefix: str,
    *,
    terminal_active: bool,
    check_resize: Callable[[], None] | None = None,
    history_bottom_row: Callable[[], int] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Open assistant streaming history through the Rust insert_history boundary."""

    bottom = None
    if terminal_active:
        if check_resize is not None:
            check_resize()
        if history_bottom_row is None:
            raise ValueError("history_bottom_row callback is required for terminal streaming history output")
        bottom = history_bottom_row()
    return open_history_stream_plan_output_and_flush(
        writer,
        state,
        prefix,
        terminal_active=terminal_active,
        history_bottom_row=bottom,
        scroll_region_bottom=bottom,
        render_bottom_pane=render_bottom_pane,
    )


def prepare_terminal_history_insert(
    writer: TextIO,
    *,
    history_bottom_row: int,
    scroll_region_bottom: int | None = None,
) -> None:
    """Prepare terminal scrollback insertion at the history viewport bottom."""

    region_bottom = history_bottom_row if scroll_region_bottom is None else scroll_region_bottom
    set_scroll_region(writer, 1, region_bottom)
    move_cursor(writer, history_bottom_row, 1)


def finish_terminal_history_output(
    writer: TextIO,
    *,
    render_bottom_pane: Callable[[], None] | None = None,
) -> None:
    """Reset history output terminal state after streaming transcript writes."""

    reset_scroll_region(writer)
    if render_bottom_pane is not None:
        render_bottom_pane()


def finish_plain_history_output_and_flush(writer: TextIO) -> None:
    """Finish non-TTY streaming history output with a newline and flush."""

    writer.write("\n")
    _flush_writer(writer)


def finish_history_stream_output_and_flush(
    writer: TextIO,
    *,
    terminal_active: bool,
    render_bottom_pane: Callable[[], None] | None = None,
) -> None:
    """Finish streaming history output for terminal or plain output surfaces."""

    if terminal_active:
        finish_terminal_history_output(writer, render_bottom_pane=render_bottom_pane)
    else:
        finish_plain_history_output_and_flush(writer)


def finish_history_stream_projection_and_flush(
    writer: TextIO,
    state: TerminalHistoryState,
    projection: str | None,
    *,
    terminal_active: bool,
    render_bottom_pane: Callable[[], None] | None = None,
) -> TerminalHistoryState:
    """Finish streaming output and retain the finalized assistant projection."""

    finish_history_stream_output_and_flush(
        writer,
        terminal_active=terminal_active,
        render_bottom_pane=render_bottom_pane,
    )
    return terminal_history_stream_finish_plan(state, projection).state


def write_terminal_history_stream_delta_and_flush(writer: TextIO, text: str) -> None:
    """Write one streaming history delta to the terminal and flush."""

    writer.write(str(text))
    _flush_writer(writer)


def _flush_writer(writer: TextIO) -> None:
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


def write_ansi(command: SetScrollRegion | ResetScrollRegion) -> str:
    return command.write_ansi()


def execute_winapi(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("tried to execute scroll region command using WinAPI, use ANSI instead")


def is_ansi_code_supported() -> bool:
    return True


__all__ = [
    "HistoryLineWrapPolicy",
    "Hyperlink",
    "HyperlinkLine",
    "InsertHistoryMode",
    "Line",
    "Modifier",
    "ModifierDiff",
    "ResetScrollRegion",
    "SetScrollRegion",
    "Span",
    "Style",
    "TerminalHistoryCellInsertPlan",
    "TerminalHistoryInlineWritePlan",
    "TerminalHistoryLinesInsertPlan",
    "TerminalHistoryState",
    "TerminalHistoryStreamFinishPlan",
    "TerminalHistoryStreamOpenPlan",
    "TerminalHistoryWriter",
    "TerminalModel",
    "execute_winapi",
    "finish_history_stream_output_and_flush",
    "finish_history_stream_projection_and_flush",
    "finish_plain_history_output_and_flush",
    "finish_terminal_history_output",
    "insert_history_hyperlink_lines_with_mode_and_wrap_policy",
    "insert_history_lines",
    "insert_history_lines_with_mode_and_wrap_policy",
    "insert_history_lines_with_wrap_policy",
    "insert_plain_history_lines_and_flush",
    "insert_terminal_history_lines",
    "insert_terminal_history_lines_and_flush",
    "is_ansi_code_supported",
    "leading_whitespace_prefix",
    "line_contains_url_like",
    "line_has_mixed_url_and_non_url_tokens",
    "open_history_stream_output_and_flush",
    "open_history_stream_plan_output_and_flush",
    "open_plain_history_stream_and_flush",
    "open_terminal_history_stream_and_flush",
    "prepare_terminal_history_insert",
    "run_terminal_history_cell_output_and_flush",
    "run_terminal_history_lines_output_and_flush",
    "run_terminal_history_output_and_flush",
    "run_terminal_history_stream_open_and_flush",
    "terminal_history_cell_insert_plan",
    "terminal_history_cell_insert_lines",
    "terminal_history_cell_lines",
    "terminal_history_inline_write_plan",
    "terminal_history_lines_insert_plan",
    "terminal_history_stream_finish_plan",
    "terminal_history_stream_open_plan",
    "terminal_history_wrap_width",
    "terminal_history_write_state_after_insert_lines",
    "terminal_history_write_state_after_write",
    "wrap_history_line",
    "write_ansi",
    "write_history_line",
    "write_history_cell_output_and_flush",
    "write_history_inline_output_and_flush",
    "insert_history_lines_output_and_flush",
    "write_spans",
    "write_terminal_history_stream_delta_and_flush",
]
