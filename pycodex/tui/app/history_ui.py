"""Terminal history and clear-screen UI helpers for the TUI app.

Rust counterpart: ``codex-rs/tui/src/app/history_ui.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from .._porting import RustTuiModule
from ..history_cell.messages import TerminalAssistantStreamState
from ..history_cell.session import SessionHeaderHistoryCell, line_text
from ..insert_history import TerminalHistoryState
from ..ratatui_bridge import Rect
from ..transcript_reflow import TranscriptReflowState


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::history_ui",
    source="codex/codex-rs/tui/src/app/history_ui.rs",
    status="complete",
)

CODEX_CLI_VERSION = "unknown"


@dataclass(frozen=True)
class SessionHeaderLine:
    text: str
    kind: str = "session_header"


@dataclass(frozen=True)
class TerminalSessionHeaderData:
    model: str
    reasoning_effort: Any | None
    show_fast_status: bool
    directory: Path
    version: str
    yolo_mode: bool = False


@dataclass
class ChatWidget:
    model: str = "gpt-5"
    reasoning_effort: Optional[str] = None
    service_tier: Optional[str] = None
    fast_status: bool = False
    errors: List[str] = field(default_factory=list)
    infos: List[Tuple[str, Optional[Any]]] = field(default_factory=list)
    wrap_width: Optional[int] = None

    def current_model(self) -> str:
        return self.model

    def current_reasoning_effort(self) -> Optional[str]:
        return self.reasoning_effort

    def current_service_tier(self) -> Optional[str]:
        return self.service_tier

    def should_show_fast_status(self, model: str, service_tier: Optional[str]) -> bool:
        return self.fast_status

    def history_wrap_width(self, screen_width: int) -> int:
        return self.wrap_width if self.wrap_width is not None else int(screen_width)

    def add_error_message(self, message: str) -> None:
        self.errors.append(message)

    def add_info_message(self, message: str, hint: Optional[Any] = None) -> None:
        self.infos.append((message, hint))


@dataclass
class Config:
    cwd: Path = field(default_factory=lambda: Path("."))
    yolo_mode: bool = False


@dataclass
class ScreenSize:
    width: int = 80
    height: int = 24


@dataclass
class Terminal:
    last_known_screen_size: ScreenSize = field(default_factory=ScreenSize)
    viewport_area: Rect = field(default_factory=Rect)
    visible_clears: int = 0
    scrollback_and_visible_ansi_clears: int = 0
    viewport_history: List[Rect] = field(default_factory=list)

    def clear_visible_screen(self) -> None:
        self.visible_clears += 1

    def clear_scrollback_and_visible_screen_ansi(self) -> None:
        self.scrollback_and_visible_ansi_clears += 1

    def set_viewport_area(self, area: Rect) -> None:
        self.viewport_area = area
        self.viewport_history.append(area)


@dataclass
class Tui:
    terminal: Terminal = field(default_factory=Terminal)
    alt_screen_active: bool = False
    pending_history_clears: int = 0
    inserted_history_lines: List[List[SessionHeaderLine]] = field(default_factory=list)

    def is_alt_screen_active(self) -> bool:
        return self.alt_screen_active

    def clear_pending_history_lines(self) -> None:
        self.pending_history_clears += 1

    def insert_history_lines(self, lines: List[SessionHeaderLine]) -> None:
        self.inserted_history_lines.append(lines)


@dataclass
class AppHistoryUiState:
    chat_widget: ChatWidget = field(default_factory=ChatWidget)
    config: Config = field(default_factory=Config)
    overlay: Optional[Any] = None
    transcript_cells: List[Any] = field(default_factory=list)
    deferred_history_lines: List[Any] = field(default_factory=list)
    has_emitted_history_lines: bool = False
    transcript_reflow: TranscriptReflowState = field(default_factory=TranscriptReflowState)
    initial_history_replay_buffer: Optional[Any] = None
    backtrack: Any = field(default_factory=dict)
    backtrack_render_pending: bool = False

    def open_url_in_browser(
        self,
        url: str,
        opener: Optional[Callable[[str], Any]] = None,
    ) -> bool:
        return open_url_in_browser(self, url, opener)

    def clear_ui_header_lines_with_version(
        self,
        width: int,
        version: str,
    ) -> List[SessionHeaderLine]:
        return clear_ui_header_lines_with_version(self, width, version)

    def clear_ui_header_lines(self, width: int) -> List[SessionHeaderLine]:
        return self.clear_ui_header_lines_with_version(width, CODEX_CLI_VERSION)

    def queue_clear_ui_header(self, tui: Tui) -> List[SessionHeaderLine]:
        return queue_clear_ui_header(self, tui)

    def clear_terminal_ui(self, tui: Tui, redraw_header: bool) -> None:
        clear_terminal_ui(self, tui, redraw_header)

    def reset_app_ui_state_after_clear(self) -> None:
        self.reset_transcript_state_after_clear()

    def reset_transcript_state_after_clear(self) -> None:
        reset_transcript_state_after_clear(self)


@dataclass(frozen=True)
class TerminalClearState:
    history_has_content: bool = False
    history_ended_with_blank: bool = False
    history_projection_cells: Tuple[str, ...] = ()
    assistant_stream_text: str = ""
    resize_reflow_pending: bool = False


@dataclass(frozen=True)
class TerminalClearApplicationState:
    """Concrete terminal scrollback state after applying app clear semantics."""

    history_state: TerminalHistoryState
    assistant_stream: TerminalAssistantStreamState
    resize_reflow_pending: bool


@dataclass
class TerminalClearUiExecutor:
    """Stateful clear-UI adapter for the terminal scrollback product path.

    Rust ``app::history_ui`` owns the reset semantics for ``/clear``.  The
    terminal runner supplies concrete terminal and state-sink callbacks, while
    this adapter keeps their ordering with the app/history-ui boundary.
    """

    deactivate_layout: Callable[[], Any]
    clear_terminal: Callable[[], Any]
    flush_terminal: Callable[[], Any]
    apply_history_state: Callable[[TerminalHistoryState], Any]
    apply_assistant_stream_state: Callable[[TerminalAssistantStreamState], Any]
    apply_resize_pending: Callable[[bool], Any]
    render_header: Callable[[], Any]
    activate_layout: Callable[[], Any]

    def run(self) -> TerminalClearState:
        return run_terminal_clear_ui_effects(
            deactivate_layout=self.deactivate_layout,
            clear_terminal=self.clear_terminal,
            flush_terminal=self.flush_terminal,
            apply_clear_state=lambda state: run_terminal_clear_application_state(
                state,
                apply_history_state=self.apply_history_state,
                apply_assistant_stream_state=self.apply_assistant_stream_state,
                apply_resize_pending=self.apply_resize_pending,
            ),
            render_header=self.render_header,
            activate_layout=self.activate_layout,
        )


def open_url_in_browser(
    app: AppHistoryUiState,
    url: str,
    opener: Optional[Callable[[str], Any]] = None,
) -> bool:
    opener = opener or (lambda _: True)
    try:
        opener(url)
    except Exception as err:  # mirrors Rust error-to-chat-message boundary
        app.chat_widget.add_error_message(f"Failed to open browser for {url}: {err}")
        return False

    app.chat_widget.add_info_message(f"Opened {url} in your browser.", None)
    return True


def clear_ui_header_lines_with_version(
    app: AppHistoryUiState,
    width: int,
    version: str,
) -> List[SessionHeaderLine]:
    model = app.chat_widget.current_model()
    return [
        SessionHeaderLine(text)
        for text in terminal_session_header_lines(
            TerminalSessionHeaderData(
                model=model,
                reasoning_effort=app.chat_widget.current_reasoning_effort(),
                show_fast_status=app.chat_widget.should_show_fast_status(
                    model,
                    app.chat_widget.current_service_tier(),
                ),
                directory=app.config.cwd,
                version=version,
                yolo_mode=app.config.yolo_mode,
            ),
            width,
        )
    ]


def terminal_session_header_lines(
    data: TerminalSessionHeaderData,
    width: int,
) -> Tuple[str, ...]:
    """Return the text lines for the scrollback session header.

    Rust ownership: ``codex-tui::app::history_ui`` builds the fresh session
    header by delegating to ``history_cell::session::SessionHeaderHistoryCell``.
    """

    if int(width) <= 0:
        return ()
    cell = SessionHeaderHistoryCell.new(
        data.model,
        data.reasoning_effort,
        data.show_fast_status,
        data.directory,
        data.version,
    ).with_yolo_mode(data.yolo_mode)
    return tuple(line_text(line) for line in cell.display_lines(int(width)))


def terminal_session_header_text(
    data: TerminalSessionHeaderData,
    width: int,
) -> str:
    return "\n".join(terminal_session_header_lines(data, width))


def terminal_session_header_data_from_runtime(
    app_runtime: Any,
    *,
    display_version: Callable[[], str],
    display_model: Callable[[Any], str],
    reasoning_effort: Callable[[Any], Any | None],
    show_fast_status: Callable[[Any], bool],
    yolo_mode: Callable[[Any], bool],
) -> TerminalSessionHeaderData:
    """Build terminal session header data from the app runtime.

    Rust ownership: ``app::history_ui`` gathers current App/chat-widget state
    and delegates display to ``history_cell::session::SessionHeaderHistoryCell``.
    """

    return TerminalSessionHeaderData(
        model=display_model(app_runtime),
        reasoning_effort=reasoning_effort(app_runtime),
        show_fast_status=show_fast_status(app_runtime),
        directory=getattr(app_runtime, "cwd"),
        version=display_version(),
        yolo_mode=yolo_mode(app_runtime),
    )


def run_terminal_session_header_render(
    app_runtime: Any,
    *,
    display_version: Callable[[], str],
    display_model: Callable[[Any], str],
    reasoning_effort: Callable[[Any], Any | None],
    show_fast_status: Callable[[Any], bool],
    yolo_mode: Callable[[Any], bool],
    write_history_cell: Callable[[str], Any],
    width: int,
) -> TerminalSessionHeaderData:
    """Render the startup session header into terminal scrollback history."""

    data = terminal_session_header_data_from_runtime(
        app_runtime,
        display_version=display_version,
        display_model=display_model,
        reasoning_effort=reasoning_effort,
        show_fast_status=show_fast_status,
        yolo_mode=yolo_mode,
    )
    write_history_cell(terminal_session_header_text(data, width))
    return data


def run_terminal_session_header_from_runtime(
    app_runtime: Any,
    *,
    write_history_cell: Callable[[str], Any],
    width: int,
) -> TerminalSessionHeaderData:
    """Render the session header using the canonical runtime providers."""

    from ..textual_runtime import (
        _display_version,
        _runtime_display_model,
        _runtime_header_reasoning_effort,
        _runtime_header_yolo_mode,
        _runtime_show_fast_status,
    )

    return run_terminal_session_header_render(
        app_runtime,
        display_version=_display_version,
        display_model=_runtime_display_model,
        reasoning_effort=_runtime_header_reasoning_effort,
        show_fast_status=_runtime_show_fast_status,
        yolo_mode=_runtime_header_yolo_mode,
        write_history_cell=write_history_cell,
        width=width,
    )


def queue_clear_ui_header(app: AppHistoryUiState, tui: Tui) -> List[SessionHeaderLine]:
    width = app.chat_widget.history_wrap_width(tui.terminal.last_known_screen_size.width)
    header_lines = app.clear_ui_header_lines(width)
    if header_lines:
        tui.insert_history_lines(header_lines)
        app.has_emitted_history_lines = True
    return header_lines


def clear_terminal_ui(app: AppHistoryUiState, tui: Tui, redraw_header: bool) -> None:
    is_alt_screen_active = tui.is_alt_screen_active()
    tui.clear_pending_history_lines()

    if is_alt_screen_active:
        tui.terminal.clear_visible_screen()
    else:
        tui.terminal.clear_scrollback_and_visible_screen_ansi()

    area = tui.terminal.viewport_area
    if area.y > 0:
        tui.terminal.set_viewport_area(
            Rect(x=area.x, y=0, width=area.width, height=area.height)
        )

    app.has_emitted_history_lines = False
    if redraw_header:
        app.queue_clear_ui_header(tui)


def reset_transcript_state_after_clear(app: AppHistoryUiState) -> None:
    app.overlay = None
    app.transcript_cells.clear()
    app.deferred_history_lines.clear()
    app.has_emitted_history_lines = False
    app.transcript_reflow.clear()
    app.initial_history_replay_buffer = None
    app.backtrack = {}
    app.backtrack_render_pending = False


def terminal_clear_state_after_clear() -> TerminalClearState:
    """Return the lightweight terminal runner state after ``/clear``."""

    return TerminalClearState()


def terminal_clear_application_state(state: TerminalClearState) -> TerminalClearApplicationState:
    """Map app clear semantics onto the terminal scrollback product state.

    Rust ``app::history_ui`` owns the transcript/UI reset performed by ``/clear``
    and Ctrl-L.  The lightweight terminal runner stores Python-specific state
    objects, but this module owns how the clear contract resets those objects.
    """

    return TerminalClearApplicationState(
        history_state=TerminalHistoryState(
            history_has_content=state.history_has_content,
            history_ended_with_blank=state.history_ended_with_blank,
            projection_cells=tuple(state.history_projection_cells),
        ),
        assistant_stream=TerminalAssistantStreamState.inactive(state.assistant_stream_text),
        resize_reflow_pending=state.resize_reflow_pending,
    )


def run_terminal_clear_application_state(
    state: TerminalClearState,
    *,
    apply_history_state: Callable[[TerminalHistoryState], Any],
    apply_assistant_stream_state: Callable[[TerminalAssistantStreamState], Any],
    apply_resize_pending: Callable[[bool], Any],
) -> TerminalClearApplicationState:
    """Apply terminal scrollback state reset through app-owned clear semantics."""

    applied = terminal_clear_application_state(state)
    apply_history_state(applied.history_state)
    apply_assistant_stream_state(applied.assistant_stream)
    apply_resize_pending(applied.resize_reflow_pending)
    return applied


def run_terminal_clear_ui_effects(
    *,
    deactivate_layout: Callable[[], Any],
    clear_terminal: Callable[[], Any],
    flush_terminal: Callable[[], Any],
    apply_clear_state: Callable[[TerminalClearState], Any],
    render_header: Callable[[], Any],
    activate_layout: Callable[[], Any],
) -> TerminalClearState:
    """Execute the terminal scrollback product path's clear UI sequence."""

    deactivate_layout()
    clear_terminal()
    flush_terminal()
    state = terminal_clear_state_after_clear()
    apply_clear_state(state)
    render_header()
    activate_layout()
    return state


