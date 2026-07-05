"""Terminal scrollback-first interactive runtime.

Rust ownership:
- ``codex-tui::tui`` keeps finalized chat history in terminal scrollback.
- ``codex-tui::insert_history`` owns history insertion semantics.
- ``codex-tui::bottom_pane`` owns the live prompt/status surface.

This runtime is intentionally small: it restores the product-critical terminal
contract that finalized transcript text is ordinary terminal output, so native
terminal scroll, selection, and copy work like the Rust TUI.
"""

from __future__ import annotations

import sys
import time
from typing import Any, TextIO

from ..app.runtime import ActiveThreadRuntime, TuiAppRuntime
from ..app.history_ui import (
    TerminalClearUiExecutor,
    run_terminal_session_header_from_runtime,
)
from ..app.resize_reflow import (
    TerminalResizeCoordinator,
    TerminalResizeHistoryReplayer,
)
from ..bottom_pane.terminal_controller import (
    TerminalBottomPaneSurfaceWriter,
)
from ..bottom_pane.chat_composer import (
    run_terminal_composer_eof,
    run_terminal_composer_interrupt,
    run_terminal_composer_read_prompt,
    run_terminal_composer_submit,
)
from ..bottom_pane.footer import run_terminal_idle_footer_text_from_runtime
from ..chatwidget.model_popups import (
    ModelPopupContext,
    ModelPopupEvent,
    ModelPreset,
    open_model_popup,
    terminal_apply_model_popup_event,
    terminal_apply_model_popup_events,
    terminal_model_popup_context_from_runtime,
    terminal_model_presets_from_runtime,
)
from ..chatwidget.protocol import (
    TerminalProtocolEventDispatcher,
)
from ..chatwidget.status_surfaces import (
    TerminalStatusSurfaceWriter,
)
from ..chatwidget.turn_runtime import run_terminal_turn_submission
from ..custom_terminal import (
    clear_scrollback_and_visible_screen_ansi,
    reset_scroll_region,
    terminal_size,
)
from ..insert_history import (
    TerminalHistoryWriter,
)
from ..history_cell.messages import (
    TerminalAssistantStreamWriter,
    run_terminal_user_prompt_output,
)
from ..history_cell.session import run_terminal_startup_notices_from_runtime
from ..status.card import run_terminal_status_card_from_runtime
from .event_stream import (
    TerminalInputSourceProvider,
    run_terminal_turn_idle_tick,
    run_terminal_turn_event_loop,
)
from .local_command import TerminalLocalCommandDispatcher


