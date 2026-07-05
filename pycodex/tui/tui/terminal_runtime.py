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

import sys
import time
from typing import Any, TextIO

from ..app.runtime import ActiveThreadRuntime, TuiAppRuntime
from ..app_event import AppEvent
from ..app.history_ui import (
    TerminalClearUiExecutor,
    run_terminal_session_header_from_runtime,
)
from ..app.resize_reflow import (
    TerminalResizeCoordinator,
    TerminalResizeHistoryReplayer,
)
from ..bottom_pane.terminal_surface import (
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
    ReasoningEffortConfig,
    ReasoningEffortPreset,
    open_all_models_popup,
    open_model_popup,
    open_plan_reasoning_scope_prompt,
    open_reasoning_popup,
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

    from ..textual_runtime import configure_app_runtime_thread_identity

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
            render_bottom_pane=lambda: self._bottom_pane.render(check_resize=False),
        )
        self._resize = TerminalResizeCoordinator(
            terminal_active=lambda: self._stdin_is_terminal,
            current_size=terminal_size,
            active_stream=lambda: self._assistant_stream.active,
            reset_terminal_scroll_region=lambda: reset_scroll_region(self.stdout),
            render_bottom_pane=lambda: self._bottom_pane.render(check_resize=False),
            repaint_history_viewport=self._resize_history.repaint_viewport,
            replay_history_scrollback=self._resize_history.replay_scrollback,
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
            repaint_active_stream=self._resize_history.repaint_viewport,
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
        current = _terminal_current_model(self.app_runtime)
        self._model_popup_context = ModelPopupContext(
            current_model=current,
            effective_reasoning_effort=_terminal_current_reasoning_effort(self.app_runtime),
        )
        self._model_popup_presets = _terminal_model_presets(self.app_runtime, current)
        result = open_model_popup(self._model_popup_context, self._model_popup_presets)
        for event in result.events:
            self._apply_model_popup_event(event)
        return result.view

    def _handle_model_popup_events(self, events: tuple[Any, ...]) -> Any:
        next_view = None
        for event in events:
            if isinstance(event, ModelPopupEvent):
                candidate = self._apply_model_popup_event(event)
                if candidate is not None:
                    next_view = candidate
        return next_view

    def _apply_model_popup_event(self, event: ModelPopupEvent) -> Any:
        context = self._model_popup_context
        if context is None:
            return None
        if event.kind == "update_model" and event.model is not None:
            self.app_runtime.handle_app_event(AppEvent.update_model(event.model))
            context.current_model = event.model
            return None
        if event.kind == "update_reasoning_effort":
            self.app_runtime.handle_app_event(AppEvent.update_reasoning_effort(event.effort))
            context.effective_reasoning_effort = event.effort
            return None
        if event.kind == "persist_model_selection" and event.model is not None:
            self.app_runtime.handle_app_event(AppEvent.persist_model_selection(event.model, event.effort))
            return None
        if event.kind == "open_all_models_popup":
            return open_all_models_popup(context, event.models).view
        if event.kind == "open_reasoning_popup" and event.model is not None:
            preset = next((candidate for candidate in self._model_popup_presets if candidate.model == event.model), None)
            if preset is None:
                return None
            result = open_reasoning_popup(context, preset)
            if result.view is not None:
                return result.view
            for followup in result.events:
                candidate = self._apply_model_popup_event(followup)
                if candidate is not None:
                    return candidate
            return None
        if event.kind == "open_plan_reasoning_scope_prompt" and event.model is not None:
            return open_plan_reasoning_scope_prompt(context, event.model, event.effort).view
        return None

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
        self._resize.deactivate_layout()
        try:
            self.app_runtime.shutdown_current_thread(timeout_seconds=1.0)
        except Exception:
            pass



__all__ = ["TerminalTuiRunner", "run_terminal_tui"]


def _terminal_current_model(app_runtime: TuiAppRuntime) -> str:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    value = (
        _terminal_runtime_value(session_config, "model")
        or _terminal_runtime_value(runtime, "model")
        or _terminal_runtime_value(app_runtime, "model")
    )
    return str(value or "gpt-5.5")


def _terminal_current_reasoning_effort(app_runtime: TuiAppRuntime) -> ReasoningEffortConfig | None:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    return _terminal_coerce_reasoning_effort(
        _terminal_runtime_value(session_config, "model_reasoning_effort")
        or _terminal_runtime_value(session_config, "reasoning_effort")
        or _terminal_runtime_value(runtime, "model_reasoning_effort")
    )


def _terminal_model_presets(app_runtime: TuiAppRuntime, current: str) -> tuple[ModelPreset, ...]:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    raw = _terminal_first_value(
        runtime,
        session_config,
        names=("available_models", "model_presets", "models"),
    )
    presets = tuple(_terminal_model_preset_from_runtime(item, current) for item in (raw or ()))
    visible = tuple(preset for preset in presets if preset.model)
    if visible:
        return visible

    managed = _terminal_model_manager_presets(app_runtime, current)
    if managed:
        return managed

    bundled = _terminal_bundled_model_popup_presets(current)
    if bundled:
        return bundled
    return (_terminal_fallback_current_model_preset(current),)


def _terminal_model_manager_presets(app_runtime: TuiAppRuntime, current: str) -> tuple[ModelPreset, ...]:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    session_config = getattr(runtime, "session_config", None)
    services = getattr(session_config, "services", None)
    for source in (
        runtime,
        getattr(services, "models_manager", None),
        getattr(session_config, "models_manager", None),
        getattr(app_runtime, "models_manager", None),
    ):
        if source is None:
            continue
        for method_name in ("list_models", "try_list_models"):
            method = getattr(source, method_name, None)
            if not callable(method):
                continue
            try:
                result = method("online_if_uncached") if method_name == "list_models" else method()
            except TypeError:
                try:
                    result = method()
                except Exception:
                    continue
            except Exception:
                continue
            presets = tuple(_terminal_model_preset_from_runtime(item, current) for item in (result or ()))
            visible = tuple(preset for preset in presets if preset.model)
            if visible:
                return visible
    return ()


def _terminal_bundled_model_popup_presets(current: str) -> tuple[ModelPreset, ...]:
    try:
        from pycodex.models_manager import bundled_models_response, model_presets_from_models
        from pycodex.protocol import ModelsResponse
    except Exception:
        return ()
    try:
        response = ModelsResponse.from_mapping(bundled_models_response())
        raw = model_presets_from_models(response.models)
    except Exception:
        return ()
    presets = tuple(_terminal_model_preset_from_runtime(item, current) for item in raw)
    return tuple(preset for preset in presets if preset.model)


def _terminal_fallback_current_model_preset(current: str) -> ModelPreset:
    effort = ReasoningEffortConfig.Medium
    return ModelPreset(
        model=current,
        default_reasoning_effort=effort,
        supported_reasoning_efforts=(ReasoningEffortPreset(effort, "Balanced reasoning for everyday tasks"),),
        is_default=True,
    )


def _terminal_model_preset_from_runtime(value: object, current_model: str) -> ModelPreset:
    if isinstance(value, str):
        effort = ReasoningEffortConfig.Medium
        return ModelPreset(
            model=value,
            default_reasoning_effort=effort,
            supported_reasoning_efforts=(ReasoningEffortPreset(effort),),
            is_default=value == current_model,
        )
    model = (
        _terminal_runtime_value(value, "model")
        or _terminal_runtime_value(value, "id")
        or _terminal_runtime_value(value, "name")
    )
    if model is None:
        return ModelPreset(model="")
    effort = _terminal_coerce_reasoning_effort(
        _terminal_runtime_value(value, "default_reasoning_effort")
        or _terminal_runtime_value(value, "reasoning_effort")
        or _terminal_runtime_value(value, "effort")
    ) or ReasoningEffortConfig.Medium
    supported = _terminal_coerce_supported_reasoning_efforts(
        _terminal_runtime_value(value, "supported_reasoning_efforts")
        or _terminal_runtime_value(value, "supported_efforts")
        or _terminal_runtime_value(value, "reasoning_efforts")
    )
    if not supported:
        supported = (ReasoningEffortPreset(effort),)
    return ModelPreset(
        model=str(model),
        description=str(_terminal_runtime_value(value, "description") or ""),
        default_reasoning_effort=effort,
        supported_reasoning_efforts=supported,
        is_default=bool(_terminal_runtime_value(value, "is_default")) or str(model) == current_model,
        show_in_picker=bool(_terminal_runtime_value(value, "show_in_picker", True)),
    )


def _terminal_first_value(*sources: object, names: tuple[str, ...]) -> object | None:
    for source in sources:
        if source is None:
            continue
        for name in names:
            value = _terminal_runtime_value(source, name, None)
            if value is not None:
                return value
    return None


def _terminal_runtime_value(source: object, name: str, default: object | None = None) -> object | None:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    value = getattr(source, name, default)
    return value() if callable(value) else value


def _terminal_coerce_reasoning_effort(value: object | None) -> ReasoningEffortConfig | None:
    if value is None:
        return None
    if isinstance(value, ReasoningEffortConfig):
        return value
    enum_value = getattr(value, "value", None)
    if enum_value is not None:
        value = enum_value
    normalized = str(value).strip().lower().replace("-", "_")
    if normalized == "none":
        return ReasoningEffortConfig.None_
    for effort in ReasoningEffortConfig:
        if effort.value == normalized:
            return effort
    return None


def _terminal_coerce_supported_reasoning_efforts(value: object | None) -> tuple[ReasoningEffortPreset, ...]:
    if not value:
        return ()
    out: list[ReasoningEffortPreset] = []
    for item in value if isinstance(value, (list, tuple)) else (value,):
        effort = _terminal_coerce_reasoning_effort(_terminal_runtime_value(item, "effort", item))
        if effort is None:
            continue
        description = str(_terminal_runtime_value(item, "description") or "")
        out.append(ReasoningEffortPreset(effort, description))
    return tuple(out)
