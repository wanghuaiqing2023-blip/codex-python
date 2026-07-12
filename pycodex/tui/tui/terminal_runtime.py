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

from collections import deque
import sys
from pathlib import Path
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
from ..app.event_dispatch import TerminalFullScreenApprovalController
from ..app.agent_message_consolidation import (
    TerminalAgentMessageConsolidator,
    TerminalTranscriptState,
)
from ..app_backtrack import TerminalTranscriptOverlayController
from ..bottom_pane.terminal_controller import (
    TerminalBottomPaneController,
)
from ..bottom_pane.chat_composer import (
    TerminalComposerEffectRunner,
    TerminalComposerPromptReader,
)
from ..bottom_pane.footer import TerminalIdleFooterTextProvider
from ..bottom_pane.approval_overlay import ApprovalViewProjector
from ..bottom_pane.request_user_input import RequestUserInputViewProjector
from ..bottom_pane.mcp_server_elicitation import McpServerElicitationViewProjector
from ..bottom_pane.app_link_view import AppLinkViewProjector
from ..chatwidget.protocol import (
    HistoryProjectionSink,
    TerminalProtocolEventDispatcher,
)
from ..chatwidget.rendering import active_history_cell_lines
from ..chatwidget.slash_dispatch import (
    TerminalLocalCommandDispatcher,
    TerminalPromptDispatcher,
    TerminalSlashCommandViewDispatcher,
)
from ..chatwidget.status_surfaces import (
    TerminalStatusSurfaceWriter,
)
from ..chatwidget.status_controls import TerminalStatusCommandController
from ..chatwidget.turn_runtime import TerminalTurnSubmissionRunner
from ..app_command import AppCommand
from ..app_event_sender import AppEventSender
from ..custom_terminal import (
    disable_bracketed_paste,
    enable_bracketed_paste,
    TerminalColumnProvider,
    TerminalScrollRegionResetter,
    terminal_size,
)
from ..keymap import RuntimeKeymap
from ..insert_history import (
    InsertHistoryMode,
    TerminalHistoryWriter,
)
from ..history_cell.messages import (
    TerminalUserPromptOutputWriter,
)
from ..chatwidget.streaming import TerminalChatWidgetStreamingRuntime
from ..history_cell.session import TerminalStartupNoticesWriter
from ..status.card import TerminalStatusCardWriter
from ..notifications import NotificationMethod, detect_backend
from .event_stream import (
    PrefixedTerminalInputSource,
    TerminalInputEvent,
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
        self._deferred_turn_input: deque[TerminalInputEvent] = deque()
        self._turn_input_eof_deferred = False
        self._stdin_is_terminal = terminal_stdin_is_terminal(stdin)
        self._stdout_is_terminal = terminal_stdin_is_terminal(stdout)
        self._scroll_region = TerminalScrollRegionResetter(stdout)
        self._desktop_notifications = detect_backend(
            NotificationMethod.AUTO,
            stream=stdout,
        )
        self._terminal_columns = TerminalColumnProvider()
        self._slash_command_views = TerminalSlashCommandViewDispatcher.for_runtime(
            app_runtime,
            submit_review=self._run_review_target,
        )
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
            set_terminal_title_requires_action=self._status.set_terminal_title_requires_action,
        )
        history_metadata = getattr(self.app_runtime.chat_widget, "bottom_history_metadata", None)
        history_lookup = getattr(self.app_runtime.active_thread_runtime, "lookup_message_history_entry", None)
        if history_metadata is not None:
            history_thread_id, history_log_id, history_entry_count = history_metadata
            self._bottom_pane._configure_history(
                history_thread_id,
                history_log_id,
                history_entry_count,
                (
                    lambda log_id, offset: history_lookup(history_thread_id, log_id, offset)
                    if callable(history_lookup)
                    else None
                ),
            )
        self._status.bind_render_bottom_pane(self._bottom_pane.render)
        self._transcript = TerminalTranscriptState()
        self._transcript_overlay = TerminalTranscriptOverlayController(
            cells=lambda: tuple(self._transcript.cells),
            get_input_source=self._input_source_provider.get,
            writer=self.stdout,
            terminal_size=terminal_size,
            keymap=self._pager_keymap,
            run_external_repaint=self._bottom_pane.run_external_repaint,
        )
        self._full_screen_approval = TerminalFullScreenApprovalController(
            get_input_source=self._input_source_provider.get,
            writer=self.stdout,
            terminal_size=terminal_size,
            keymap=self._pager_keymap,
            run_external_repaint=self._bottom_pane.run_external_repaint,
        )
        self._history = TerminalHistoryWriter(
            stdout,
            terminal_active=lambda: self._resize.terminal_layout_active,
            terminal_columns=self._terminal_columns.columns,
            check_resize=lambda: self._resize.check_size_change(),
            history_bottom_row=self._bottom_pane.history_bottom_row,
            clear_bottom_pane=self._bottom_pane.clear_without_resize_check,
            render_bottom_pane=self._bottom_pane.render_without_resize_check,
            append_transcript_cell=self._transcript.append,
            insert_mode=(
                InsertHistoryMode.ZELLIJ_RAW
                if self._stdout_is_terminal
                else InsertHistoryMode.STANDARD
            ),
            terminal_rows=lambda: terminal_size().lines,
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
            transcript_cells=lambda: tuple(self._transcript.cells),
        )
        self._resize = TerminalResizeCoordinator(
            terminal_active=lambda: self._stdin_is_terminal,
            current_size=terminal_size,
            active_stream=lambda: self._assistant_stream.active,
            reset_terminal_scroll_region=self._scroll_region.reset,
            render_bottom_pane=self._bottom_pane.render_without_resize_check,
            repaint_history_viewport=self._resize_history.repaint_viewport,
            repaint_history_viewport_for_footprint=self._resize_history.repaint_viewport_for_footprint,
            replay_history_scrollback=self._resize_history.replay_scrollback,
            run_external_repaint=self._bottom_pane.run_external_repaint,
            render_after_external_repaint=self._bottom_pane.render_after_history_repaint,
            on_width_change=lambda width: self._assistant_stream.set_width(width),
        )
        self._agent_message_consolidation = TerminalAgentMessageConsolidator(
            transcript=self._transcript,
            write_transient_cell=lambda cell: self._history.write_source_cell(
                cell,
                record_transcript=False,
            ),
            replace_projection_run=self._history.replace_projection_run,
            run_required_reflow=self._resize.run_required_stream_reflow,
            run_conditional_reflow=self._resize.run_conditional_stream_reflow,
        )
        self._assistant_stream = TerminalChatWidgetStreamingRuntime(
            width=lambda: self._history.wrap_width(),
            cwd=self._stream_cwd,
            insert_stable_cell=self._agent_message_consolidation.append_transient,
            consolidate_agent_message=self._agent_message_consolidation.consolidate,
            apply_live_tail=self._bottom_pane.sync_active_tail,
            render_frame=self._bottom_pane.render_without_resize_check,
        )
        self._user_prompt_output = TerminalUserPromptOutputWriter(
            terminal_active=self._resize.terminal_layout_active_state,
            clear_live_status=self._status.clear_live_status,
            write_history_cell=self._history.write_cell,
            render_bottom_pane=self._bottom_pane.render,
            write_source_cell=self._history.write_source_cell,
        )
        self._protocol = TerminalProtocolEventDispatcher(
            handle_notification=self.app_runtime.handle_notification,
            handle_request=self.app_runtime.handle_server_request,
            assistant_stream_active=lambda: self._assistant_stream.active,
            assistant_delta=self._assistant_stream.handle_delta,
            assistant_completed=self._assistant_stream.complete_message,
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
            reset_assistant_stream=self._reset_terminal_stream_state,
            apply_resize_pending=self._resize.apply_pending,
            write_history_cell=self._history.write_cell,
            activate_layout=self._resize.activate_layout,
        )
        self._status_card = TerminalStatusCardWriter(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
            terminal_columns=self._terminal_columns.columns,
            write_source_cell=self._history.write_source_cell,
        )
        self._status_command = TerminalStatusCommandController(
            self.app_runtime,
            self._status_card,
        )
        self._composer_effects = TerminalComposerEffectRunner(
            writer=self.stdout,
            clear_bottom_pane=self._bottom_pane.clear_without_resize_check,
        )
        self._composer_prompt = TerminalComposerPromptReader(
            terminal_active=lambda: self._resize.terminal_layout_active,
            get_input_source=self._get_composer_input_source,
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
            handle_global_key=self._handle_global_key,
            record_submission=self._bottom_pane._record_submission,
        )
        self._turn_idle = TerminalTurnIdleTicker(
            check_resize=self._resize.check_size_change,
            commit_stream=self._assistant_stream.commit_tick,
            refresh_turn_status=self._status.refresh_turn_status_if_due,
        )
        self._turn_events = TerminalTurnEventLoopRunner(
            on_event=self._protocol.handle_event,
            on_closed=self._protocol.close_turn,
            on_idle=self._turn_idle.tick,
            before_event=self._resize.check_size_change,
            poll_input=self._poll_turn_input,
            on_input=self._handle_turn_input,
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
            status=self._status_command.run,
        )
        self._prompt_dispatch = TerminalPromptDispatcher(
            run_local_command=self._local_commands.run,
            open_command_view=self._slash_command_views.open_command_view,
            open_command_with_args=self._slash_command_views.open_command_with_args,
        )
        self._session_header = TerminalSessionHeaderWriter(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
            width=100,
            write_source_cell=self._history.write_source_cell,
        )
        self._startup_notices = TerminalStartupNoticesWriter(
            self.app_runtime,
            write_history_cell=self._history.write_cell,
            write_blank_line=self._history.write,
        )
        self.app_runtime.bind_history_cell_sink(self._history.write_source_cell)
        self.app_runtime.bind_app_server_request_dismiss_sink(
            self._bottom_pane.dismiss_app_server_request
        )
        self.app_runtime.bind_full_screen_approval_sink(self._full_screen_approval)
        self.app_runtime.chat_widget.bind_history_projection(
            HistoryProjectionSink(
                insert_cell=self.app_runtime.insert_history_cell,
                set_active_cell=lambda cell: self._bottom_pane.sync_active_tail(
                    active_history_cell_lines(cell, self._history.wrap_width())
                ),
                request_redraw=self._bottom_pane.render_without_resize_check,
            )
        )
        bottom_pane_event_sender = AppEventSender(self.app_runtime.handle_bottom_pane_app_event)
        runtime_keymap = getattr(self.app_runtime, "runtime_keymap", None) or RuntimeKeymap.built_in_defaults()
        self.app_runtime.chat_widget.bind_approval_request_sink(
            ApprovalViewProjector(
                app_event_sender=bottom_pane_event_sender,
                show_view=self._bottom_pane.show_view,
                render=self._bottom_pane.render_without_resize_check,
                approval_keymap=runtime_keymap.approval,
                list_keymap=runtime_keymap.list,
            )
        )
        self.app_runtime.chat_widget.bind_pending_thread_approvals_sink(
            self._bottom_pane.sync_pending_thread_approvals
        )
        self.app_runtime.chat_widget.bind_interactive_request_sinks(
            user_input=RequestUserInputViewProjector(
                app_event_sender=bottom_pane_event_sender,
                show_view=self._bottom_pane.show_view,
                render=self._bottom_pane.render_without_resize_check,
            ),
            mcp_form=McpServerElicitationViewProjector(
                app_event_sender=bottom_pane_event_sender,
                show_view=self._bottom_pane.show_view,
                render=self._bottom_pane.render_without_resize_check,
            ),
            app_link=AppLinkViewProjector(
                app_event_sender=bottom_pane_event_sender,
                show_view=self._bottom_pane.show_view,
                render=self._bottom_pane.render_without_resize_check,
            ),
            resolve_elicitation=lambda server_name, request_id, decision: (
                bottom_pane_event_sender.resolve_elicitation(
                    self.app_runtime.chat_widget.tool_requests.thread_id,
                    server_name,
                    request_id,
                    decision,
                    None,
                    None,
                )
            ),
        )
        self.app_runtime.chat_widget.bind_tool_request_status_projection(
            set_status=lambda status: self._status.show_guardian_status(
                status.header,
                status.details,
            ),
            set_status_header=self._status.restore_turn_status,
        )
        self.app_runtime.chat_widget.bind_notification_projection(
            self._desktop_notifications.notify
        )

    def run(self) -> int:
        if self._stdin_is_terminal:
            enable_bracketed_paste(self.stdout)
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
                if prompt_dispatch.action == "show_view" and prompt_dispatch.view is not None:
                    self._bottom_pane._show_selection_view(prompt_dispatch.view)
                    self._bottom_pane.render()
                continue
            prompt = prompt_dispatch.prompt
            self._user_prompt_output.write(prompt)
            self._run_turn(prompt)

    def _read_prompt(self) -> str | None:
        return self._composer_prompt.read()

    def _get_composer_input_source(self) -> object | None:
        source = self._input_source_provider.get()
        if source is None:
            return None
        self._turn_input_eof_deferred = False
        return PrefixedTerminalInputSource(source, self._deferred_turn_input)

    def _handle_global_key(self, event_kind: str, event_text: str) -> bool:
        """Route Rust app-level shortcuts before composer key handling."""

        _ = event_text
        if event_kind != "ctrl_t":
            return False
        return self._transcript_overlay.open()

    def _pager_keymap(self) -> object:
        runtime_keymap = getattr(self.app_runtime, "runtime_keymap", None)
        if runtime_keymap is None:
            runtime_keymap = RuntimeKeymap.built_in_defaults()
        return runtime_keymap.pager

    def _run_turn(self, prompt: str) -> None:
        self._turn_submission.submit(prompt)

    def _stream_cwd(self) -> Path:
        config = getattr(self.app_runtime.active_thread_runtime, "session_config", None)
        return Path(getattr(config, "cwd", None) or Path.cwd())

    def _reset_terminal_stream_state(self) -> None:
        self._assistant_stream.reset()
        self._transcript.clear()

    def _run_review_target(self, target: object, summary: str) -> None:
        self._turn_submission.submit_operation(
            summary,
            lambda: self.app_runtime.submit_op(AppCommand.review(target)),
        )

    def _set_exit_code(self, code: int) -> None:
        self.exit_code = int(code)

    def _consume_events(self, event_stream: TerminalTurnEventStreamProtocol) -> None:
        self._turn_events.consume(event_stream)

    def _poll_turn_input(self, timeout: float) -> object | None:
        if self._turn_input_eof_deferred:
            return None
        source = self._input_source_provider.get()
        return None if source is None else source.poll(timeout)

    def _handle_turn_input(self, event: object) -> bool:
        if str(getattr(event, "kind", "")) == "resize":
            self._resize.check_size_change()
            return True
        if self._bottom_pane.has_active_view():
            return self._bottom_pane.handle_active_view_input(event)
        if str(getattr(event, "kind", "")) in {"interrupt", "ctrl_d"}:
            if self.app_runtime.maybe_return_from_side():
                return True
        if str(getattr(event, "kind", "")) in {"interrupt", "escape"}:
            self.app_runtime.submit_op(AppCommand.interrupt())
            return True
        if isinstance(event, TerminalInputEvent):
            self._deferred_turn_input.append(event)
            if event.kind == "eof":
                self._turn_input_eof_deferred = True
            return True
        return False

    def _shutdown(self) -> None:
        self._status.set_terminal_title_requires_action(False)
        if self._stdin_is_terminal:
            disable_bracketed_paste(self.stdout)
        self._bottom_pane.show_shutdown()
        self._bottom_pane.restore_cursor()
        self._resize.deactivate_layout()
        try:
            self.app_runtime.shutdown_current_thread(timeout_seconds=1.0)
        except Exception:
            pass

__all__ = ["TerminalTuiRunner", "run_terminal_tui"]