def run_terminal_tui(
    *,
    active_thread_runtime: ActiveThreadRuntime | TuiAppRuntime,
    stdout: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    """Run the Rust-style scrollback-first TUI product path."""

    from ..runtime_projection import configure_app_runtime_thread_identity

    if isinstance(active_thread_runtime, TuiAppRuntime):
        app_runtime = active_thread_runtime
        configure_app_runtime_thread_identity(app_runtime, app_runtime.active_thread_runtime)
    else:
        app_runtime = TuiAppRuntime(active_thread_runtime=active_thread_runtime)
        configure_app_runtime_thread_identity(app_runtime, active_thread_runtime)
    runner = TerminalTuiRunner(app_runtime, stdout=stdout or sys.stdout, stdin=stdin or sys.stdin)
    return runner.run()


class TerminalTuiRunner:
    """Line-oriented live pane with ordinary terminal scrollback history."""

    def __init__(self, app_runtime: TuiAppRuntime, *, stdout: TextIO, stdin: TextIO) -> None:
        self.app_runtime = app_runtime
        self.stdout = stdout
        self.stdin = stdin
        self.exit_code = 0
        self._input_source_provider = TerminalInputSourceProvider(stdin)
        isatty = getattr(stdin, "isatty", None)
        self._stdin_is_terminal = bool(isatty()) if callable(isatty) else False
        self._model_popup_context: ModelPopupContext | None = None
        self._model_popup_presets: tuple[ModelPreset, ...] = ()
        self._bottom_pane = TerminalBottomPaneSurfaceWriter(
            stdout,
            stdin_is_terminal=lambda: self._stdin_is_terminal,
            layout_active=lambda: self._resize.layout_active,
            live_status=lambda: self._status.live_status,
            terminal_size=terminal_size,
            resize=lambda: self._resize.check_size_change(),
            footer_text=lambda: run_terminal_idle_footer_text_from_runtime(self.app_runtime),
            open_model_view=self._open_model_popup_view,
            on_selection_events=self._handle_model_popup_events,
            repaint_footprint=lambda previous, current: self._resize.run_bottom_pane_frame_footprint_reflow(
                previous,
                current,
            ),
            cursor_visible=lambda: not self._status.turn_active,
        )
        self._status = TerminalStatusSurfaceWriter(
            stdout,
            stdin_is_terminal=lambda: self._stdin_is_terminal,
            layout_active=lambda: self._resize.layout_active,
            check_resize=lambda: self._resize.check_size_change(),
            repaint_footprint=lambda previous: self._resize.run_bottom_pane_footprint_reflow(
                previous=previous,
                current=self._status.live_status,
            ),
            render_bottom_pane=self._bottom_pane.render,
        )
        self._resize_history = TerminalResizeHistoryReplayer(
            stdout,
            history_state=lambda: self._history.state,
            history_wrap_width=lambda: self._history.wrap_width(),
            terminal_active=lambda: self._resize.terminal_layout_active,
            live_status_footprint_active=lambda: self._status.live_status.footprint_active,
            history_bottom_row=self._bottom_pane.history_bottom_row,
            terminal_columns=lambda: terminal_size().columns,
            insert_replayed_history_lines=lambda materialized, reserve_active_bottom_pane: self._history.insert_lines(
                materialized,
                clear_bottom_pane=False,
                reserve_active_bottom_pane=reserve_active_bottom_pane,
                render_bottom_pane=False,
            ),
            apply_history_state=lambda state: setattr(self._history, "state", state),
            render_bottom_pane=lambda: self._bottom_pane.render_after_history_repaint(check_resize=False),
        )
        self._resize = TerminalResizeCoordinator(
            terminal_active=lambda: self._stdin_is_terminal,
            current_size=terminal_size,
            active_stream=lambda: self._assistant_stream.active,
            reset_terminal_scroll_region=lambda: reset_scroll_region(self.stdout),
            render_bottom_pane=lambda: self._bottom_pane.render(check_resize=False),
            repaint_history_viewport=self._repaint_history_viewport_preserving_bottom_pane,
            replay_history_scrollback=self._replay_history_scrollback_resetting_bottom_pane,
        )
        self._history = TerminalHistoryWriter(
            stdout,
            terminal_active=lambda: self._resize.terminal_layout_active,
            terminal_columns=lambda: terminal_size().columns,
            check_resize=lambda: self._resize.check_size_change(),
            history_bottom_row=self._bottom_pane.history_bottom_row,
            clear_bottom_pane=lambda: self._bottom_pane.clear(check_resize=False),
            render_bottom_pane=lambda: self._bottom_pane.render(check_resize=False),
        )
        self._assistant_stream = TerminalAssistantStreamWriter(
            wrap_width=lambda: self._history.wrap_width(),
            open_stream=self._history.open_stream,
            write_delta=self._history.write_stream_delta,
            finish_projection=self._history.finish_stream_projection,
            apply_history_state=lambda state: setattr(self._history, "state", state),
            finish_stream_reflow=self._resize.run_stream_finish_reflow,
            repaint_active_stream=self._repaint_history_viewport_preserving_bottom_pane,
        )
        self._protocol = TerminalProtocolEventDispatcher(
            handle_notification=self.app_runtime.handle_notification,
            assistant_stream_active=lambda: self._assistant_stream.active,
            assistant_delta=self._assistant_stream.handle_delta,
            command_started=self._history.write_cell,
            command_completed=self._history.write_cell,
            retry_error=self._status.show_live_status,
            suppress_turn_status=self._status.suppress_turn_status,
            clear_turn_status=self._status.clear_turn_status,
            hide_live_status=lambda: self._status.hide_inline_status(redraw_bottom_pane=True),
            clear_live_status=self._status.clear_live_status,
            finalize_active_stream=self._assistant_stream.finalize,
        )
        self._clear_ui = TerminalClearUiExecutor(
            deactivate_layout=self._resize.deactivate_layout,
            clear_terminal=lambda: clear_scrollback_and_visible_screen_ansi(self.stdout),
            flush_terminal=self.stdout.flush,
            apply_history_state=lambda state: setattr(self._history, "state", state),
            apply_assistant_stream_state=self._assistant_stream.apply_state,
            apply_resize_pending=self._resize.apply_pending,
            render_header=lambda: run_terminal_session_header_from_runtime(
                self.app_runtime,
                write_history_cell=self._history.write_cell,
                width=100,
            ),
            activate_layout=self._resize.activate_layout,
        )
        self._local_commands = TerminalLocalCommandDispatcher(
            clear=self._clear_ui.run,
            help_=self._history.write_cell,
            status=lambda: run_terminal_status_card_from_runtime(
                self.app_runtime,
                write_history_cell=self._history.write_cell,
            ),
        )

    def run(self) -> int:
        self._resize.activate_layout()
        run_terminal_session_header_from_runtime(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
            width=100,
        )
        run_terminal_startup_notices_from_runtime(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
            write_blank_line=self._history.write,
        )
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
            command_result = self._local_commands.run(prompt)
            if command_result == "exit":
                self._shutdown()
                return self.exit_code
            if command_result:
                continue
            run_terminal_user_prompt_output(
                prompt,
                terminal_active=self._resize.terminal_layout_active,
                clear_live_status=self._status.clear_live_status,
                write_history_cell=self._history.write_cell,
                render_bottom_pane=self._bottom_pane.render,
            )
            self._run_turn(prompt)

    def _read_prompt(self) -> str | None:
        return run_terminal_composer_read_prompt(
            terminal_active=self._resize.terminal_layout_active,
            get_input_source=self._input_source_provider.get,
            read_line=self.stdin.readline,
            write_nonterminal_prompt=lambda: (self.stdout.write("\n\u203a "), self.stdout.flush()),
            apply_draft=self._bottom_pane.apply_draft,
            check_resize=lambda: self._resize.check_size_change(),
            render=self._bottom_pane.render,
            clear_bottom_pane=lambda: self._bottom_pane.clear(check_resize=False),
            submit=lambda line: run_terminal_composer_submit(
                line,
                clear_bottom_pane=lambda: self._bottom_pane.clear(check_resize=False),
            ),
            interrupt=run_terminal_composer_interrupt,
            eof=lambda: run_terminal_composer_eof(
                clear_bottom_pane=lambda: self._bottom_pane.clear(check_resize=False),
            ),
            handle_key=self._bottom_pane.handle_composer_key,
        )

    def _open_model_popup_view(self) -> Any:
        self._model_popup_context = terminal_model_popup_context_from_runtime(self.app_runtime)
        self._model_popup_presets = terminal_model_presets_from_runtime(
            self.app_runtime,
            self._model_popup_context.current_model,
        )
        result = open_model_popup(self._model_popup_context, self._model_popup_presets)
        for event in result.events:
            self._apply_model_popup_event(event)
        return result.view

    def _handle_model_popup_events(self, events: tuple[Any, ...]) -> Any:
        return terminal_apply_model_popup_events(
            events,
            context=self._model_popup_context,
            presets=self._model_popup_presets,
            dispatch_app_event=self.app_runtime.handle_app_event,
        )

    def _apply_model_popup_event(self, event: ModelPopupEvent) -> Any:
        return terminal_apply_model_popup_event(
            event,
            context=self._model_popup_context,
            presets=self._model_popup_presets,
            dispatch_app_event=self.app_runtime.handle_app_event,
        )

    def _repaint_history_viewport_preserving_bottom_pane(self, *args: Any, **kwargs: Any) -> None:
        self._resize_history.repaint_viewport(*args, **kwargs)

    def _replay_history_scrollback_resetting_bottom_pane(self, *args: Any, **kwargs: Any) -> None:
        self._bottom_pane.reset_buffer_state()
        self._resize_history.replay_scrollback(*args, **kwargs)
        self._bottom_pane.reset_buffer_state()

    def _run_turn(self, prompt: str) -> None:
        run_terminal_turn_submission(
            prompt,
            started_at=time.monotonic(),
            append_history=getattr(self.app_runtime, "append_message_history_entry", None),
            apply_started_at=self._status.start_turn,
            reset_assistant_stream=self._assistant_stream.reset,
            clear_turn_status=self._status.clear_turn_status,
            render_turn_status=lambda: self._status.render_turn_status(force=True),
            submit_user_turn=self.app_runtime.submit_user_turn,
            consume_events=self._consume_events,
            close_turn=self._protocol.close_turn,
            write_error=self._history.write_cell,
            set_exit_code=lambda code: setattr(self, "exit_code", code),
        )

    def _consume_events(self, event_stream: Any) -> None:
        run_terminal_turn_event_loop(
            event_stream,
            timeout=0.1,
            on_event=self._protocol.handle_event,
            on_closed=self._protocol.close_turn,
            on_idle=lambda: run_terminal_turn_idle_tick(
                check_resize=self._resize.check_size_change,
                refresh_turn_status=self._status.refresh_turn_status_if_due,
            ),
            before_event=self._resize.check_size_change,
        )

    def _shutdown(self) -> None:
        self._bottom_pane.restore_cursor()
        self._resize.deactivate_layout()
        try:
            self.app_runtime.shutdown_current_thread(timeout_seconds=1.0)
        except Exception:
            pass

__all__ = ["TerminalTuiRunner", "run_terminal_tui"]
