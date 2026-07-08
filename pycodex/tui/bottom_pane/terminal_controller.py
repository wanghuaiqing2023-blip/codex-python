"""Terminal bottom-pane controller for the hybrid product path.

The controller wires Rust-owned bottom-pane state to Python's hybrid terminal
backend.  ``view_stack`` owns draft/popup/active-view semantics,
``app.resize_reflow`` owns footprint repaint decisions, and
``custom_terminal`` owns terminal repaint state and side effects through
``terminal_projection``.
"""

from __future__ import annotations

import os
from typing import Callable, TextIO, TypeVar

from .terminal_footprint import TerminalBottomPaneFootprint
from .terminal_projection import TerminalBottomPaneRequestRunner
from .view_stack import (
    TerminalBottomPaneViewState,
    TerminalCommandViewFactory,
    TerminalSelectionEventHandler,
)
_ExternalRepaintResult = TypeVar("_ExternalRepaintResult")
from ..chatwidget.status_surfaces import TerminalLiveStatusSurface
from ..app.resize_reflow import (
    create_terminal_bottom_pane_footprint_cycle_runner,
)


class TerminalBottomPaneController:
    """Runtime-facing controller for the real-terminal bottom live pane.

    This class is glue: it holds the bottom-pane owner state object and terminal
    callbacks, but it should not grow command-popup, model-picker, footprint, or
    buffer-rendering behavior of its own.
    """

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
        open_command_view: TerminalCommandViewFactory | None = None,
        on_selection_events: TerminalSelectionEventHandler | None = None,
        repaint_footprint: Callable[[TerminalBottomPaneFootprint, TerminalBottomPaneFootprint], None] | None = None,
        cursor_visible: Callable[[], bool] | None = None,
    ) -> None:
        self._open_command_view = open_command_view
        self._on_selection_events = on_selection_events
        composer_cursor_visible = cursor_visible or (lambda: True)
        self._view_state = TerminalBottomPaneViewState.new()
        self._footprint_runner = create_terminal_bottom_pane_footprint_cycle_runner()
        self._request_runner = TerminalBottomPaneRequestRunner(
            writer,
            terminal_size=terminal_size,
            resize=resize,
        )
        self._history_bottom_row = self._footprint_runner.history_bottom_row_callback(
            terminal_size=self._request_runner.terminal_size,
            live_status=live_status,
            bottom_pane_state=self._view_state,
            composer_cursor_visible=composer_cursor_visible,
        )
        self._clear_bottom_pane = self._footprint_runner.clear_callback(
            live_status=live_status,
            clear_factory=self._request_runner.clear_factory_callback(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
            ),
        )
        self._render_for_view_state = self._footprint_runner.render_for_view_state_callback(
            terminal_size=self._request_runner.terminal_size,
            live_status=live_status,
            bottom_pane_state=self._view_state,
            composer_cursor_visible=composer_cursor_visible,
            repaint_footprint=repaint_footprint,
            run_external_repaint=self.run_external_repaint,
            render_factory=self._request_runner.render_pass_factory_callback(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
                footer_text=footer_text,
            ),
        )

    def sync_draft(self, draft: str) -> None:
        """Synchronize composer draft into the bottom-pane owner state."""

        self._view_state.apply_draft(draft)

    def handle_composer_key(self, draft: str, event_kind: str, event_text: str = "") -> str | None:
        return self._view_state.handle_composer_key(
            draft,
            event_kind,
            event_text,
            on_selection_events=self._on_selection_events,
            open_command_view=self._open_command_view,
        )

    def history_bottom_row(self, reserve_active_bottom_pane: bool = False) -> int:
        return self._history_bottom_row(reserve_active_bottom_pane)

    def clear(self, *, check_resize: bool = True) -> bool:
        return self._clear_bottom_pane(check_resize)

    def clear_without_resize_check(self) -> bool:
        """Clear the live pane when the caller already owns resize handling."""

        return self.clear(check_resize=False)

    def restore_cursor(self) -> None:
        """Leave the host terminal with a visible cursor after TUI shutdown."""

        self._request_runner.restore_cursor()

    def run_external_repaint(self, repaint: Callable[[], _ExternalRepaintResult]) -> _ExternalRepaintResult:
        """Run external terminal writes through the live-viewport lifecycle."""

        return self._request_runner.run_external_repaint(repaint)

    def render_after_history_repaint(self, *, check_resize: bool = False) -> bool:
        """Render after external history viewport writes may have dirtied blank live rows."""

        return self.render(check_resize=check_resize, clear_external_blank_rows=True)

    def render_without_resize_check(self) -> bool:
        """Render the live pane when the caller already owns resize handling."""

        return self.render(check_resize=False)

    def render(self, *, check_resize: bool = True, clear_external_blank_rows: bool = False) -> bool:
        return self._render_for_view_state(
            check_resize=check_resize,
            clear_external_blank_rows=clear_external_blank_rows,
        )

__all__ = [
    "TerminalBottomPaneController",
]
