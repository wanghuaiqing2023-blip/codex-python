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
from .history_cell import HistoryRenderMode, display_hyperlink_lines_for_mode
from .history_cell.base import PrefixedWrappedHistoryCell
from .terminal_hyperlinks import line_text, visible_lines


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
        return display_width(self.text)


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
        return display_width(self.text)


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


def _coerce_style(value: object) -> Style:
    if isinstance(value, Style):
        return value
    if value is None:
        return Style()
    if isinstance(value, str):
        tokens = {token.lower().replace("-", "_") for token in value.split()}
        fg = next((name for name in ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white") if name in tokens), None)
        modifiers = Modifier(0)
        for token, modifier in (
            ("bold", Modifier.BOLD),
            ("dim", Modifier.DIM),
            ("italic", Modifier.ITALIC),
            ("underlined", Modifier.UNDERLINED),
            ("underline", Modifier.UNDERLINED),
            ("reversed", Modifier.REVERSED),
            ("crossed_out", Modifier.CROSSED_OUT),
            ("strikethrough", Modifier.CROSSED_OUT),
        ):
            if token in tokens:
                modifiers |= modifier
        return Style(fg=fg, add_modifier=modifiers)
    if isinstance(value, dict):
        modifiers = Modifier(0)
        for key, modifier in (
            ("bold", Modifier.BOLD),
            ("dim", Modifier.DIM),
            ("italic", Modifier.ITALIC),
            ("underlined", Modifier.UNDERLINED),
            ("underline", Modifier.UNDERLINED),
            ("reversed", Modifier.REVERSED),
            ("crossed_out", Modifier.CROSSED_OUT),
            ("strikethrough", Modifier.CROSSED_OUT),
        ):
            if value.get(key):
                modifiers |= modifier
        return Style(
            fg=_style_color_name(value.get("fg")),
            bg=_style_color_name(value.get("bg")),
            add_modifier=modifiers,
        )
    raw_add_modifier = getattr(value, "add_modifier", 0)
    modifiers = Modifier(0) if callable(raw_add_modifier) else Modifier(int(raw_add_modifier or 0))
    modifier_names = {
        str(item).lower().replace("-", "_")
        for item in (getattr(value, "modifiers", ()) or ())
    }
    for name, modifier in (
        ("bold", Modifier.BOLD),
        ("dim", Modifier.DIM),
        ("italic", Modifier.ITALIC),
        ("underlined", Modifier.UNDERLINED),
        ("underline", Modifier.UNDERLINED),
        ("reversed", Modifier.REVERSED),
        ("crossed_out", Modifier.CROSSED_OUT),
        ("strikethrough", Modifier.CROSSED_OUT),
    ):
        if name in modifier_names or bool(getattr(value, name, False)):
            modifiers |= modifier
    raw_sub_modifier = getattr(value, "sub_modifier", 0)
    return Style(
        fg=_style_color_name(getattr(value, "fg", None)),
        bg=_style_color_name(getattr(value, "bg", None)),
        add_modifier=modifiers,
        sub_modifier=Modifier(0) if callable(raw_sub_modifier) else Modifier(int(raw_sub_modifier or 0)),
    )


def _style_color_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, tuple) and value:
        if value[0] == "rgb" and len(value) >= 4:
            return f"rgb:{int(value[1])}:{int(value[2])}:{int(value[3])}"
        if value[0] == "indexed" and len(value) >= 2:
            return f"indexed:{int(value[1])}"
    kind = getattr(value, "kind", None)
    payload = getattr(value, "value", None)
    if kind == "rgb" and payload is not None:
        return f"rgb:{int(payload[0])}:{int(payload[1])}:{int(payload[2])}"
    if kind == "indexed" and payload is not None:
        return f"indexed:{int(payload)}"
    if kind == "named" and payload is not None:
        return str(payload).lower()
    text = str(getattr(value, "value", value)).strip().lower()
    return None if text in {"", "none", "reset", "default"} else text


def _coerce_line(value: object) -> Line:
    if isinstance(value, HyperlinkLine):
        return value.line
    if isinstance(value, Line):
        return value
    spans = getattr(value, "spans", None)
    if spans is None:
        return Line.from_text(str(value))
    return Line(
        tuple(
            Span(
                str(getattr(span, "content", getattr(span, "text", span))),
                _coerce_style(getattr(span, "style", None)),
            )
            for span in spans
        ),
        _coerce_style(getattr(value, "style", None)),
    )


def _coerce_hyperlink_line(value: object) -> HyperlinkLine:
    if isinstance(value, HyperlinkLine):
        return value
    line = _coerce_line(getattr(value, "line", value))
    links: list[Hyperlink] = []
    for link in getattr(value, "hyperlinks", ()) or ():
        columns = getattr(link, "columns", None)
        start = getattr(link, "start", getattr(columns, "start", None))
        end = getattr(link, "end", getattr(columns, "stop", None))
        uri = getattr(link, "uri", getattr(link, "destination", None))
        if start is not None and end is not None and uri is not None:
            links.append(Hyperlink(int(start), int(end), str(uri)))
    return HyperlinkLine(line, tuple(links))


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

    def replace_trailing_projection_cells(
        self,
        count: int,
        projection: str,
    ) -> "TerminalHistoryState":
        remove = min(max(0, int(count)), len(self.projection_cells))
        prefix = self.projection_cells[:-remove] if remove else self.projection_cells
        return TerminalHistoryState(
            history_has_content=self.history_has_content,
            history_ended_with_blank=self.history_ended_with_blank,
            projection_cells=(*prefix, str(projection)),
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
    prepare_history_insert: Callable[[int], None] | None = None
    clear_bottom_pane: Callable[[], None] | None = None
    render_bottom_pane: Callable[[], None] | None = None
    append_transcript_cell: Callable[[object], None] | None = None
    insert_mode: InsertHistoryMode = InsertHistoryMode.STANDARD
    terminal_rows: Callable[[], int] | None = None

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
        terminal_active = self.terminal_active()
        prepared = end == "\n" and self._prepare_terminal_insert(1, terminal_active=terminal_active)
        self.state = run_terminal_history_output_and_flush(
            self.writer,
            self.state,
            text,
            end,
            terminal_active=terminal_active,
            check_resize=None if prepared else self.check_resize,
            history_bottom_row=lambda: self._history_bottom_row(reserve_active_bottom_pane),
            clear_bottom_pane=self.clear_bottom_pane,
            render_bottom_pane=self.render_bottom_pane,
            insert_mode=self.insert_mode,
            terminal_rows=self.terminal_rows,
        )
        self._append_text_transcript_cell(f"{text}{end}")

    def write_cell(
        self,
        text: str = "",
        *,
        end: str = "\n",
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        terminal_active = self.terminal_active()
        row_count = len(terminal_history_cell_insert_plan(self.state, text, self.wrap_width()).lines)
        prepared = end == "\n" and self._prepare_terminal_insert(
            row_count,
            terminal_active=terminal_active,
        )
        self.state = run_terminal_history_cell_output_and_flush(
            self.writer,
            self.state,
            text,
            end,
            self.wrap_width(),
            terminal_active=terminal_active,
            check_resize=None if prepared else self.check_resize,
            history_bottom_row=lambda: self._history_bottom_row(reserve_active_bottom_pane),
            clear_bottom_pane=self.clear_bottom_pane,
            render_bottom_pane=self.render_bottom_pane,
            insert_mode=self.insert_mode,
            terminal_rows=self.terminal_rows,
        )
        self._append_text_transcript_cell(text)

    def source_cell_projection(self, cell: object) -> str:
        lines = self.source_cell_lines(cell)
        return "\n".join(line_text(line) for line in visible_lines(lines))

    def source_cell_lines(self, cell: object) -> list[object]:
        source_lines = list(
            display_hyperlink_lines_for_mode(
                cell, self.wrap_width(), HistoryRenderMode.RICH
            )
        )
        wrapped: list[HyperlinkLine] = []
        for source_line in source_lines:
            line = _coerce_hyperlink_line(source_line)
            merged = [span.style.patch(line.line.style) for span in line.line.spans]
            if (
                line.width() > self.wrap_width()
                and not line.hyperlinks
                and all(style == Style() for style in merged)
            ):
                wrapped.extend(
                    HyperlinkLine(Line.from_text(row))
                    for row in terminal_history_cell_lines(line.text, self.wrap_width())
                )
            else:
                wrapped.append(line)
        return wrapped

    def write_source_cell(
        self,
        cell: object,
        *,
        reserve_active_bottom_pane: bool = False,
        record_transcript: bool = True,
    ) -> str:
        """Insert one typed HistoryCell through Rust insert-history semantics."""

        source_lines = self.source_cell_lines(cell)
        plain_rows = [line_text(line.line) for line in source_lines]
        projection = "\n".join(plain_rows)
        if source_lines:
            bottom = None
            if self.terminal_active():
                if self.check_resize is not None:
                    self.check_resize()
                self._prepare_terminal_insert(
                    sum(
                        max(1, (line.width() + self.wrap_width() - 1) // self.wrap_width())
                        for line in source_lines
                    ),
                    terminal_active=True,
                    check_resize=False,
                )
                bottom = self._history_bottom_row(reserve_active_bottom_pane)
                insert_terminal_history_lines_and_flush(
                    self.writer,
                    source_lines,
                    history_bottom_row=bottom,
                    scroll_region_bottom=bottom,
                    clear_bottom_pane=self.clear_bottom_pane,
                    render_bottom_pane=self.render_bottom_pane,
                    wrap_width=self.wrap_width(),
                    mode=self.insert_mode,
                    terminal_rows=None if self.terminal_rows is None else self.terminal_rows(),
                )
            else:
                insert_plain_history_lines_and_flush(self.writer, plain_rows)
            self.state = self.state.after_insert_lines(plain_rows).with_projection_cell(projection)
        if record_transcript and self.append_transcript_cell is not None:
            self.append_transcript_cell(cell)
        return projection

    def replace_projection_run(self, count: int, cell: object) -> TerminalHistoryState:
        """Replace transient stream projections with one canonical source cell."""

        projection = self.source_cell_projection(cell)
        self.state = self.state.replace_trailing_projection_cells(count, projection)
        return self.state

    def insert_lines(
        self,
        lines: Sequence[str],
        *,
        clear_bottom_pane: bool = True,
        reserve_active_bottom_pane: bool = False,
        render_bottom_pane: bool = True,
    ) -> None:
        materialized = tuple(str(line) for line in lines)
        terminal_active = self.terminal_active()
        prepared = self._prepare_terminal_insert(
            len(materialized),
            terminal_active=terminal_active,
        )
        self.state = run_terminal_history_lines_output_and_flush(
            self.writer,
            self.state,
            materialized,
            terminal_active=terminal_active,
            check_resize=None if prepared else self.check_resize,
            history_bottom_row=lambda: self._history_bottom_row(reserve_active_bottom_pane),
            clear_bottom_pane=self.clear_bottom_pane if clear_bottom_pane else None,
            render_bottom_pane=self.render_bottom_pane if render_bottom_pane else None,
            insert_mode=self.insert_mode,
            terminal_rows=self.terminal_rows,
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

    def _history_bottom_row(self, reserve_active_bottom_pane: bool) -> int:
        if self.history_bottom_row is None:
            raise ValueError("history_bottom_row callback is required for terminal history insertion")
        return self.history_bottom_row(reserve_active_bottom_pane)

    def _prepare_terminal_insert(
        self,
        inserted_rows: int,
        *,
        terminal_active: bool,
        check_resize: bool = True,
    ) -> bool:
        if not terminal_active:
            return False
        if check_resize and self.check_resize is not None:
            self.check_resize()
        if self.prepare_history_insert is not None:
            self.prepare_history_insert(max(0, int(inserted_rows)))
        return True

    def _append_text_transcript_cell(self, text: str) -> None:
        if self.append_transcript_cell is None:
            return
        source_lines = str(text).splitlines()
        if not source_lines and text:
            source_lines = [str(text)]
        self.append_transcript_cell(
            PrefixedWrappedHistoryCell.new(source_lines, "", "")
        )


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
    insert_mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    terminal_rows: int | None = None,
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
            mode=insert_mode,
            terminal_rows=terminal_rows,
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
    insert_mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    terminal_rows: Callable[[], int] | None = None,
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
        insert_mode=insert_mode,
        terminal_rows=None if terminal_rows is None else terminal_rows(),
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
    insert_mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    terminal_rows: Callable[[], int] | None = None,
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
            insert_mode=insert_mode,
            terminal_rows=terminal_rows,
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
    insert_mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    terminal_rows: int | None = None,
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
        insert_mode=insert_mode,
        terminal_rows=terminal_rows,
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
    insert_mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    terminal_rows: Callable[[], int] | None = None,
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
        insert_mode=insert_mode,
        terminal_rows=None if terminal_rows is None else terminal_rows(),
    )


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
    normalized = name.lower()
    if normalized.startswith("rgb:"):
        try:
            red, green, blue = (int(part) for part in normalized.split(":")[1:4])
        except (TypeError, ValueError):
            return "\x1b[39m" if foreground else "\x1b[49m"
        channel = 38 if foreground else 48
        return f"\x1b[{channel};2;{red};{green};{blue}m"
    if normalized.startswith("indexed:"):
        try:
            index = int(normalized.split(":", 1)[1])
        except (TypeError, ValueError):
            return "\x1b[39m" if foreground else "\x1b[49m"
        channel = 38 if foreground else 48
        return f"\x1b[{channel};5;{index}m"
    table = {
        "black": 30,
        "red": 31,
        "green": 32,
        "yellow": 33,
        "blue": 34,
        "magenta": 35,
        "cyan": 36,
        "white": 37,
        "gray": 90,
        "grey": 90,
    }
    code = table.get(normalized, 39 if foreground else 49)
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
    merged = [Span(span.content, span.style.patch(hline.line.style)) for span in hline.line.spans]
    if not hline.hyperlinks and all(span.style == Style() for span in merged):
        if physical_rows > 1:
            writer.write("\x1b[K")
        writer.write("".join(span.content for span in merged))
        return
    writer.write(_ansi_color(hline.line.style.fg, True))
    writer.write(_ansi_color(hline.line.style.bg, False))
    writer.write("\x1b[K")
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
    lines: Sequence[object],
    *,
    history_bottom_row: int,
    scroll_region_bottom: int | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
    wrap_width: int = 65_535,
    mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    terminal_rows: int | None = None,
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
    if mode is InsertHistoryMode.ZELLIJ_RAW:
        # Rust insert_history::ZellijRaw is a Zellij-only fallback because
        # Zellij does not preserve terminal soft-wrap continuation inside a
        # scroll region. Other terminal backends use the Standard branch.
        reset_scroll_region(writer)
        screen_bottom = max(int(terminal_rows or history_bottom_row), int(history_bottom_row))
        viewport_top = min(screen_bottom, max(1, int(history_bottom_row) + 1))
        move_cursor(writer, viewport_top, 1)
        for index, line in enumerate(lines):
            if index:
                writer.write("\r\n")
            if isinstance(line, str):
                writer.write(line)
            else:
                write_history_line(writer, _coerce_hyperlink_line(line), wrap_width)
        for _ in range(max(0, screen_bottom - int(history_bottom_row))):
            writer.write("\r\n\x1b[2K")
        reset_scroll_region(writer)
        if render_bottom_pane is not None:
            render_bottom_pane()
        return
    region_bottom = history_bottom_row if scroll_region_bottom is None else scroll_region_bottom
    prepare_terminal_history_insert(
        writer,
        history_bottom_row=history_bottom_row,
        scroll_region_bottom=region_bottom,
    )
    for line in lines:
        writer.write("\r\n")
        if isinstance(line, str):
            writer.write(line)
        else:
            write_history_line(writer, _coerce_hyperlink_line(line), wrap_width)
    reset_scroll_region(writer)
    if render_bottom_pane is not None:
        render_bottom_pane()


def insert_terminal_history_lines_and_flush(
    writer: TextIO,
    lines: Sequence[object],
    *,
    history_bottom_row: int,
    scroll_region_bottom: int | None = None,
    clear_bottom_pane: Callable[[], None] | None = None,
    render_bottom_pane: Callable[[], None] | None = None,
    wrap_width: int = 65_535,
    mode: InsertHistoryMode = InsertHistoryMode.STANDARD,
    terminal_rows: int | None = None,
) -> None:
    """Insert finalized terminal history rows and flush the terminal writer."""

    insert_terminal_history_lines(
        writer,
        lines,
        history_bottom_row=history_bottom_row,
        scroll_region_bottom=scroll_region_bottom,
        clear_bottom_pane=clear_bottom_pane,
        render_bottom_pane=render_bottom_pane,
        wrap_width=wrap_width,
        mode=mode,
        terminal_rows=terminal_rows,
    )
    _flush_writer(writer)


def insert_plain_history_lines_and_flush(writer: TextIO, lines: Sequence[str]) -> None:
    """Write finalized history rows for non-TTY output and flush the writer."""

    for line in lines:
        writer.write(str(line) + "\n")
    _flush_writer(writer)


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
    "TerminalHistoryWriter",
    "TerminalModel",
    "execute_winapi",
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
    "prepare_terminal_history_insert",
    "run_terminal_history_cell_output_and_flush",
    "run_terminal_history_lines_output_and_flush",
    "run_terminal_history_output_and_flush",
    "terminal_history_cell_insert_plan",
    "terminal_history_cell_insert_lines",
    "terminal_history_cell_lines",
    "terminal_history_inline_write_plan",
    "terminal_history_lines_insert_plan",
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
]
