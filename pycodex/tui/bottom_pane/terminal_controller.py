"""Terminal bottom-pane controller for the hybrid product path.

The controller wires Rust-owned bottom-pane state to Python's hybrid terminal
backend. ``view_stack`` owns draft/popup/active-view semantics, ``tui`` owns
the inline viewport, and ``custom_terminal`` owns backend side effects through
``terminal_projection``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, TextIO, TypeVar


from .chat_composer import TERMINAL_COMPOSER_SHUTDOWN_PLACEHOLDER
from .terminal_projection import TerminalBottomPaneRequestRunner
from .view_stack import (
    TerminalBottomPaneViewState,
    TerminalCommandViewFactory,
    TerminalSelectionEventHandler,
)
_ExternalRepaintResult = TypeVar("_ExternalRepaintResult")
from ..chatwidget.status_surfaces import TerminalLiveStatusSurface
from ..tui import create_terminal_bottom_pane_viewport_cycle_runner


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
        footer_right_text: Callable[[], str] | None = None,
        open_command_view: TerminalCommandViewFactory | None = None,
        on_selection_events: TerminalSelectionEventHandler | None = None,
        cursor_visible: Callable[[], bool] | None = None,
        set_terminal_title_requires_action: Callable[[bool], None] | None = None,
        command_popup_flags: object | None = None,
    ) -> None:
        self._open_command_view = open_command_view
        self._on_selection_events = on_selection_events
        self._set_terminal_title_requires_action = set_terminal_title_requires_action or (lambda _required: None)
        composer_cursor_visible = cursor_visible or (lambda: True)
        self._view_state = TerminalBottomPaneViewState.new(command_popup_flags)

        def visible_live_status() -> TerminalLiveStatusSurface:
            if not self._view_state.status_indicator_visible:
                return TerminalLiveStatusSurface.inactive()
            return live_status()

        self._visible_live_status = visible_live_status
        self._request_runner = TerminalBottomPaneRequestRunner(
            writer,
            terminal_size=terminal_size,
            resize=resize,
        )
        self._viewport_runner = create_terminal_bottom_pane_viewport_cycle_runner(
            terminal_size=self._request_runner.terminal_size,
            resize=resize,
            scroll_region_up=self._request_runner.scroll_region_up,
            scroll_region_down=self._request_runner.scroll_region_down,
            clear_after_position=self._request_runner.clear_after_position,
            invalidate_viewport=self._request_runner.invalidate_viewport,
        )
        self._history_bottom_row = self._viewport_runner.history_bottom_row_callback(
            terminal_size=self._request_runner.terminal_size,
            live_status=self._visible_live_status,
            bottom_pane_state=self._view_state,
            composer_cursor_visible=composer_cursor_visible,
        )
        self._resize_reflow_replay_callback = (
            self._viewport_runner.resize_reflow_replay_callback_factory(
                terminal_size=self._request_runner.terminal_size,
                live_status=self._visible_live_status,
                bottom_pane_state=self._view_state,
                composer_cursor_visible=composer_cursor_visible,
            )
        )
        self._clear_bottom_pane = self._viewport_runner.clear_callback(
            live_status=self._visible_live_status,
            clear_factory=self._request_runner.clear_factory_callback(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
            ),
        )
        self._render_for_view_state = self._viewport_runner.render_for_view_state_callback(
            terminal_size=self._request_runner.terminal_size,
            live_status=self._visible_live_status,
            bottom_pane_state=self._view_state,
            composer_cursor_visible=composer_cursor_visible,
            render_factory=self._request_runner.render_pass_factory_callback(
                stdin_is_terminal=stdin_is_terminal,
                layout_active=layout_active,
                footer_text=footer_text,
                footer_right_text=footer_right_text or (lambda: ""),
            ),
        )

    def sync_draft(self, draft: str) -> None:
        """Synchronize composer draft into the bottom-pane owner state."""

        self._view_state.apply_draft(draft)

    @property
    def composer(self) -> object:
        return self._view_state.composer

    def _record_submission(self, text: str) -> None:
        """Record a submitted composer entry through its Rust-owned history."""

        self._view_state.record_submission(text)

    def _configure_history(
        self,
        thread_id: object,
        log_id: int,
        entry_count: int,
        lookup: Callable[[int, int], object | None] | None,
    ) -> None:
        """Bind persistent composer history through the bottom-pane owner."""

        self._view_state.configure_history(thread_id, log_id, entry_count, lookup)

    def sync_active_tail(self, lines: tuple[str, ...]) -> None:
        """Apply chatwidget-owned mutable stream-tail frame input."""

        self._view_state.apply_active_tail(lines)

    def sync_pending_thread_approvals(self, approvals: list[str]) -> None:
        """Project Rust pending-thread approval rows through bottom-pane state."""

        self._view_state.apply_pending_thread_approvals(approvals)
        self.render_without_resize_check()

    def show_shutdown(self) -> None:
        """Render Rust ChatComposer's disabled shutdown presentation."""

        self._view_state.apply_draft(TERMINAL_COMPOSER_SHUTDOWN_PLACEHOLDER)
        self.render_without_resize_check()

    def _show_selection_view(self, params: object) -> None:
        """Show a command-owned selection view through the shared stack."""

        self._view_state.show_selection_view(params)
        self._sync_terminal_title_requires_action()

    def show_view(self, view: object) -> object:
        """Push a generic Rust-owned active view through the shared stack."""

        active_view = self._view_state.show_view(view)
        self._sync_terminal_title_requires_action()
        return active_view

    def dismiss_app_server_request(self, request: object) -> bool:
        """Remove an externally resolved request from the active view stack."""

        dismissed = self._view_state.dismiss_app_server_request(request)
        if dismissed:
            self._sync_terminal_title_requires_action()
            self.render_without_resize_check()
        return dismissed

    def has_active_view(self) -> bool:
        return self._view_state.active_view is not None

    def live_status_footprint_active(self) -> bool:
        """Return the status footprint actually rendered by ``BottomPane``."""

        return self._visible_live_status().footprint_active

    def handle_active_view_input(self, event: object, event_text: str = "") -> bool:
        """Route one task-time terminal event to the active bottom-pane view."""

        if isinstance(event, str):
            event_kind = event
        else:
            event_kind = str(getattr(event, "kind", ""))
            event_text = str(getattr(event, "text", ""))

        if not self.has_active_view() or event_kind == "eof":
            return False
        self._view_state.handle_composer_event(
            event_kind,
            event_text,
            on_selection_events=self._on_selection_events,
            open_command_view=self._open_command_view,
        )
        self._sync_terminal_title_requires_action()
        self.render_without_resize_check()
        return True

    def handle_composer_event(
        self,
        event_kind: str,
        event_text: str = "",
        now: float | None = None,
        detect_paste_bursts: bool = False,
    ) -> object:
        result = self._view_state.handle_composer_event(
            event_kind,
            event_text,
            now=now,
            detect_paste_bursts=detect_paste_bursts,
            on_selection_events=self._on_selection_events,
            open_command_view=self._open_command_view,
        )
        self._sync_terminal_title_requires_action()
        return result

    def _sync_terminal_title_requires_action(self) -> None:
        self._set_terminal_title_requires_action(
            self._view_state.terminal_title_requires_action()
        )

    def history_bottom_row(self, reserve_active_bottom_pane: bool = False) -> int:
        return self._history_bottom_row(reserve_active_bottom_pane)

    def prepare_history_insert(self, inserted_rows: int) -> None:
        self._viewport_runner.prepare_history_insert(inserted_rows)

    def resize_reflow_replay_callback(
        self,
        replay_history_scrollback: Callable[[], Any],
    ) -> Callable[[], Any]:
        """Bind app-owned replay behind TUI-owned viewport preparation."""

        return self._resize_reflow_replay_callback(replay_history_scrollback)

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

        return self.render(check_resize=check_resize, clear_external_blank_rows=False)

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
