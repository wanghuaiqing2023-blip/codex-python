"""Terminal scrollback-first interactive runtime.

Rust ownership:
- ``codex-tui::tui`` keeps finalized chat history in terminal scrollback.
- ``codex-tui::insert_history`` owns history insertion semantics.
- ``codex-tui::bottom_pane`` owns the live prompt/status pane.

This runtime is intentionally small: it restores the product-critical terminal
contract that finalized transcript text is ordinary terminal output, so native
terminal scroll, selection, and copy work like the Rust TUI.
"""

from __future__ import annotations

import sys
from typing import TextIO

from ..app.runtime import ActiveThreadRuntime, TuiAppRuntime
from ..app.history_ui import (
    TerminalClearUiExecutor,
    TerminalSessionHeaderWriter,
)
from ..app.resize_reflow import (
    TerminalResizeCoordinator,
    TerminalResizeHistoryReplayer,
)
from ..bottom_pane.terminal_controller import (
    TerminalBottomPaneController,
)
from ..bottom_pane.chat_composer import (
    TerminalComposerEffectRunner,
    TerminalComposerPromptReader,
)
from ..bottom_pane.footer import TerminalIdleFooterTextProvider
from ..chatwidget.protocol import (
    TerminalProtocolEventDispatcher,
)
from ..chatwidget.slash_dispatch import (
    TerminalLocalCommandDispatcher,
    TerminalPromptDispatcher,
    TerminalSlashCommandViewDispatcher,
)
from ..chatwidget.status_surfaces import (
    TerminalStatusSurfaceWriter,
)
from ..chatwidget.turn_runtime import TerminalTurnSubmissionRunner
from ..custom_terminal import (
    TerminalColumnProvider,
    TerminalScrollRegionResetter,
    terminal_size,
)
from ..insert_history import (
    TerminalHistoryWriter,
)
from ..history_cell.messages import (
    TerminalAssistantStreamWriter,
    TerminalUserPromptOutputWriter,
)
from ..history_cell.session import TerminalStartupNoticesWriter
from ..status.card import TerminalStatusCardWriter
from .event_stream import (
    TerminalInputSourceProvider,
    TerminalTurnEventLoopRunner,
    TerminalTurnIdleTicker,
    TerminalTurnEventStreamProtocol,
    terminal_stdin_is_terminal,
)


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
        self._stdin_is_terminal = terminal_stdin_is_terminal(stdin)
        self._scroll_region = TerminalScrollRegionResetter(stdout)
        self._terminal_columns = TerminalColumnProvider()
        self._slash_command_views = TerminalSlashCommandViewDispatcher.for_runtime(app_runtime)
        self._idle_footer = TerminalIdleFooterTextProvider(self.app_runtime)
        self._status = TerminalStatusSurfaceWriter(
            stdout,
            stdin_is_terminal=lambda: self._stdin_is_terminal,
            layout_active=lambda: self._resize.layout_active,
            check_resize=lambda: self._resize.check_size_change(),
            repaint_footprint=lambda previous: self._resize.run_bottom_pane_footprint_reflow(
                previous=previous,
                current=self._status.live_status,
            ),
        )
        self._bottom_pane = TerminalBottomPaneController(
            stdout,
            stdin_is_terminal=lambda: self._stdin_is_terminal,
            layout_active=lambda: self._resize.layout_active,
            live_status=lambda: self._status.live_status,
            terminal_size=terminal_size,
            resize=lambda: self._resize.check_size_change(),
            footer_text=self._idle_footer.text,
            open_command_view=self._slash_command_views.open_command_view,
            on_selection_events=self._slash_command_views.handle_selection_events,
            repaint_footprint=lambda previous, current: self._resize.run_bottom_pane_frame_footprint_reflow(
                previous,
                current,
            ),
            cursor_visible=self._status.composer_cursor_visible,
        )
        self._status.bind_render_bottom_pane(self._bottom_pane.render)
        self._history = TerminalHistoryWriter(
            stdout,
            terminal_active=lambda: self._resize.terminal_layout_active,
            terminal_columns=self._terminal_columns.columns,
            check_resize=lambda: self._resize.check_size_change(),
            history_bottom_row=self._bottom_pane.history_bottom_row,
            clear_bottom_pane=self._bottom_pane.clear_without_resize_check,
            render_bottom_pane=self._bottom_pane.render_without_resize_check,
        )
        self._resize_history = TerminalResizeHistoryReplayer(
            stdout,
            history_state=lambda: self._history.state,
            history_wrap_width=lambda: self._history.wrap_width(),
            terminal_active=lambda: self._resize.terminal_layout_active,
            live_status_footprint_active=lambda: self._status.live_status.footprint_active,
            history_bottom_row=self._bottom_pane.history_bottom_row,
            terminal_columns=self._terminal_columns.columns,
            insert_replayed_history_lines=self._history.insert_replayed_lines,
            apply_history_state=self._history.apply_state,
            render_bottom_pane=self._bottom_pane.render_after_history_repaint,
        )
        self._resize = TerminalResizeCoordinator(
            terminal_active=lambda: self._stdin_is_terminal,
            current_size=terminal_size,
            active_stream=lambda: self._assistant_stream.active,
            reset_terminal_scroll_region=self._scroll_region.reset,
            render_bottom_pane=self._bottom_pane.render_without_resize_check,
            repaint_history_viewport=self._resize_history.repaint_viewport,
            replay_history_scrollback=self._resize_history.replay_scrollback,
            run_external_repaint=self._bottom_pane.run_external_repaint,
        )
        self._assistant_stream = TerminalAssistantStreamWriter(
            wrap_width=lambda: self._history.wrap_width(),
            open_stream=self._history.open_stream,
            write_delta=self._history.write_stream_delta,
            finish_projection=self._history.finish_stream_projection,
            apply_history_state=self._history.apply_state,
            finish_stream_reflow=self._resize.run_stream_finish_reflow,
            repaint_active_stream=self._resize_history.repaint_viewport,
        )
        self._user_prompt_output = TerminalUserPromptOutputWriter(
            terminal_active=self._resize.terminal_layout_active_state,
            clear_live_status=self._status.clear_live_status,
            write_history_cell=self._history.write_cell,
            render_bottom_pane=self._bottom_pane.render,
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
            hide_live_status=self._status.hide_live_status,
            clear_live_status=self._status.clear_live_status,
            finalize_active_stream=self._assistant_stream.finalize,
        )
        self._clear_ui = TerminalClearUiExecutor.for_terminal_runtime(
            app_runtime=self.app_runtime,
            writer=self.stdout,
            deactivate_layout=self._resize.deactivate_layout,
            apply_history_state=self._history.apply_state,
            apply_assistant_stream_state=self._assistant_stream.apply_state,
            apply_resize_pending=self._resize.apply_pending,
            write_history_cell=self._history.write_cell,
            activate_layout=self._resize.activate_layout,
        )
        self._status_card = TerminalStatusCardWriter(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
        )
        self._composer_effects = TerminalComposerEffectRunner(
            writer=self.stdout,
            clear_bottom_pane=self._bottom_pane.clear_without_resize_check,
        )
        self._composer_prompt = TerminalComposerPromptReader(
            terminal_active=lambda: self._resize.terminal_layout_active,
            get_input_source=self._input_source_provider.get,
            read_line=self.stdin.readline,
            write_nonterminal_prompt=self._composer_effects.write_nonterminal_prompt,
            apply_draft=self._bottom_pane.sync_draft,
            check_resize=self._resize.check_size_change,
            render=self._bottom_pane.render,
            clear_bottom_pane=self._bottom_pane.clear_without_resize_check,
            submit=self._composer_effects.submit,
            interrupt=self._composer_effects.interrupt,
            eof=self._composer_effects.eof,
            handle_key=self._bottom_pane.handle_composer_key,
        )
        self._turn_idle = TerminalTurnIdleTicker(
            check_resize=self._resize.check_size_change,
            refresh_turn_status=self._status.refresh_turn_status_if_due,
        )
        self._turn_events = TerminalTurnEventLoopRunner(
            on_event=self._protocol.handle_event,
            on_closed=self._protocol.close_turn,
            on_idle=self._turn_idle.tick,
            before_event=self._resize.check_size_change,
        )
        self._turn_submission = TerminalTurnSubmissionRunner(
            append_history=self.app_runtime.append_message_history_entry,
            apply_started_at=self._status.start_turn,
            reset_assistant_stream=self._assistant_stream.reset,
            clear_turn_status=self._status.clear_turn_status,
            render_turn_status=self._status.render_turn_status_force,
            submit_user_turn=self.app_runtime.submit_user_turn,
            consume_events=self._consume_events,
            close_turn=self._protocol.close_turn,
            write_error=self._history.write_cell,
            set_exit_code=self._set_exit_code,
        )
        self._local_commands = TerminalLocalCommandDispatcher(
            clear=self._clear_ui.run,
            help_=self._history.write_cell,
            status=self._status_card.run,
        )
        self._prompt_dispatch = TerminalPromptDispatcher(
            run_local_command=self._local_commands.run,
        )
        self._session_header = TerminalSessionHeaderWriter(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
            width=100,
        )
        self._startup_notices = TerminalStartupNoticesWriter(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
            write_blank_line=self._history.write,
        )

    def run(self) -> int:
        self._resize.activate_layout()
        self._session_header.write()
        self._startup_notices.write()
        while True:
            try:
                prompt = self._read_prompt()
            except (EOFError, KeyboardInterrupt):
                self._shutdown()
                return self.exit_code
            if prompt is None:
                self._shutdown()
                return self.exit_code
            prompt_dispatch = self._prompt_dispatch.dispatch(prompt)
            if prompt_dispatch.action == "exit":
                self._shutdown()
                return self.exit_code
            if prompt_dispatch.action != "submit":
                continue
            prompt = prompt_dispatch.prompt
            self._user_prompt_output.write(prompt)
            self._run_turn(prompt)

    def _read_prompt(self) -> str | None:
        return self._composer_prompt.read()

    def _run_turn(self, prompt: str) -> None:
        self._turn_submission.submit(prompt)

    def _set_exit_code(self, code: int) -> None:
        self.exit_code = int(code)

    def _consume_events(self, event_stream: TerminalTurnEventStreamProtocol) -> None:
        self._turn_events.consume(event_stream)

    def _shutdown(self) -> None:
        self._bottom_pane.restore_cursor()
        self._resize.deactivate_layout()
        try:
            self.app_runtime.shutdown_current_thread(timeout_seconds=1.0)
        except Exception:
            pass

__all__ = ["TerminalTuiRunner", "run_terminal_tui"]
