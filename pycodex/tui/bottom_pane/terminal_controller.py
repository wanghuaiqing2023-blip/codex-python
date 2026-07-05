"""Terminal bottom-pane controller for the hybrid product path.

The controller owns terminal-path bottom-pane state orchestration: draft text,
slash popup navigation, active selection views, and footprint-change callbacks.
Actual terminal repaint side effects remain in ``terminal_surface``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, TextIO

from .command_popup import CommandPopup, CommandPopupFlags
from .list_selection_view import (
    ListSelectionView,
    SelectionViewParams,
    handle_key_event as handle_selection_key_event,
)
from .selection_popup_common import TerminalPopupLine as TerminalBottomPanePopupLine
from .terminal_frame import (
    TerminalBottomPaneActionPlan,
    TerminalBottomPaneFootprint,
    history_bottom_row,
    terminal_bottom_pane_clear_plan,
    terminal_bottom_pane_frame,
    terminal_bottom_pane_frame_buffer,
    terminal_bottom_pane_render_plan,
)
from .terminal_surface import (
    clear_bottom_pane_and_flush,
    render_terminal_bottom_pane_frame,
)
from ..custom_terminal import flush_writer, hide_cursor_ansi, show_cursor_ansi
from ..chatwidget.status_surfaces import TerminalLiveStatusSurface
from ..ratatui_bridge import FrameBufferState as RatatuiFrameBufferState


class TerminalBottomPaneSurfaceWriter:
    """Stateful controller for the real-terminal bottom pane surface."""

    def __init__(
        self,
        writer: TextIO,
        *,
        stdin_is_terminal: Callable[[], bool],
        layout_active: Callable[[], bool],
        live_status: Callable[[], TerminalLiveStatusSurface],
        terminal_size: Callable[[], os.terminal_size],
        resize: Callable[[], None],
        footer_text: Callable[[], str],
        open_model_view: Callable[[], SelectionViewParams | None] | None = None,
        on_selection_events: Callable[[tuple[Any, ...]], SelectionViewParams | None] | None = None,
        repaint_footprint: Callable[[TerminalBottomPaneFootprint, TerminalBottomPaneFootprint], None] | None = None,
        cursor_visible: Callable[[], bool] | None = None,
    ) -> None:
        self.writer = writer
        self.stdin_is_terminal = stdin_is_terminal
        self.layout_active = layout_active
        self.live_status = live_status
        self.terminal_size = terminal_size
        self.resize = resize
        self.footer_text = footer_text
        self.open_model_view = open_model_view
        self.on_selection_events = on_selection_events
        self.repaint_footprint = repaint_footprint
        self.cursor_visible = cursor_visible or (lambda: True)
        self.draft = ""
        self.command_popup = CommandPopup.new(CommandPopupFlags(), [])
        self.command_popup_visible = False
        self.active_view: ListSelectionView | None = None
        self.view_stack: list[ListSelectionView] = []
        self.selection_events: list[Any] = []
        self._last_popup_height = 0
        self._last_live_status_active = False
        self._last_popup_was_active_view = False
        self._buffer_state = RatatuiFrameBufferState()
        self._terminal_cursor_visible = True

    def apply_draft(self, draft: str) -> None:
        self.draft = str(draft)
        self._sync_command_popup()

    def handle_composer_key(self, draft: str, event_kind: str, event_text: str = "") -> str | None:
        self.apply_draft(draft)
        key = terminal_popup_key(event_kind, event_text)
        if self.active_view is not None:
            if key:
                handle_selection_key_event(self.active_view, key)
                self._drain_active_view_events()
                self._pop_completed_views()
            elif str(event_kind).lower() in {"eof", "interrupt"}:
                return None
            return draft
        if not self.command_popup_visible:
            return None
        if key == "up":
            self.command_popup.move_up()
            return draft
        if key == "down":
            self.command_popup.move_down()
            return draft
        if key == "tab":
            selected = self.command_popup.selected_item()
            if selected is None:
                return draft
            return f"/{selected.command()} "
        if key == "enter":
            selected = self.command_popup.selected_item()
            command = selected.command() if selected is not None else draft_command_name(draft)
            if command == "model":
                params = self.open_model_view() if self.open_model_view is not None else None
                if params is not None:
                    self.show_selection_view(params)
                return ""
        return None

    def show_selection_view(self, params: SelectionViewParams) -> None:
        self.selection_events.clear()
        self.active_view = ListSelectionView.new(params, self.selection_events)
        self.view_stack = [self.active_view]
        self.command_popup_visible = False

    def history_bottom_row(self, reserve_active_bottom_pane: bool = False) -> int:
        return history_bottom_row(
            self.terminal_size(),
            live_status_active=self.live_status().footprint_active,
            popup_height=self._popup_height(),
            reserve_active_bottom_pane=reserve_active_bottom_pane,
        )

    def clear(self, *, check_resize: bool = True) -> bool:
        cleared = run_terminal_bottom_pane_clear(
            self.writer,
            stdin_is_terminal=self.stdin_is_terminal(),
            layout_active=self.layout_active(),
            check_resize=check_resize,
            live_status=self.live_status(),
            terminal_size=self.terminal_size,
            resize=self.resize,
            buffer_state=self._buffer_state,
        )
        if cleared:
            self._last_popup_height = 0
            self._last_live_status_active = False
        return cleared

    def restore_cursor(self) -> None:
        """Leave the host terminal with a visible cursor after TUI shutdown."""

        if self._terminal_cursor_visible:
            return
        show_cursor_ansi(self.writer)
        self._terminal_cursor_visible = True
        flush_writer(self.writer)

    def reset_buffer_state(self) -> None:
        """Invalidate the live-pane previous buffer after external repaint."""

        self._buffer_state.reset()

    def render_after_history_repaint(self, *, check_resize: bool = False) -> bool:
        """Render after external history viewport writes may have dirtied blank live rows."""

        return self.render(check_resize=check_resize, clear_external_blank_rows=True)

    def render(self, *, check_resize: bool = True, clear_external_blank_rows: bool = False) -> bool:
        popup_lines = tuple(self._popup_lines())
        live_status = self.live_status()
        cursor_visible = self._frame_cursor_visible()
        self._sync_terminal_cursor_visibility(cursor_visible)
        previous_footprint = TerminalBottomPaneFootprint(
            live_status_active=self._last_live_status_active,
            popup_height=self._last_popup_height,
        )
        current_footprint = TerminalBottomPaneFootprint.from_surface(live_status, len(popup_lines))
        size = self.terminal_size()
        old_height = previous_footprint.height_for_size(size)
        new_height = current_footprint.height_for_size(size)
        current_popup_is_active_view = self.active_view is not None
        popup_footprint_changed = (
            previous_footprint.popup_height != current_footprint.popup_height
            and (self._last_popup_was_active_view or current_popup_is_active_view)
        )
        if popup_footprint_changed and new_height >= old_height:
            self._repaint_footprint(previous_footprint, current_footprint)
        rendered = run_terminal_bottom_pane_render(
            self.writer,
            stdin_is_terminal=self.stdin_is_terminal(),
            layout_active=self.layout_active(),
            check_resize=check_resize,
            draft=self.draft,
            footer_text=self.footer_text(),
            popup_lines=popup_lines,
            live_status=live_status,
            terminal_size=self.terminal_size,
            resize=self.resize,
            clear_popup_height=self._last_popup_height,
            clear_live_status_active=self._last_live_status_active,
            buffer_state=self._buffer_state,
            cursor_visible=cursor_visible,
            clear_external_blank_rows=clear_external_blank_rows,
        )
        if popup_footprint_changed and new_height < old_height:
            self._repaint_footprint(previous_footprint, current_footprint)
            if rendered:
                run_terminal_bottom_pane_render(
                    self.writer,
                    stdin_is_terminal=self.stdin_is_terminal(),
                    layout_active=self.layout_active(),
                    check_resize=False,
                    draft=self.draft,
                    footer_text=self.footer_text(),
                    popup_lines=popup_lines,
                    live_status=live_status,
                    terminal_size=self.terminal_size,
                    resize=self.resize,
                    clear_popup_height=0,
                    clear_live_status_active=live_status.footprint_active,
                    buffer_state=self._buffer_state,
                    cursor_visible=cursor_visible,
                    clear_external_blank_rows=clear_external_blank_rows,
                )
        if rendered:
            self._last_popup_height = len(popup_lines)
            self._last_live_status_active = live_status.footprint_active
            self._last_popup_was_active_view = current_popup_is_active_view
        return rendered

    def _repaint_footprint(
        self,
        previous: TerminalBottomPaneFootprint,
        current: TerminalBottomPaneFootprint,
    ) -> None:
        if self.repaint_footprint is None:
            return
        if previous == current:
            return
        self._buffer_state.reset()
        self.repaint_footprint(previous, current)
        self._buffer_state.reset()

    def _frame_cursor_visible(self) -> bool:
        if self.active_view is not None:
            return False
        return bool(self.cursor_visible())

    def _sync_terminal_cursor_visibility(self, visible: bool) -> None:
        if not self.stdin_is_terminal() or not self.layout_active():
            return
        if visible == self._terminal_cursor_visible:
            return
        if visible:
            show_cursor_ansi(self.writer)
        else:
            hide_cursor_ansi(self.writer)
        self._terminal_cursor_visible = visible

    def _sync_command_popup(self) -> None:
        if self.active_view is not None:
            self.command_popup_visible = False
            return
        visible = terminal_command_popup_visible_for_draft(self.draft)
        self.command_popup_visible = visible
        if visible:
            self.command_popup.on_composer_text_change(self.draft)

    def _popup_lines(self) -> list[TerminalBottomPanePopupLine]:
        if self.active_view is not None:
            return terminal_selection_view_lines(self.active_view, width=max(1, self.terminal_size().columns - 1))
        if not self.command_popup_visible:
            return []
        return terminal_command_popup_lines(self.command_popup, width=max(1, self.terminal_size().columns - 1))

    def _popup_height(self) -> int:
        return len(self._popup_lines())

    def _drain_active_view_events(self) -> None:
        if not self.selection_events:
            return
        events = tuple(self.selection_events)
        self.selection_events.clear()
        next_params = self.on_selection_events(events) if self.on_selection_events is not None else None
        if next_params is not None:
            self._push_selection_view(next_params)

    def _push_selection_view(self, params: SelectionViewParams) -> None:
        self.active_view = ListSelectionView.new(params, self.selection_events)
        self.view_stack.append(self.active_view)

    def _pop_completed_views(self) -> None:
        while self.view_stack and self.view_stack[-1].is_complete():
            completed = self.view_stack.pop()
            child_was_submitted = completed.completion() == "Submitted"
            while child_was_submitted and self.view_stack and self.view_stack[-1].dismiss_after_child_accept():
                parent = self.view_stack.pop()
                parent.clear_dismiss_after_child_accept()
                child_was_submitted = parent.completion() == "Submitted"
        self.active_view = self.view_stack[-1] if self.view_stack else None


def run_terminal_bottom_pane_action_plan(
    writer: TextIO,
    size: os.terminal_size,
    plan: TerminalBottomPaneActionPlan,
    *,
    move_cursor: Callable[[int, int], None] | None = None,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    buffer_state: RatatuiFrameBufferState | None = None,
    cursor_visible: bool = True,
    clear_external_blank_rows: bool = False,
) -> None:
    """Execute a planned real-terminal bottom-pane action.

    Rust owner: ``codex-tui::bottom_pane`` owns the action plan; the terminal
    controller owns product-path callback orchestration and delegates actual
    live-viewport repaint side effects to ``terminal_surface``.
    """

    if plan.action == "clear":
        clear_bottom_pane_and_flush(
            writer,
            size,
            live_status_active=plan.live_status_active,
        )
        if buffer_state is not None:
            buffer_state.reset()
        return
    if plan.action == "render" and plan.state is not None:
        frame = terminal_bottom_pane_frame(
            size,
            plan.state,
            clear_popup_height=clear_popup_height,
            clear_live_status_active=clear_live_status_active,
        )
        buffer = terminal_bottom_pane_frame_buffer(size, frame)
        render_terminal_bottom_pane_frame(
            writer,
            frame,
            buffer=buffer,
            previous_buffer=buffer_state.previous if buffer_state is not None else None,
            move_cursor=move_cursor,
            cursor_visible=cursor_visible,
            clear_external_blank_rows=clear_external_blank_rows,
        )
        if buffer_state is not None:
            buffer_state.update(buffer)
        flush_writer(writer)


def run_terminal_bottom_pane_clear(
    writer: TextIO,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool = True,
    live_status: TerminalLiveStatusSurface,
    terminal_size: Callable[[], os.terminal_size],
    resize: Callable[[], None],
    buffer_state: RatatuiFrameBufferState | None = None,
) -> bool:
    """Clear the real-terminal bottom pane through the terminal controller."""

    plan = terminal_bottom_pane_clear_plan(
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
        check_resize=check_resize,
        live_status=live_status,
    )
    if not plan.should_run:
        return False
    if plan.check_resize:
        resize()
        if buffer_state is not None:
            buffer_state.reset()
    run_terminal_bottom_pane_action_plan(
        writer,
        terminal_size(),
        plan,
        buffer_state=buffer_state,
    )
    return True


def run_terminal_bottom_pane_render(
    writer: TextIO,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool = True,
    draft: str,
    footer_text: str,
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = (),
    live_status: TerminalLiveStatusSurface,
    terminal_size: Callable[[], os.terminal_size],
    resize: Callable[[], None],
    move_cursor: Callable[[int, int], None] | None = None,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
    buffer_state: RatatuiFrameBufferState | None = None,
    cursor_visible: bool = True,
    clear_external_blank_rows: bool = False,
) -> bool:
    """Render the real-terminal bottom pane through the terminal controller."""

    plan = terminal_bottom_pane_render_plan(
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
        check_resize=check_resize,
        draft=draft,
        footer_text=footer_text,
        popup_lines=tuple(popup_lines),
        live_status=live_status,
    )
    if not plan.should_run:
        return False
    if plan.check_resize:
        resize()
        if buffer_state is not None:
            buffer_state.reset()
    run_terminal_bottom_pane_action_plan(
        writer,
        terminal_size(),
        plan,
        move_cursor=move_cursor,
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
        buffer_state=buffer_state,
        cursor_visible=cursor_visible,
        clear_external_blank_rows=clear_external_blank_rows,
    )
    return True


def terminal_command_popup_visible_for_draft(draft: str) -> bool:
    first_line = str(draft).replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    if not first_line.startswith("/"):
        return False
    command_text = first_line[1:].lstrip()
    return not any(char.isspace() for char in command_text)


def terminal_command_popup_lines(popup: CommandPopup, *, width: int) -> list[TerminalBottomPanePopupLine]:
    return list(popup.terminal_lines(width=width))


def terminal_selection_view_lines(view: ListSelectionView, *, width: int) -> list[TerminalBottomPanePopupLine]:
    return list(view.terminal_lines(width=width))


def terminal_popup_key(event_kind: str, event_text: str = "") -> str:
    kind = str(event_kind).lower()
    raw_text = str(event_text)
    text = raw_text.lower()
    if kind in {"text", "line", "paste"}:
        if raw_text in {"\r", "\n", "\r\n"} or text in {"enter", "return"}:
            return "enter"
        if raw_text == "\t":
            return "tab"
        if raw_text == "\x1b" or text in {"escape", "esc"}:
            return "esc"
        if kind == "line" and raw_text == "":
            return "enter"
        return ""
    if kind == "key":
        if text in {"up", "down", "tab", "\t", "enter", "return", "\r", "\n", "escape", "esc", "\x1b"}:
            if text in {"enter", "return", "\r", "\n"}:
                return "enter"
            if text in {"escape", "\x1b"}:
                return "esc"
            return "tab" if text == "\t" else text
        if len(text) == 1:
            return text
    if kind in {"up", "down", "tab", "enter", "return", "esc", "escape"}:
        if kind == "return":
            return "enter"
        if kind == "escape":
            return "esc"
        return kind
    return ""


def draft_command_name(draft: str) -> str:
    first_line = str(draft).replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    if not first_line.startswith("/"):
        return ""
    token = first_line[1:].lstrip()
    return token.split()[0] if token.split() else ""


__all__ = [
    "TerminalBottomPaneSurfaceWriter",
    "draft_command_name",
    "run_terminal_bottom_pane_action_plan",
    "run_terminal_bottom_pane_clear",
    "run_terminal_bottom_pane_render",
    "terminal_command_popup_lines",
    "terminal_command_popup_visible_for_draft",
    "terminal_popup_key",
    "terminal_selection_view_lines",
]
