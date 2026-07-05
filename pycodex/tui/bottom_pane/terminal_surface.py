"""Terminal live-pane helpers for Rust ``codex-tui::bottom_pane``.

The Rust bottom pane renders through ratatui.  Python's real-terminal product
path keeps finalized transcript text in native scrollback, so this small helper
owns the live bottom-pane footprint and repaint commands for that path.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable, TextIO

from .command_popup import COMMAND_COLUMN_WIDTH, CommandPopup, CommandPopupFlags
from .list_selection_view import (
    ListSelectionView,
    SelectionViewParams,
    handle_key_event as handle_selection_key_event,
)
from .popup_consts import MAX_POPUP_ROWS
from .selection_popup_common import Rect, render_rows_with_col_width_mode
from ..custom_terminal import (
    clear_inline_status_line,
    clear_line_at,
    display_width,
    move_cursor as terminal_move_cursor,
    reset_scroll_region,
    write_at,
    write_inline_status_line,
)


IDLE_BOTTOM_PANE_ROWS = 4
STATUS_BOTTOM_PANE_ROWS = 6


@dataclass(frozen=True)
class TerminalBottomPanePopupLine:
    text: str
    selected: bool = False


@dataclass(frozen=True)
class TerminalBottomPaneState:
    draft: str = ""
    footer_text: str = ""
    live_status_text: str | None = None
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = ()

    @property
    def live_status_active(self) -> bool:
        return bool(self.live_status_text)

    @property
    def popup_height(self) -> int:
        return len(self.popup_lines)


@dataclass(frozen=True)
class TerminalBottomPaneFrameWrite:
    row: int
    column: int
    text: str
    selected: bool = False


@dataclass(frozen=True)
class TerminalBottomPaneFrame:
    clear_rows: tuple[int, ...]
    writes: tuple[TerminalBottomPaneFrameWrite, ...]
    cursor_row: int
    cursor_column: int


@dataclass(frozen=True)
class TerminalBottomPaneRenderPolicy:
    selected_prefix: str = "\x1b[94m"
    selected_suffix: str = "\x1b[0m"


@dataclass(frozen=True)
class TerminalBottomPaneActionPlan:
    """Terminal side-effect plan for clear/render bottom-pane actions."""

    action: str
    check_resize: bool = False
    state: TerminalBottomPaneState | None = None
    live_status_active: bool = False

    @property
    def should_run(self) -> bool:
        return self.action != "skip"


@dataclass(frozen=True)
class TerminalLiveStatusSurface:
    """Runtime live-status state for the real-terminal bottom pane.

    Rust ``bottom_pane`` owns whether the status indicator expands the bottom
    pane footprint.  The terminal runner keeps the current state, but delegates
    footprint/render interpretation here.
    """

    active: bool = False
    text: str | None = None

    @classmethod
    def inactive(cls) -> "TerminalLiveStatusSurface":
        return cls(False, None)

    @classmethod
    def active_status(cls, text: str | None = None) -> "TerminalLiveStatusSurface":
        return cls(True, text)

    @property
    def footprint_active(self) -> bool:
        return bool(self.active and self.text)

    @property
    def render_text(self) -> str | None:
        return self.text if self.active else None

    def rows_for_size(self, size: os.terminal_size) -> list[int]:
        return bottom_pane_rows_for_size(size, live_status_active=self.footprint_active)


@dataclass(frozen=True)
class TerminalLiveStatusTransition:
    previous: TerminalLiveStatusSurface
    current: TerminalLiveStatusSurface


@dataclass(frozen=True)
class TerminalBottomPaneFootprint:
    """Rows reserved by the live bottom pane.

    Rust ``bottom_pane`` computes desired heights from the active view and
    composer/footer state.  The real-terminal adapter keeps the same boundary
    by reporting a compact footprint value to ``app::resize_reflow``.
    """

    live_status_active: bool = False
    popup_height: int = 0

    @classmethod
    def from_surface(cls, live_status: TerminalLiveStatusSurface, popup_height: int = 0) -> "TerminalBottomPaneFootprint":
        return cls(live_status_active=live_status.footprint_active, popup_height=max(0, int(popup_height)))

    def rows_for_size(self, size: os.terminal_size) -> list[int]:
        return bottom_pane_rows_for_size(
            size,
            live_status_active=self.live_status_active,
            popup_height=self.popup_height,
        )

    def height_for_size(self, size: os.terminal_size) -> int:
        return len(self.rows_for_size(size))


class TerminalBottomPaneSurfaceWriter:
    """Stateful terminal writer for the real-terminal bottom pane surface."""

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
        self.draft = ""
        self.command_popup = CommandPopup.new(CommandPopupFlags(), [])
        self.command_popup_visible = False
        self.active_view: ListSelectionView | None = None
        self.view_stack: list[ListSelectionView] = []
        self.selection_events: list[Any] = []
        self._last_popup_height = 0
        self._last_live_status_active = False
        self._last_popup_was_active_view = False

    def apply_draft(self, draft: str) -> None:
        self.draft = str(draft)
        self._sync_command_popup()

    def handle_composer_key(self, draft: str, event_kind: str, event_text: str = "") -> str | None:
        self.apply_draft(draft)
        key = _terminal_popup_key(event_kind, event_text)
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
            command = selected.command() if selected is not None else _draft_command_name(draft)
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
        )
        if cleared:
            self._last_popup_height = 0
            self._last_live_status_active = False
        return cleared

    def render(self, *, check_resize: bool = True) -> bool:
        popup_lines = tuple(self._popup_lines())
        live_status = self.live_status()
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
        self.repaint_footprint(previous, current)

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


@dataclass(frozen=True)
class TerminalLiveStatusActionPlan:
    """Terminal side-effect plan for live-status surface changes."""

    transition: TerminalLiveStatusTransition
    check_resize: bool = False
    repaint_footprint: bool = False
    render_bottom_pane: bool = False
    flush_writer: bool = False
    inline_status_text: str | None = None
    clear_inline_status: bool = False

    @property
    def changed(self) -> bool:
        return self.transition.previous != self.transition.current


def terminal_live_status_transition_to_status(
    previous: TerminalLiveStatusSurface,
    text: str | None = None,
) -> TerminalLiveStatusTransition:
    """Return the bottom-pane live-status transition for showing status."""

    return TerminalLiveStatusTransition(
        previous=previous,
        current=TerminalLiveStatusSurface.active_status(text),
    )


def terminal_live_status_transition_to_inactive(
    previous: TerminalLiveStatusSurface,
) -> TerminalLiveStatusTransition:
    """Return the bottom-pane live-status transition for hiding status."""

    return TerminalLiveStatusTransition(
        previous=previous,
        current=TerminalLiveStatusSurface.inactive(),
    )


def terminal_live_status_show_plan(
    previous: TerminalLiveStatusSurface,
    text: str,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
) -> TerminalLiveStatusActionPlan:
    """Plan live-status show/update side effects for the terminal product path."""

    transition = terminal_live_status_transition_to_status(previous, text)
    if stdin_is_terminal:
        return TerminalLiveStatusActionPlan(
            transition=transition,
            check_resize=layout_active,
            repaint_footprint=True,
            render_bottom_pane=True,
        )
    return TerminalLiveStatusActionPlan(
        transition=transition,
        inline_status_text=text,
        flush_writer=True,
    )


def terminal_live_status_hide_plan(
    previous: TerminalLiveStatusSurface,
    *,
    stdin_is_terminal: bool,
    redraw_bottom_pane: bool = True,
) -> TerminalLiveStatusActionPlan:
    """Plan live-status hide side effects for the terminal product path."""

    transition = terminal_live_status_transition_to_inactive(previous)
    if not previous.active:
        return TerminalLiveStatusActionPlan(transition=transition)
    if stdin_is_terminal:
        return TerminalLiveStatusActionPlan(
            transition=transition,
            repaint_footprint=True,
            render_bottom_pane=redraw_bottom_pane,
            flush_writer=not redraw_bottom_pane,
        )
    return TerminalLiveStatusActionPlan(
        transition=transition,
        clear_inline_status=True,
        flush_writer=True,
    )


def run_terminal_live_status_action_plan(
    writer: TextIO,
    plan: TerminalLiveStatusActionPlan,
    *,
    repaint_footprint: Callable[[TerminalLiveStatusSurface], None],
    render_bottom_pane: Callable[[], None],
) -> None:
    """Execute terminal side effects selected by a live-status action plan."""

    if plan.repaint_footprint:
        repaint_footprint(plan.transition.previous)
    if plan.render_bottom_pane:
        render_bottom_pane()
        return
    if plan.inline_status_text is not None:
        write_inline_status_line(writer, plan.inline_status_text)
    if plan.clear_inline_status:
        clear_inline_status_line(writer)
    if plan.flush_writer:
        _flush_writer(writer)


def run_terminal_live_status_show(
    writer: TextIO,
    previous: TerminalLiveStatusSurface,
    text: str,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: Callable[[], None],
    repaint_footprint: Callable[[TerminalLiveStatusSurface], None],
    render_bottom_pane: Callable[[], None],
    apply_state: Callable[[TerminalLiveStatusSurface], None] | None = None,
) -> TerminalLiveStatusSurface:
    """Show/update live status and return the new bottom-pane surface state."""

    plan = terminal_live_status_show_plan(
        previous,
        text,
        stdin_is_terminal=stdin_is_terminal,
        layout_active=layout_active,
    )
    if plan.check_resize:
        check_resize()
    if apply_state is not None:
        apply_state(plan.transition.current)
    run_terminal_live_status_action_plan(
        writer,
        plan,
        repaint_footprint=repaint_footprint,
        render_bottom_pane=render_bottom_pane,
    )
    return plan.transition.current


def run_terminal_live_status_hide(
    writer: TextIO,
    previous: TerminalLiveStatusSurface,
    *,
    stdin_is_terminal: bool,
    redraw_bottom_pane: bool = True,
    repaint_footprint: Callable[[TerminalLiveStatusSurface], None],
    render_bottom_pane: Callable[[], None],
    apply_state: Callable[[TerminalLiveStatusSurface], None] | None = None,
) -> TerminalLiveStatusSurface:
    """Hide live status and return the new bottom-pane surface state."""

    plan = terminal_live_status_hide_plan(
        previous,
        stdin_is_terminal=stdin_is_terminal,
        redraw_bottom_pane=redraw_bottom_pane,
    )
    if not plan.changed:
        return plan.transition.current
    if apply_state is not None:
        apply_state(plan.transition.current)
    run_terminal_live_status_action_plan(
        writer,
        plan,
        repaint_footprint=repaint_footprint,
        render_bottom_pane=render_bottom_pane,
    )
    return plan.transition.current


@dataclass(frozen=True)
class TerminalBottomPaneFootprintTransition:
    old_rows: tuple[int, ...]
    new_rows: tuple[int, ...]

    @property
    def changed(self) -> bool:
        return self.old_rows != self.new_rows


def bottom_pane_footprint_transition(
    size: os.terminal_size,
    previous: TerminalLiveStatusSurface,
    current: TerminalLiveStatusSurface,
    *,
    previous_popup_height: int = 0,
    current_popup_height: int = 0,
) -> TerminalBottomPaneFootprintTransition:
    previous_footprint = TerminalBottomPaneFootprint.from_surface(previous, previous_popup_height)
    current_footprint = TerminalBottomPaneFootprint.from_surface(current, current_popup_height)
    return bottom_pane_footprint_transition_for_footprints(
        size,
        previous_footprint,
        current_footprint,
    )


def bottom_pane_footprint_transition_for_footprints(
    size: os.terminal_size,
    previous: TerminalBottomPaneFootprint,
    current: TerminalBottomPaneFootprint,
) -> TerminalBottomPaneFootprintTransition:
    return TerminalBottomPaneFootprintTransition(
        old_rows=tuple(previous.rows_for_size(size)),
        new_rows=tuple(current.rows_for_size(size)),
    )


def bottom_pane_rows_for_size(size: os.terminal_size, *, live_status_active: bool, popup_height: int = 0) -> list[int]:
    rows = size.lines
    height = bottom_pane_height(live_status_active=live_status_active, popup_height=popup_height)
    if height != IDLE_BOTTOM_PANE_ROWS:
        return [max(1, rows - offset) for offset in range(height - 1, -1, -1)]
    return [
        max(1, rows - 3),
        max(1, rows - 2),
        max(1, rows - 1),
        max(1, rows),
    ]


def bottom_pane_height(*, live_status_active: bool, popup_height: int = 0) -> int:
    if popup_height:
        return max(
            STATUS_BOTTOM_PANE_ROWS if live_status_active else IDLE_BOTTOM_PANE_ROWS,
            (1 if live_status_active else 0) + 1 + int(popup_height) + 1,
        )
    return STATUS_BOTTOM_PANE_ROWS if live_status_active else IDLE_BOTTOM_PANE_ROWS


def history_bottom_row(
    size: os.terminal_size,
    *,
    live_status_active: bool,
    popup_height: int = 0,
    reserve_active_bottom_pane: bool = False,
) -> int:
    reserved = (
        STATUS_BOTTOM_PANE_ROWS
        if reserve_active_bottom_pane
        else bottom_pane_height(live_status_active=live_status_active, popup_height=popup_height)
    )
    return max(1, size.lines - reserved)


def terminal_bottom_pane_clear_plan(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool,
    live_status: TerminalLiveStatusSurface,
) -> TerminalBottomPaneActionPlan:
    """Plan clearing the real-terminal bottom pane."""

    if not (stdin_is_terminal and layout_active):
        return TerminalBottomPaneActionPlan(action="skip")
    return TerminalBottomPaneActionPlan(
        action="clear",
        check_resize=check_resize,
        live_status_active=live_status.footprint_active,
    )


def terminal_bottom_pane_render_plan(
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool,
    draft: str,
    footer_text: str,
    popup_lines: tuple[TerminalBottomPanePopupLine, ...] = (),
    live_status: TerminalLiveStatusSurface,
) -> TerminalBottomPaneActionPlan:
    """Plan rendering the real-terminal bottom pane."""

    if not (stdin_is_terminal and layout_active):
        return TerminalBottomPaneActionPlan(action="skip")
    return TerminalBottomPaneActionPlan(
        action="render",
        check_resize=check_resize,
        state=TerminalBottomPaneState(
            draft=draft,
            footer_text=footer_text,
            live_status_text=live_status.render_text,
            popup_lines=tuple(popup_lines),
        ),
    )


def status_row(size: os.terminal_size, *, live_status_active: bool) -> int | None:
    if not live_status_active:
        return None
    return max(1, size.lines - 5)


def composer_row(size: os.terminal_size) -> int:
    return max(1, size.lines - 2)


def footer_row(size: os.terminal_size) -> int:
    return max(1, size.lines)


def composer_line_text(draft: str) -> str:
    visible_draft = str(draft).replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    return f"\u203a {visible_draft}"


def truncate_display_width(text: str, width: int) -> str:
    budget = max(1, int(width))
    current = 0
    out: list[str] = []
    for char in str(text):
        char_width = display_width(char)
        if current + char_width > budget:
            break
        out.append(char)
        current += char_width
    return "".join(out)


def composer_cursor_column(size: os.terminal_size, draft: str) -> int:
    visible_line = truncate_display_width(composer_line_text(draft), max(1, size.columns - 1))
    return min(size.columns, max(3, 1 + display_width(visible_line)))


def clear_bottom_pane(writer: TextIO, size: os.terminal_size, *, live_status_active: bool) -> None:
    reset_scroll_region(writer)
    for row in bottom_pane_rows_for_size(size, live_status_active=live_status_active):
        clear_line_at(writer, row)


def clear_bottom_pane_and_flush(writer: TextIO, size: os.terminal_size, *, live_status_active: bool) -> None:
    """Clear the real-terminal bottom pane and flush the terminal writer."""

    clear_bottom_pane(writer, size, live_status_active=live_status_active)
    _flush_writer(writer)


def terminal_bottom_pane_frame(
    size: os.terminal_size,
    state: TerminalBottomPaneState,
    *,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
) -> TerminalBottomPaneFrame:
    clear_rows = tuple(bottom_pane_rows_for_size(
        size,
        live_status_active=state.live_status_active or clear_live_status_active,
        popup_height=max(state.popup_height, int(clear_popup_height)),
    ))

    columns = size.columns
    writes: list[TerminalBottomPaneFrameWrite] = []
    if state.popup_lines:
        rows = bottom_pane_rows_for_size(
            size,
            live_status_active=state.live_status_active,
            popup_height=state.popup_height,
        )
        cursor = 0
        if state.live_status_active and state.live_status_text:
            writes.append(TerminalBottomPaneFrameWrite(rows[cursor], 1, state.live_status_text[: max(0, columns - 1)]))
            cursor += 1
        composer = rows[cursor]
        writes.append(
            TerminalBottomPaneFrameWrite(
                composer,
                1,
                truncate_display_width(composer_line_text(state.draft), max(1, columns - 1)),
            )
        )
        cursor += 1
        for popup_line in state.popup_lines:
            if cursor >= len(rows) - 1:
                break
            line = truncate_display_width(popup_line.text, max(1, columns - 1))
            writes.append(TerminalBottomPaneFrameWrite(rows[cursor], 1, line, popup_line.selected))
            cursor += 1
        if state.footer_text:
            writes.append(TerminalBottomPaneFrameWrite(rows[-1], 1, state.footer_text[: max(0, columns - 1)]))
        return TerminalBottomPaneFrame(
            clear_rows=clear_rows,
            writes=tuple(writes),
            cursor_row=composer,
            cursor_column=composer_cursor_column(size, state.draft),
        )

    status = status_row(size, live_status_active=state.live_status_active)
    if status is not None and state.live_status_text:
        writes.append(TerminalBottomPaneFrameWrite(status, 1, state.live_status_text[: max(0, columns - 1)]))

    writes.append(
        TerminalBottomPaneFrameWrite(
            composer_row(size),
            1,
            truncate_display_width(composer_line_text(state.draft), max(1, columns - 1)),
        )
    )
    if state.footer_text:
        writes.append(TerminalBottomPaneFrameWrite(footer_row(size), 1, state.footer_text[: max(0, columns - 1)]))

    return TerminalBottomPaneFrame(
        clear_rows=clear_rows,
        writes=tuple(writes),
        cursor_row=composer_row(size),
        cursor_column=composer_cursor_column(size, state.draft),
    )


def render_terminal_bottom_pane_frame(
    writer: TextIO,
    frame: TerminalBottomPaneFrame,
    *,
    policy: TerminalBottomPaneRenderPolicy = TerminalBottomPaneRenderPolicy(),
    move_cursor: Callable[[int, int], None] | None = None,
) -> None:
    reset_scroll_region(writer)
    for row in frame.clear_rows:
        clear_line_at(writer, row)
    for item in frame.writes:
        text = item.text
        if item.selected:
            text = f"{policy.selected_prefix}{text}{policy.selected_suffix}"
        write_at(writer, item.row, item.column, text)
    if move_cursor is None:
        terminal_move_cursor(writer, frame.cursor_row, frame.cursor_column)
    else:
        move_cursor(frame.cursor_row, frame.cursor_column)


def render_bottom_pane(
    writer: TextIO,
    size: os.terminal_size,
    state: TerminalBottomPaneState,
    *,
    move_cursor: Callable[[int, int], None] | None = None,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
) -> None:
    frame = terminal_bottom_pane_frame(
        size,
        state,
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
    )
    render_terminal_bottom_pane_frame(writer, frame, move_cursor=move_cursor)


def render_bottom_pane_and_flush(
    writer: TextIO,
    size: os.terminal_size,
    state: TerminalBottomPaneState,
    *,
    move_cursor: Callable[[int, int], None] | None = None,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
) -> None:
    """Render the real-terminal bottom pane and flush the terminal writer."""

    render_bottom_pane(
        writer,
        size,
        state,
        move_cursor=move_cursor,
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
    )
    _flush_writer(writer)


def run_terminal_bottom_pane_action_plan(
    writer: TextIO,
    size: os.terminal_size,
    plan: TerminalBottomPaneActionPlan,
    *,
    move_cursor: Callable[[int, int], None] | None = None,
    clear_popup_height: int = 0,
    clear_live_status_active: bool = False,
) -> None:
    """Execute a planned real-terminal bottom-pane action."""

    if plan.action == "clear":
        clear_bottom_pane_and_flush(
            writer,
            size,
            live_status_active=plan.live_status_active,
        )
        return
    if plan.action == "render" and plan.state is not None:
        render_bottom_pane_and_flush(
            writer,
            size,
            plan.state,
            move_cursor=move_cursor,
            clear_popup_height=clear_popup_height,
            clear_live_status_active=clear_live_status_active,
        )


def run_terminal_bottom_pane_clear(
    writer: TextIO,
    *,
    stdin_is_terminal: bool,
    layout_active: bool,
    check_resize: bool = True,
    live_status: TerminalLiveStatusSurface,
    terminal_size: Callable[[], os.terminal_size],
    resize: Callable[[], None],
) -> bool:
    """Clear the real-terminal bottom pane through the bottom-pane surface.

    Rust ``bottom_pane`` owns whether the pane should draw; the Python terminal
    product path maps that draw to ordinary ANSI terminal operations while the
    runner supplies terminal state and resize callbacks.
    """

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
    run_terminal_bottom_pane_action_plan(
        writer,
        terminal_size(),
        plan,
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
) -> bool:
    """Render the real-terminal bottom pane through the bottom-pane surface."""

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
    run_terminal_bottom_pane_action_plan(
        writer,
        terminal_size(),
        plan,
        move_cursor=move_cursor,
        clear_popup_height=clear_popup_height,
        clear_live_status_active=clear_live_status_active,
    )
    return True


def terminal_command_popup_visible_for_draft(draft: str) -> bool:
    first_line = str(draft).replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    if not first_line.startswith("/"):
        return False
    command_text = first_line[1:].lstrip()
    return not any(char.isspace() for char in command_text)


def terminal_command_popup_lines(popup: CommandPopup, *, width: int) -> list[TerminalBottomPanePopupLine]:
    rows = popup.rows_from_matches(popup.filtered())
    return _render_generic_popup_rows(
        rows,
        popup.state,
        width=max(1, width),
        max_results=MAX_POPUP_ROWS,
        empty_message="no matches",
        column_width=COMMAND_COLUMN_WIDTH,
    )


def terminal_selection_view_lines(view: ListSelectionView, *, width: int) -> list[TerminalBottomPanePopupLine]:
    lines: list[TerminalBottomPanePopupLine] = []
    for header_line in _selection_header_lines(view.active_header()):
        lines.append(TerminalBottomPanePopupLine(header_line, False))
    rendered_rows = _render_generic_popup_rows(
        view.build_rows(),
        view.state,
        width=max(1, width),
        max_results=view.max_visible_rows(view.visible_len()),
        empty_message="no matches",
        column_width=view.rows_width(),
    )
    lines.extend(rendered_rows)
    return lines


def _render_generic_popup_rows(
    rows: list[Any],
    state: Any,
    *,
    width: int,
    max_results: int,
    empty_message: str,
    column_width: Any,
) -> list[TerminalBottomPanePopupLine]:
    buffer: list[Any] = []
    render_rows_with_col_width_mode(
        Rect(0, 0, max(1, width), max(1, max_results)),
        buffer,
        rows,
        state,
        max_results,
        empty_message,
        column_width,
    )
    return [
        TerminalBottomPanePopupLine(
            str(getattr(line, "text", line)),
            _line_has_accent_style(line),
        )
        for line in buffer
    ]


def _selection_header_lines(header: Any) -> list[str]:
    if header is None:
        return []
    if isinstance(header, tuple):
        return [str(part) for part in header if part]
    if isinstance(header, list):
        return [str(part) for part in header if part]
    return [str(header)]


def _line_has_accent_style(line: Any) -> bool:
    spans = getattr(line, "spans", ())
    for span in spans:
        style = str(getattr(span, "style", ""))
        if "accent" in style:
            return True
    return False


def _terminal_popup_key(event_kind: str, event_text: str = "") -> str:
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


def _draft_command_name(draft: str) -> str:
    first_line = str(draft).replace("\r\n", "\n").replace("\r", "\n").split("\n", 1)[0]
    if not first_line.startswith("/"):
        return ""
    token = first_line[1:].lstrip()
    return token.split()[0] if token.split() else ""


def _flush_writer(writer: TextIO) -> None:
    flush = getattr(writer, "flush", None)
    if callable(flush):
        flush()


__all__ = [
    "IDLE_BOTTOM_PANE_ROWS",
    "STATUS_BOTTOM_PANE_ROWS",
    "TerminalBottomPaneActionPlan",
    "TerminalBottomPaneFrame",
    "TerminalBottomPaneFrameWrite",
    "TerminalBottomPaneFootprint",
    "TerminalBottomPanePopupLine",
    "TerminalBottomPaneRenderPolicy",
    "TerminalBottomPaneSurfaceWriter",
    "TerminalBottomPaneState",
    "TerminalBottomPaneFootprintTransition",
    "TerminalLiveStatusActionPlan",
    "TerminalLiveStatusSurface",
    "TerminalLiveStatusTransition",
    "bottom_pane_footprint_transition",
    "bottom_pane_footprint_transition_for_footprints",
    "bottom_pane_height",
    "bottom_pane_rows_for_size",
    "clear_bottom_pane",
    "clear_bottom_pane_and_flush",
    "composer_cursor_column",
    "composer_line_text",
    "composer_row",
    "footer_row",
    "history_bottom_row",
    "render_bottom_pane",
    "render_bottom_pane_and_flush",
    "run_terminal_bottom_pane_action_plan",
    "run_terminal_bottom_pane_clear",
    "run_terminal_bottom_pane_render",
    "run_terminal_live_status_action_plan",
    "run_terminal_live_status_hide",
    "run_terminal_live_status_show",
    "status_row",
    "terminal_bottom_pane_frame",
    "terminal_bottom_pane_clear_plan",
    "terminal_bottom_pane_render_plan",
    "terminal_command_popup_lines",
    "terminal_command_popup_visible_for_draft",
    "terminal_selection_view_lines",
    "terminal_live_status_transition_to_inactive",
    "terminal_live_status_transition_to_status",
    "terminal_live_status_hide_plan",
    "terminal_live_status_show_plan",
    "truncate_display_width",
]
