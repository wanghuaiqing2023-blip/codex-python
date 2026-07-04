"""Terminal scrollback-first interactive runtime.

Rust ownership:
- ``codex-tui::tui`` keeps finalized chat history in terminal scrollback.
- ``codex-tui::insert_history`` owns history insertion semantics.
- ``codex-tui::bottom_pane`` owns the live prompt/status surface.

This runtime is intentionally small: it restores the product-critical terminal
contract that finalized transcript text is ordinary terminal output, so native
terminal scroll, selection, and copy work like the Rust TUI.  The richer Textual
runtime remains available for module-level overlay work, but it no longer has
to own the main transcript surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import queue
import sys
import threading
import time
import shutil
import unicodedata
from pathlib import Path
from typing import Any, TextIO

from .app.runtime import ActiveThreadRuntime, TuiAppRuntime
from .app_event import AppEvent
from .history_cell.session import SessionHeaderHistoryCell


@dataclass(frozen=True)
class TerminalInputEvent:
    """Small Rust-shaped terminal event for the scrollback product path."""

    kind: str
    text: str = ""


class _TerminalInputSource:
    def poll(self, timeout: float) -> TerminalInputEvent | None:
        raise NotImplementedError


class _StringTerminalInputSource(_TerminalInputSource):
    """Deterministic char event source for fake TTY tests."""

    def __init__(self, stdin: TextIO) -> None:
        self.stdin = stdin

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        char = self.stdin.read(1)
        if char == "":
            return TerminalInputEvent("eof")
        return _terminal_event_from_char(char)


class _LineTerminalInputSource(_TerminalInputSource):
    """Cooked-line adapter for Windows Terminal/IME friendly input.

    Rust receives key and resize events from crossterm in one event stream.
    Python's Windows console raw-character path is less reliable around IME
    composition and paste, so the product path keeps the terminal's native
    line editor for text while the main loop continues polling for resize.
    """

    def __init__(self, stdin: TextIO) -> None:
        self.stdin = stdin
        self._queue: queue.Queue[TerminalInputEvent] = queue.Queue()
        self._thread = threading.Thread(target=self._read_lines, daemon=True)
        self._thread.start()

    def _read_lines(self) -> None:
        while True:
            line = self.stdin.readline()
            if line == "":
                self._queue.put(TerminalInputEvent("eof"))
                return
            self._queue.put(TerminalInputEvent("line", line))

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        try:
            return self._queue.get(timeout=max(0.0, timeout))
        except queue.Empty:
            return None


class _WindowsConsoleInputSource(_TerminalInputSource):
    """Minimal Windows console adapter matching Rust TuiEvent key polling."""

    def __init__(self) -> None:
        import msvcrt

        self._msvcrt = msvcrt

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self._msvcrt.kbhit():
                char = self._msvcrt.getwch()
                if char in {"\x00", "\xe0"}:
                    if self._msvcrt.kbhit():
                        self._msvcrt.getwch()
                    return None
                return _terminal_event_from_char(char)
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))


class _SelectTerminalInputSource(_TerminalInputSource):
    """Best-effort non-Windows TTY adapter, used only outside Windows."""

    def __init__(self, stdin: TextIO) -> None:
        self.stdin = stdin

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        import select

        ready, _, _ = select.select([self.stdin], [], [], timeout)
        if not ready:
            return None
        char = self.stdin.read(1)
        if char == "":
            return TerminalInputEvent("eof")
        return _terminal_event_from_char(char)


def _terminal_event_from_char(char: str) -> TerminalInputEvent:
    if char in {"\r", "\n"}:
        return TerminalInputEvent("enter")
    if char in {"\b", "\x7f"}:
        return TerminalInputEvent("backspace")
    if char == "\x03":
        return TerminalInputEvent("interrupt")
    if char == "\x1a":
        return TerminalInputEvent("eof")
    return TerminalInputEvent("text", char)


def run_scrollback_tui(
    *,
    active_thread_runtime: ActiveThreadRuntime | TuiAppRuntime,
    stdout: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    """Run the Rust-style scrollback-first TUI product path."""

    from .textual_runtime import configure_app_runtime_thread_identity

    if isinstance(active_thread_runtime, TuiAppRuntime):
        app_runtime = active_thread_runtime
        configure_app_runtime_thread_identity(app_runtime, app_runtime.active_thread_runtime)
    else:
        app_runtime = TuiAppRuntime(active_thread_runtime=active_thread_runtime)
        configure_app_runtime_thread_identity(app_runtime, active_thread_runtime)
    runner = ScrollbackTuiRunner(app_runtime, stdout=stdout or sys.stdout, stdin=stdin or sys.stdin)
    return runner.run()


class ScrollbackTuiRunner:
    """Line-oriented live pane with ordinary terminal scrollback history."""

    # Rust codex-tui::bottom_pane::chat_composer reserves vertical padding
    # around the textarea and the footer.  Keep those rows live-only so
    # insert_history writes finalized transcript cells above them.
    _IDLE_BOTTOM_PANE_ROWS = 4
    # Rust's StatusIndicatorWidget is visually separated from the transcript,
    # composer, and footer.  The active pane uses:
    # status, blank, blank, composer, blank, footer.
    _STATUS_BOTTOM_PANE_ROWS = 6

    def __init__(self, app_runtime: TuiAppRuntime, *, stdout: TextIO, stdin: TextIO) -> None:
        self.app_runtime = app_runtime
        self.stdout = stdout
        self.stdin = stdin
        self.exit_code = 0
        self._assistant_open = False
        self._assistant_stream_column = 0
        self._assistant_stream_text = ""
        self._turn_started_at = 0.0
        self._live_status_active = False
        self._live_status_text: str | None = None
        self._turn_status_active = False
        self._turn_status_last_second: int | None = None
        self._turn_status_suppressed = False
        self._layout_active = False
        self._last_terminal_size: os.terminal_size | None = None
        self._handling_resize = False
        self._resize_reflow_pending = False
        self._history_has_content = False
        self._history_ended_with_blank = False
        self._history_projection_cells: list[str] = []
        self._composer_draft = ""
        self._terminal_input_source: _TerminalInputSource | None = None
        isatty = getattr(stdin, "isatty", None)
        self._stdin_is_terminal = bool(isatty()) if callable(isatty) else False

    def run(self) -> int:
        self._activate_layout()
        self._render_header()
        self._render_startup_notices()
        while True:
            try:
                prompt = self._read_prompt()
            except (EOFError, KeyboardInterrupt):
                self._shutdown()
                return self.exit_code
            if prompt is None:
                self._shutdown()
                return self.exit_code
            prompt = prompt.rstrip("\n")
            if not prompt.strip():
                continue
            command_result = self._handle_local_command(prompt)
            if command_result == "exit":
                self._shutdown()
                return self.exit_code
            if command_result:
                continue
            self._write_user_prompt(prompt)
            self._run_turn(prompt)

    def _read_prompt(self) -> str | None:
        if self._stdin_is_terminal and self._layout_active:
            source = self._get_terminal_input_source()
            if source is None:
                return self._read_prompt_with_blocking_line_fallback()
            self._composer_draft = ""
            self._render_bottom_pane()
            while True:
                event = source.poll(0.1)
                self._check_terminal_resize()
                if event is None:
                    continue
                if event.kind == "resize":
                    self._check_terminal_resize()
                    continue
                if event.kind == "text":
                    self._append_composer_text(event.text)
                    continue
                if event.kind == "line":
                    self._composer_draft = ""
                    self._clear_bottom_pane(check_resize=False)
                    return event.text
                if event.kind == "backspace":
                    self._backspace_composer_text()
                    continue
                if event.kind == "interrupt":
                    raise KeyboardInterrupt
                if event.kind == "eof":
                    self._composer_draft = ""
                    self._clear_bottom_pane(check_resize=False)
                    return None
                if event.kind == "enter":
                    line = self._composer_draft + "\n"
                    self._composer_draft = ""
                    self._clear_bottom_pane(check_resize=False)
                    return line
        self._write_live_footer()
        self.stdout.write("\n\u203a ")
        self.stdout.flush()
        line = self.stdin.readline()
        if line == "":
            return None
        return line

    def _read_prompt_with_blocking_line_fallback(self) -> str | None:
        self._composer_draft = ""
        self._render_bottom_pane()
        line = self.stdin.readline()
        self._check_terminal_resize()
        self._clear_bottom_pane(check_resize=False)
        if line == "":
            return None
        return line

    def _get_terminal_input_source(self) -> _TerminalInputSource | None:
        if self._terminal_input_source is None:
            self._terminal_input_source = self._make_terminal_input_source()
        return self._terminal_input_source

    def _make_terminal_input_source(self) -> _TerminalInputSource | None:
        if isinstance(self.stdin, str):
            return None
        if hasattr(self.stdin, "getvalue"):
            return _StringTerminalInputSource(self.stdin)
        if os.name == "nt":
            return _LineTerminalInputSource(self.stdin)
        try:
            self.stdin.fileno()
        except Exception:
            return None
        return _SelectTerminalInputSource(self.stdin)

    def _append_composer_text(self, text: str) -> None:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized:
            return
        self._composer_draft += normalized
        self._render_bottom_pane()

    def _backspace_composer_text(self) -> None:
        if self._composer_draft:
            self._composer_draft = self._composer_draft[:-1]
        self._render_bottom_pane()

    def _write(
        self,
        text: str = "",
        *,
        end: str = "\n",
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        if end == "\n":
            self._insert_history_lines([text], reserve_active_bottom_pane=reserve_active_bottom_pane)
            return
        self.stdout.write(text + end)
        self.stdout.flush()
        self._record_history_write(text, end)

    def _record_history_write(self, text: str, end: str) -> None:
        if text == "" and "\n" in end:
            if self._history_has_content:
                self._history_ended_with_blank = True
            return
        if text or end:
            self._history_has_content = True
            self._history_ended_with_blank = False

    def _write_cell_gap(
        self,
        *,
        clear_bottom_pane: bool = True,
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        if not self._history_has_content or self._history_ended_with_blank:
            return
        self._insert_history_lines(
            [""],
            clear_bottom_pane=clear_bottom_pane,
            reserve_active_bottom_pane=reserve_active_bottom_pane,
        )

    def _write_history_cell(
        self,
        text: str = "",
        *,
        end: str = "\n",
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        if end == "\n":
            self._record_history_projection_cell(text)
            lines: list[str] = []
            if self._history_has_content and not self._history_ended_with_blank:
                lines.append("")
            lines.extend(self._wrapped_history_cell_lines(text))
            self._insert_history_lines(lines, reserve_active_bottom_pane=reserve_active_bottom_pane)
            return
        self._write(text, end=end, reserve_active_bottom_pane=reserve_active_bottom_pane)

    def _record_history_projection_cell(self, text: str) -> None:
        self._history_projection_cells.append(text)

    def _wrapped_history_cell_lines(self, text: str) -> list[str]:
        if not text:
            return [""]
        lines: list[str] = []
        for raw_line in text.split("\n"):
            prefix, content = self._split_history_prefix(raw_line)
            continuation_prefix = " " * self._display_width(prefix)
            lines.extend(self._wrap_line_with_prefix(content, prefix, continuation_prefix))
        return lines

    def _split_history_prefix(self, text: str) -> tuple[str, str]:
        for prefix in ("\u203a ", "\u2022 ", "\u25a0 "):
            if text.startswith(prefix):
                return prefix, text[len(prefix) :]
        return "", text

    def _wrap_line_with_prefix(self, text: str, prefix: str, continuation_prefix: str) -> list[str]:
        width = self._history_wrap_width()
        if text == "":
            return [prefix.rstrip()]
        lines: list[str] = []
        current_prefix = prefix
        remaining = text
        while remaining:
            budget = max(1, width - self._display_width(current_prefix))
            chunk, remaining = self._take_display_width(remaining, budget)
            lines.append(f"{current_prefix}{chunk}")
            current_prefix = continuation_prefix
        return lines

    def _take_display_width(self, text: str, budget: int) -> tuple[str, str]:
        width = 0
        last_break_index: int | None = None
        last_break_width = 0
        for index, char in enumerate(text):
            char_width = self._char_display_width(char)
            if width + char_width > budget:
                if last_break_index is not None and last_break_width >= max(1, budget // 2):
                    return text[:last_break_index].rstrip(), text[last_break_index + 1 :].lstrip()
                return text[:index], text[index:]
            width += char_width
            if char.isspace():
                last_break_index = index
                last_break_width = width
        return text, ""

    def _history_wrap_width(self) -> int:
        return max(10, self._terminal_size().columns - 1)

    def _display_width(self, text: str) -> int:
        return sum(self._char_display_width(char) for char in text)

    @staticmethod
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

    def _write_live_status(self, header: str, details: str | None = None) -> None:
        """Render a transient status line without finalizing transcript history."""

        text = f"\u2022 {header}"
        if details:
            text = f"{text} \u2514 {details}"
        if self._stdin_is_terminal:
            if self._layout_active:
                self._check_terminal_resize()
            old_rows = self._bottom_pane_rows_for_size(self._terminal_size())
            self._live_status_active = True
            self._live_status_text = text
            self._repaint_after_bottom_pane_footprint_change(old_rows)
            self._render_bottom_pane()
            return
        self.stdout.write(f"\r\x1b[2K{text}")
        self.stdout.flush()
        self._live_status_active = True

    def _turn_elapsed_seconds(self) -> int:
        if not self._turn_started_at:
            return 0
        return max(0, int(time.monotonic() - self._turn_started_at))

    def _turn_status_header(self) -> str:
        return f"Working ({self._turn_elapsed_seconds()}s \u2022 esc to interrupt)"

    def _render_turn_status(self, *, force: bool = False) -> None:
        if self._turn_status_suppressed:
            return
        elapsed = self._turn_elapsed_seconds()
        if not force and self._turn_status_active and self._turn_status_last_second == elapsed:
            return
        self._write_live_status(self._turn_status_header())
        self._turn_status_active = True
        self._turn_status_last_second = elapsed

    def _refresh_turn_status_if_due(self) -> None:
        if not self._turn_status_active or self._turn_status_suppressed:
            return
        self._render_turn_status()

    def _clear_turn_status(self) -> None:
        self._turn_status_active = False
        self._turn_status_last_second = None
        self._turn_status_suppressed = False

    def _hide_inline_status(self, *, redraw_bottom_pane: bool = True) -> None:
        if not self._live_status_active:
            return
        if self._stdin_is_terminal:
            old_rows = self._bottom_pane_rows_for_size(self._terminal_size())
            self._live_status_active = False
            self._live_status_text = None
            self._repaint_after_bottom_pane_footprint_change(old_rows)
            if redraw_bottom_pane:
                self._render_bottom_pane()
            else:
                self.stdout.flush()
            return
        self.stdout.write("\r\x1b[2K")
        self.stdout.flush()
        self._live_status_active = False
        self._live_status_text = None

    def _repaint_after_bottom_pane_footprint_change(self, old_rows: list[int]) -> None:
        """Replay retained history when status indicator changes pane height.

        Rust's bottom_pane::ensure_status_indicator/hide_status_indicator requests
        a redraw; app::resize_reflow then re-renders source-backed history cells
        above the new bottom pane footprint.  Without this replay, clearing the
        expanded live pane can erase the previous finalized assistant cell.
        """

        if not (self._stdin_is_terminal and self._layout_active):
            return
        new_rows = self._bottom_pane_rows_for_size(self._terminal_size())
        if old_rows == new_rows:
            return
        if self._assistant_open:
            self._resize_reflow_pending = True
            return
        self._repaint_history_viewport()

    def _clear_live_status(self) -> None:
        self._hide_inline_status(redraw_bottom_pane=True)

    def _write_live_footer(self, status: str | None = None) -> None:
        if not self._stdin_is_terminal:
            return
        self._render_bottom_pane()

    def _activate_layout(self) -> None:
        if not self._stdin_is_terminal:
            return
        self._layout_active = True
        self._last_terminal_size = self._terminal_size()
        self._render_bottom_pane(check_resize=False)

    def _deactivate_layout(self) -> None:
        if not self._stdin_is_terminal:
            return
        self._layout_active = False
        self._last_terminal_size = None
        self._reset_scroll_region()

    def _terminal_size(self) -> os.terminal_size:
        return shutil.get_terminal_size((80, 24))

    def _check_terminal_resize(self) -> None:
        """Mirror Rust TuiEvent::Resize redraw for the lightweight scrollback path."""

        if not (self._stdin_is_terminal and self._layout_active):
            return
        if self._handling_resize:
            return
        current = self._terminal_size()
        previous = self._last_terminal_size
        if previous is None:
            self._last_terminal_size = current
            return
        if previous == current:
            return
        self._last_terminal_size = current
        if self._assistant_open:
            self._resize_reflow_pending = True
            return
        self._handling_resize = True
        try:
            self._reset_scroll_region()
            self._clear_terminal_for_resize_replay()
            self._replay_history_projection_into_scrollback()
            self._render_bottom_pane(check_resize=False)
        finally:
            self._handling_resize = False

    def _repaint_history_viewport(self) -> None:
        if not (self._stdin_is_terminal and self._layout_active):
            return
        bottom = self._history_bottom_row()
        if bottom < 1:
            return
        self._reset_scroll_region()
        for row in range(1, bottom + 1):
            self._clear_line_at(row)
        lines = self._reflow_history_projection_lines()
        visible_lines = lines[-bottom:]
        # Rust's resize reflow renders the retained transcript tail into the
        # viewport above the bottom pane.  Keep the visible tail anchored next
        # to the composer instead of replaying it from row 1; otherwise the
        # next streamed assistant cell appears at the bottom with a full-screen
        # gap after the user's prompt.
        start_row = max(1, bottom - len(visible_lines) + 1)
        for offset, line in enumerate(visible_lines):
            row = start_row + offset
            self._write_at(row, 1, self._truncate_display_width(line, max(1, self._terminal_size().columns - 1)))
        self.stdout.flush()

    def _reflow_history_projection_lines(self) -> list[str]:
        lines: list[str] = []
        for cell in self._history_projection_cells:
            if lines and (lines[-1] != ""):
                lines.append("")
            lines.extend(self._wrapped_history_cell_lines(cell))
        return lines

    def _clear_resize_bottom_pane(
        self,
        previous: os.terminal_size,
        current: os.terminal_size,
    ) -> None:
        rows = set(self._bottom_pane_rows_for_size(previous))
        rows.update(self._bottom_pane_rows_for_size(current))
        max_row = current.lines
        for row in sorted(rows):
            if 1 <= row <= max_row:
                self._clear_line_at(row)
        self.stdout.flush()

    def _clear_terminal_for_resize_replay(self) -> None:
        """Clear terminal scrollback and visible cells before transcript replay.

        Rust codex-tui::app::resize_reflow::clear_terminal_for_resize_replay
        calls custom_terminal::Terminal::clear_scrollback_and_visible_screen_ansi
        in the non-alt-screen product path.  The retained transcript projection
        is the source of truth, so stale terminal scrollback must be purged
        before rebuilding it from that source.
        """

        self._reset_scroll_region()
        self.stdout.write("\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H")
        self.stdout.flush()

    def _replay_history_projection_into_scrollback(self) -> None:
        """Rebuild terminal scrollback from retained source-backed cells."""

        lines = self._reflow_history_projection_lines()
        self._history_has_content = False
        self._history_ended_with_blank = False
        if not lines:
            return
        self._insert_history_lines(
            lines,
            clear_bottom_pane=False,
            reserve_active_bottom_pane=bool(self._live_status_active and self._live_status_text),
            render_bottom_pane=False,
        )

    def _bottom_pane_rows_for_size(self, size: os.terminal_size) -> list[int]:
        rows = size.lines
        if self._live_status_active and self._live_status_text:
            return [
                max(1, rows - 5),
                max(1, rows - 4),
                max(1, rows - 3),
                max(1, rows - 2),
                max(1, rows - 1),
                max(1, rows),
            ]
        return [
            max(1, rows - 3),
            max(1, rows - 2),
            max(1, rows - 1),
            max(1, rows),
        ]

    def _history_bottom_row(self, *, reserve_active_bottom_pane: bool = False) -> int:
        rows = self._terminal_size().lines
        bottom_pane_rows = self._STATUS_BOTTOM_PANE_ROWS if reserve_active_bottom_pane else self._bottom_pane_rows()
        return max(1, rows - bottom_pane_rows)

    def _bottom_pane_rows(self) -> int:
        if self._live_status_active and self._live_status_text:
            return self._STATUS_BOTTOM_PANE_ROWS
        return self._IDLE_BOTTOM_PANE_ROWS

    def _status_row(self) -> int | None:
        if not (self._live_status_active and self._live_status_text):
            return None
        rows = self._terminal_size().lines
        return max(1, rows - 5)

    def _composer_row(self) -> int:
        rows = self._terminal_size().lines
        return max(1, rows - 2)

    def _footer_row(self) -> int:
        return max(1, self._terminal_size().lines)

    def _move_cursor(self, row: int, column: int = 1) -> None:
        self.stdout.write(f"\x1b[{row};{column}H")

    def _write_at(self, row: int, column: int, text: str) -> None:
        self._move_cursor(row, column)
        self.stdout.write(text)

    def _restore_composer_cursor(self) -> None:
        columns = self._terminal_size().columns
        visible_line = self._composer_line_text()
        visible_line = self._truncate_display_width(visible_line, max(1, columns - 1))
        column = min(columns, max(3, 1 + self._display_width(visible_line)))
        self._move_cursor(self._composer_row(), column)

    def _composer_line_text(self) -> str:
        visible_draft = self._composer_draft.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
        return f"\u203a {visible_draft}"

    def _truncate_display_width(self, text: str, width: int) -> str:
        chunk, _ = self._take_display_width(text, max(1, width))
        return chunk

    def _clear_line_at(self, row: int) -> None:
        self._move_cursor(row, 1)
        self.stdout.write("\x1b[2K")

    def _set_history_scroll_region(self, *, reserve_active_bottom_pane: bool = False) -> None:
        bottom = self._history_bottom_row(reserve_active_bottom_pane=reserve_active_bottom_pane)
        self.stdout.write(f"\x1b[1;{bottom}r")

    def _reset_scroll_region(self) -> None:
        self.stdout.write("\x1b[r")

    def _clear_bottom_pane(self, *, check_resize: bool = True) -> None:
        if not (self._stdin_is_terminal and self._layout_active):
            return
        if check_resize:
            self._check_terminal_resize()
        self._reset_scroll_region()
        for row in self._bottom_pane_rows_for_size(self._terminal_size()):
            self._clear_line_at(row)
        self.stdout.flush()

    def _render_bottom_pane(self, *, check_resize: bool = True) -> None:
        if not (self._stdin_is_terminal and self._layout_active):
            return
        if check_resize:
            self._check_terminal_resize()
        self._reset_scroll_region()
        columns = self._terminal_size().columns
        for row in self._bottom_pane_rows_for_size(self._terminal_size()):
            self._clear_line_at(row)
        status_row = self._status_row()
        if status_row is not None and self._live_status_text:
            self._write_at(status_row, 1, self._live_status_text[: max(0, columns - 1)])
        composer_text = self._truncate_display_width(self._composer_line_text(), max(1, columns - 1))
        self._write_at(self._composer_row(), 1, composer_text)
        text = self._idle_footer_text()
        if text:
            self._write_at(self._footer_row(), 1, text[: max(0, columns - 1)])
        self._restore_composer_cursor()
        self.stdout.flush()

    def _insert_history_lines(
        self,
        lines: list[str],
        *,
        clear_bottom_pane: bool = True,
        reserve_active_bottom_pane: bool = False,
        render_bottom_pane: bool = True,
    ) -> None:
        """Insert finalized transcript lines using Rust insert_history semantics.

        codex-tui::insert_history constrains the scroll region above the bottom
        pane, moves the cursor to the region end, emits CRLF, then writes each
        pre-wrapped history line.  This prevents finalized transcript cells from
        being painted directly at the visual bottom of the history viewport.
        """

        if not lines:
            return
        if not (self._stdin_is_terminal and self._layout_active):
            for line in lines:
                self.stdout.write(line + "\n")
            self.stdout.flush()
            self._record_inserted_history_lines(lines)
            return
        self._check_terminal_resize()
        if clear_bottom_pane:
            self._clear_bottom_pane(check_resize=False)
        self._set_history_scroll_region(reserve_active_bottom_pane=reserve_active_bottom_pane)
        self._move_cursor(self._history_bottom_row(reserve_active_bottom_pane=reserve_active_bottom_pane), 1)
        for line in lines:
            self.stdout.write("\r\n")
            self.stdout.write(line)
        self.stdout.flush()
        self._reset_scroll_region()
        self._record_inserted_history_lines(lines)
        if render_bottom_pane:
            self._render_bottom_pane(check_resize=False)

    def _record_inserted_history_lines(self, lines: list[str]) -> None:
        for line in lines:
            self._record_history_write(line, "\n")

    def _open_assistant_stream_cell(
        self,
        prefix: str,
        *,
        reserve_active_bottom_pane: bool = False,
    ) -> None:
        if self._history_has_content and not self._history_ended_with_blank:
            self._insert_history_lines(
                [""],
                clear_bottom_pane=False,
                reserve_active_bottom_pane=reserve_active_bottom_pane,
            )
        if self._stdin_is_terminal and self._layout_active:
            self._check_terminal_resize()
            self._set_history_scroll_region(reserve_active_bottom_pane=reserve_active_bottom_pane)
            self._move_cursor(self._history_bottom_row(reserve_active_bottom_pane=reserve_active_bottom_pane), 1)
            self.stdout.write("\r\n")
            self.stdout.write(prefix)
            self.stdout.flush()
        else:
            self.stdout.write(prefix)
            self.stdout.flush()
        self._assistant_stream_column = self._display_width(prefix)
        self._assistant_stream_text = ""
        self._history_has_content = True
        self._history_ended_with_blank = False
        self._assistant_open = True

    def _finish_history_output(self) -> None:
        if not (self._stdin_is_terminal and self._layout_active):
            return
        self._reset_scroll_region()
        self._render_bottom_pane()

    def _render_header(self) -> None:
        from .textual_runtime import (
            _display_version,
            _line_text,
            _runtime_display_model,
            _runtime_header_reasoning_effort,
            _runtime_header_yolo_mode,
            _runtime_show_fast_status,
        )

        cell = SessionHeaderHistoryCell.new(
            _runtime_display_model(self.app_runtime),
            _runtime_header_reasoning_effort(self.app_runtime),
            _runtime_show_fast_status(self.app_runtime),
            self.app_runtime.cwd,
            _display_version(),
        ).with_yolo_mode(_runtime_header_yolo_mode(self.app_runtime))
        self._write_history_cell("\n".join(_line_text(line) for line in cell.display_lines(100)))

    def _render_startup_notices(self) -> None:
        from .textual_runtime import _plain_markdown_text, _runtime_startup_tooltip, _runtime_startup_warnings

        tooltip = _runtime_startup_tooltip(self.app_runtime)
        if tooltip:
            self._write_history_cell(f"\u2022 Tip: {_plain_markdown_text(tooltip)}")
        seen: set[str] = set()
        for warning in _runtime_startup_warnings(self.app_runtime):
            text = str(warning)
            if text in seen:
                continue
            seen.add(text)
            self._write_history_cell(f"\u2022 {text}")
        if seen or tooltip:
            self._write()

    def _write_footer(self, status: str | None = None) -> None:
        text = status or self._idle_footer_text()
        if text:
            self._write(text)

    def _idle_footer_text(self) -> str:
        from .textual_runtime import _runtime_cwd, _runtime_model_with_reasoning, _runtime_show_fast_status

        cwd = _runtime_cwd(self.app_runtime)
        model_part = _runtime_model_with_reasoning(self.app_runtime)
        if _runtime_show_fast_status(self.app_runtime) and " fast" not in f" {model_part.lower()} ":
            model_part = f"{model_part} fast"
        cwd_part = f"~\\{Path(cwd).name}" if cwd else ""
        return " · ".join(part for part in (model_part, cwd_part) if part)

    def _write_user_prompt(self, prompt: str) -> None:
        self._clear_live_status()
        self._write_history_cell(f"\u203a {prompt}", reserve_active_bottom_pane=True)
        if self._stdin_is_terminal and self._layout_active:
            self._render_bottom_pane()

    def _handle_local_command(self, prompt: str) -> bool | str:
        stripped = prompt.strip()
        lowered = stripped.lower()
        if lowered in {"/quit", "/exit", ":q", "q", "quit", "exit"}:
            return "exit"
        if lowered == "/clear":
            self._deactivate_layout()
            self.stdout.write("\x1b[2J\x1b[3J\x1b[H")
            self.stdout.flush()
            self._history_has_content = False
            self._history_ended_with_blank = False
            self._history_projection_cells = []
            self._assistant_stream_text = ""
            self._resize_reflow_pending = False
            self._render_header()
            self._activate_layout()
            return True
        if lowered in {"/help", "/?"}:
            self._write_history_cell("\u2022 Commands: /clear, /status, /quit")
            return True
        if lowered == "/status":
            self._render_status_card()
            return True
        return False

    def _render_status_card(self) -> None:
        from .textual_runtime import (
            _display_version,
            _runtime_agents_summary,
            _runtime_cwd,
            _runtime_display_model,
            _runtime_header_reasoning_effort,
            _runtime_permissions_label,
        )

        model = _runtime_display_model(self.app_runtime)
        effort = _runtime_header_reasoning_effort(self.app_runtime)
        model_line = f"{model} (reasoning {effort})" if effort else model
        thread_id = getattr(self.app_runtime.active_thread_runtime, "thread_id", None) or "<none>"
        self._write_history_cell(
            "\n".join(
                [
                    "• /status",
                    f"  >_ OpenAI Codex ({_display_version()})",
                    f"  Model: {model_line}",
                    f"  Directory: {_runtime_cwd(self.app_runtime)}",
                    f"  Permissions: {_runtime_permissions_label(self.app_runtime)}",
                    f"  Agents.md: {_runtime_agents_summary(self.app_runtime)}",
                    f"  Session: {thread_id}",
                    "  Limits: data not available yet",
                ]
            )
        )

    def _run_turn(self, prompt: str) -> None:
        append_history = getattr(self.app_runtime, "append_message_history_entry", None)
        if callable(append_history):
            append_history(prompt)
        self._turn_started_at = time.monotonic()
        self._assistant_open = False
        self._clear_turn_status()
        self._render_turn_status(force=True)
        try:
            event_stream = self.app_runtime.submit_user_turn(prompt)
            self._consume_events(event_stream)
        except BaseException as exc:
            self._clear_turn_status()
            self._clear_live_status()
            if self._assistant_open:
                self._finalize_assistant_stream()
            self._write_history_cell(f"\u25a0 {exc}")
            self.exit_code = 1

    def _consume_events(self, event_stream: Any) -> None:
        while True:
            event = event_stream.next_event(timeout=0.1)
            if event is None:
                if _event_stream_closed(event_stream):
                    self._clear_turn_status()
                    self._clear_live_status()
                    if self._assistant_open:
                        self._finalize_assistant_stream()
                    return
                self._check_terminal_resize()
                self._refresh_turn_status_if_due()
                continue
            self._check_terminal_resize()
            self._handle_event(event)
            if str(getattr(event, "kind", "")) == "TurnCompleted":
                return

    def _handle_event(self, event: Any) -> None:
        from .textual_runtime import _event_delta, _payload_field

        kind = str(getattr(event, "kind", ""))
        try:
            self.app_runtime.handle_notification(event)
        except Exception:
            pass
        if kind == "AgentMessageDelta":
            delta = _event_delta(event)
            if not delta:
                return
            self._turn_status_suppressed = True
            self._hide_inline_status(redraw_bottom_pane=True)
            if not self._assistant_open:
                prefix = "\u2022 "
                self._open_assistant_stream_cell(prefix)
            self._write_assistant_delta(delta)
            return
        if kind == "ItemStarted":
            command = _event_command_text(event)
            if command:
                self._turn_status_suppressed = True
                self._clear_live_status()
                if self._assistant_open:
                    self._finalize_assistant_stream()
                self._write_history_cell(f"\u2022 Running {command}")
            return
        if kind == "ItemCompleted":
            command = _event_command_text(event)
            if command:
                self._turn_status_suppressed = True
                self._clear_live_status()
                if self._assistant_open:
                    self._finalize_assistant_stream()
                self._write_history_cell(f"\u2022 Ran {command}")
            return
        if kind == "Error":
            if not bool(_payload_field(getattr(event, "payload", {}), "will_retry", False)):
                return
            self._turn_status_suppressed = True
            error = _payload_field(getattr(event, "payload", {}), "error", {})
            message = str(_payload_field(error, "message", "") or "Request failed")
            details = _payload_field(error, "additional_details", None)
            self._write_live_status(message, None if details is None else str(details))
            return
        if kind == "TurnCompleted":
            self._clear_turn_status()
            self._clear_live_status()
            if self._assistant_open:
                self._finalize_assistant_stream()

    def _write_assistant_delta(self, delta: str) -> None:
        self._assistant_stream_text += delta
        continuation_prefix = "  "
        continuation_width = self._display_width(continuation_prefix)
        width = self._history_wrap_width()
        for char in delta:
            if char == "\r":
                continue
            if char == "\n":
                self.stdout.write(f"\r\n{continuation_prefix}")
                self._assistant_stream_column = continuation_width
                continue
            char_width = self._char_display_width(char)
            if (
                char_width > 0
                and self._assistant_stream_column > continuation_width
                and self._assistant_stream_column + char_width > width
            ):
                self.stdout.write(f"\r\n{continuation_prefix}")
                self._assistant_stream_column = continuation_width
            self.stdout.write(char)
            self._assistant_stream_column += char_width
        self.stdout.flush()

    def _finalize_assistant_stream(self) -> None:
        if not (self._stdin_is_terminal and self._layout_active):
            self.stdout.write("\n")
            self.stdout.flush()
        self._finish_history_output()
        text = self._assistant_stream_text
        self._assistant_open = False
        self._assistant_stream_column = 0
        self._assistant_stream_text = ""
        if text:
            self._record_history_projection_cell(f"\u2022 {text}")
        if self._resize_reflow_pending:
            self._resize_reflow_pending = False
            self._clear_terminal_for_resize_replay()
            self._replay_history_projection_into_scrollback()
            self._render_bottom_pane(check_resize=False)

    def _shutdown(self) -> None:
        self._deactivate_layout()
        try:
            self.app_runtime.shutdown_current_thread(timeout_seconds=1.0)
        except Exception:
            pass


def _event_stream_closed(event_stream: Any) -> bool:
    closed = getattr(event_stream, "closed", None)
    if callable(closed):
        try:
            return bool(closed())
        except Exception:
            return False
    if closed is not None:
        return bool(closed)
    return bool(getattr(event_stream, "is_closed", False))


def _event_command_text(event: Any) -> str:
    from .textual_runtime import _payload_field

    payload = getattr(event, "payload", {}) or {}
    item = _payload_field(payload, "item", payload)
    command = _payload_field(item, "command", None)
    if isinstance(command, (list, tuple)):
        return " ".join(str(part) for part in command)
    return "" if command is None else str(command)


__all__ = ["ScrollbackTuiRunner", "run_scrollback_tui"]