def open_url_success_and_failure_messages() -> bool:
    app = AppHistoryUiState()
    ok = app.open_url_in_browser("https://example.com", lambda _: True)

    def fail(_: str) -> None:
        raise RuntimeError("no browser")

    failed = app.open_url_in_browser("https://bad.example", fail)
    return (
        ok
        and not failed
        and app.chat_widget.infos == [("Opened https://example.com in your browser.", None)]
        and app.chat_widget.errors == [
            "Failed to open browser for https://bad.example: no browser"
        ]
    )


def clear_terminal_ui_alt_and_inline_branches() -> bool:
    app = AppHistoryUiState()
    inline_tui = Tui(
        terminal=Terminal(
            last_known_screen_size=ScreenSize(width=80, height=24),
            viewport_area=Rect(x=0, y=4, width=80, height=20),
        )
    )
    clear_terminal_ui(app, inline_tui, redraw_header=True)

    alt_tui = Tui(terminal=Terminal(), alt_screen_active=True)
    clear_terminal_ui(app, alt_tui, redraw_header=False)
    return (
        inline_tui.pending_history_clears == 1
        and inline_tui.terminal.scrollback_and_visible_ansi_clears == 1
        and inline_tui.terminal.viewport_area.y == 0
        and len(inline_tui.inserted_history_lines) == 1
        and alt_tui.terminal.visible_clears == 1
        and alt_tui.inserted_history_lines == []
    )


