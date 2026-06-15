"""Terminal history and clear-screen UI helpers for the TUI app.

Rust counterpart: ``codex-rs/tui/src/app/history_ui.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

from .._porting import RustTuiModule
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
    if int(width) <= 0:
        return []

    parts = [
        f"Codex {version}",
        f"model: {app.chat_widget.current_model()}",
        f"cwd: {_display_cwd(app.config.cwd)}",
    ]
    effort = app.chat_widget.current_reasoning_effort()
    if effort is not None:
        parts.append(f"effort: {effort}")
    if app.chat_widget.should_show_fast_status(
        app.chat_widget.current_model(),
        app.chat_widget.current_service_tier(),
    ):
        parts.append("fast")
    if app.config.yolo_mode:
        parts.append("yolo")

    line = " | ".join(parts)
    return [SessionHeaderLine(line[: max(0, int(width))])]


def _display_cwd(cwd: Path) -> str:
    return str(cwd).replace("\\", "/")


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
    "Tui",
    "clear_terminal_ui",
    "clear_terminal_ui_alt_and_inline_branches",
    "clear_ui_header_lines_with_version",
    "open_url_in_browser",
    "open_url_success_and_failure_messages",
    "queue_clear_ui_header",
    "reset_transcript_state_after_clear",
    "reset_transcript_state_after_clear_resets_owned_state",
]