def reset_transcript_state_after_clear_resets_owned_state() -> bool:
    app = AppHistoryUiState(
        overlay=object(),
        transcript_cells=[object()],
        deferred_history_lines=[object()],
        has_emitted_history_lines=True,
        initial_history_replay_buffer=[object()],
        backtrack={"selection": object()},
        backtrack_render_pending=True,
    )
    app.transcript_reflow.note_width(80)
    app.transcript_reflow.schedule_debounced(100)

    reset_transcript_state_after_clear(app)
    return (
        app.overlay is None
        and app.transcript_cells == []
        and app.deferred_history_lines == []
        and not app.has_emitted_history_lines
        and app.transcript_reflow.last_observed_width is None
        and app.initial_history_replay_buffer is None
        and app.backtrack == {}
        and not app.backtrack_render_pending
    )


__all__ = [
    "AppHistoryUiState",
    "CODEX_CLI_VERSION",
    "ChatWidget",
    "Config",
    "RUST_MODULE",
    "Rect",
    "ScreenSize",
    "SessionHeaderLine",
    "Terminal",
    "TerminalClearApplicationState",
    "TerminalClearState",
    "TerminalClearUiExecutor",
    "TerminalSessionHeaderData",
    "Tui",
    "clear_terminal_ui",
    "clear_terminal_ui_alt_and_inline_branches",
    "clear_ui_header_lines_with_version",
    "open_url_in_browser",
    "open_url_success_and_failure_messages",
    "queue_clear_ui_header",
    "reset_transcript_state_after_clear",
    "reset_transcript_state_after_clear_resets_owned_state",
    "run_terminal_clear_application_state",
    "run_terminal_clear_ui_effects",
    "run_terminal_session_header_from_runtime",
    "run_terminal_session_header_render",
    "terminal_clear_application_state",
    "terminal_clear_state_after_clear",
    "terminal_session_header_data_from_runtime",
    "terminal_session_header_lines",
    "terminal_session_header_text",
]
