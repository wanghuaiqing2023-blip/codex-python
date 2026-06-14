"""Suspend/resume job-control helpers for the TUI.

Rust counterpart: ``codex-rs/tui/src/tui/job_control.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .._porting import RustTuiModule
from ..ratatui_bridge import Rect


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="tui::job_control",
    source="codex/codex-rs/tui/src/tui/job_control.rs",
    status="complete_slice",
)

SUSPEND_KEY = "Ctrl+Z"


@dataclass(frozen=True)
class Position:
    x: int = 0
    y: int = 0


@dataclass
class Terminal:
    last_known_cursor_pos: Position = field(default_factory=Position)
    cursor_position: Position | None = None
    viewport_area: Rect = field(default_factory=Rect)
    size_width: int = 80
    size_height: int = 24
    entered_alt_screen: int = 0
    enabled_alt_scroll: int = 0
    cleared: int = 0
    viewport_history: list[Rect] = field(default_factory=list)

    def get_cursor_position(self) -> Position:
        if self.cursor_position is None:
            raise RuntimeError("cursor position unavailable")
        return self.cursor_position

    def set_viewport_area(self, area: Rect) -> None:
        self.viewport_area = area
        self.viewport_history.append(area)

    def size(self) -> tuple[int, int]:
        return self.size_width, self.size_height

    def clear(self) -> None:
        self.cleared += 1


class ResumeAction(Enum):
    RealignInline = "RealignInline"
    RestoreAlt = "RestoreAlt"


@dataclass(frozen=True)
class PreparedResumeAction:
    kind: str
    area: Rect | None = None

    @classmethod
    def RestoreAltScreen(cls) -> "PreparedResumeAction":
        return cls("RestoreAltScreen")

    @classmethod
    def RealignViewport(cls, area: Rect) -> "PreparedResumeAction":
        return cls("RealignViewport", area=area)

    def apply(self, terminal: Terminal) -> None:
        if self.kind == "RealignViewport":
            if self.area is None:
                raise ValueError("RealignViewport requires an area")
            terminal.set_viewport_area(self.area)
            return
        if self.kind == "RestoreAltScreen":
            terminal.entered_alt_screen += 1
            terminal.enabled_alt_scroll += 1
            width, height = terminal.size()
            terminal.set_viewport_area(Rect(0, 0, width, height))
            terminal.clear()
            return
        raise ValueError(f"unknown prepared resume action: {self.kind!r}")


@dataclass
class SuspendProcessTrace:
    restored: int = 0
    stderr_paused: int = 0
    sigtstp_sent: int = 0
    stderr_resumed: int = 0
    modes_set: int = 0


@dataclass
class SuspendContext:
    resume_pending: ResumeAction | None = None
    suspend_cursor_y: int = 0
    suspend_trace: SuspendProcessTrace = field(default_factory=SuspendProcessTrace)
    terminal_commands: list[Any] = field(default_factory=list)

    @classmethod
    def new(cls) -> "SuspendContext":
        return cls()

    def suspend(self, alt_screen_active: bool) -> None:
        if alt_screen_active:
            self.terminal_commands.extend(["DisableAlternateScroll", "LeaveAlternateScreen"])
            self.set_resume_action(ResumeAction.RestoreAlt)
        else:
            self.set_resume_action(ResumeAction.RealignInline)
        self.terminal_commands.extend([("MoveTo", 0, self.suspend_cursor_y), "Show"])
        suspend_process(self.suspend_trace)

    def prepare_resume_action(
        self,
        terminal: Terminal,
        alt_saved_viewport: Rect | None = None,
    ) -> PreparedResumeAction | None:
        action = self.take_resume_action()
        if action is None:
            return None
        if action is ResumeAction.RealignInline:
            try:
                cursor_pos = terminal.get_cursor_position()
            except RuntimeError:
                cursor_pos = terminal.last_known_cursor_pos
            return PreparedResumeAction.RealignViewport(Rect(0, cursor_pos.y, 0, 0))
        if action is ResumeAction.RestoreAlt:
            if alt_saved_viewport is not None:
                try:
                    pos = terminal.get_cursor_position()
                    object.__setattr__(alt_saved_viewport, "y", pos.y)
                except RuntimeError:
                    pass
            return PreparedResumeAction.RestoreAltScreen()
        raise ValueError(f"unknown resume action: {action!r}")

    def set_cursor_y(self, value: int) -> None:
        self.suspend_cursor_y = int(value) & 0xFFFF

    def set_resume_action(self, value: ResumeAction) -> None:
        self.resume_pending = value

    def take_resume_action(self) -> ResumeAction | None:
        action = self.resume_pending
        self.resume_pending = None
        return action


def suspend_process(trace: SuspendProcessTrace | None = None) -> SuspendProcessTrace:
    trace = trace or SuspendProcessTrace()
    trace.restored += 1
    trace.stderr_paused += 1
    trace.sigtstp_sent += 1
    trace.stderr_resumed += 1
    trace.modes_set += 1
    return trace


def suspend_sets_restore_alt_for_alt_screen() -> bool:
    ctx = SuspendContext.new()
    ctx.set_cursor_y(7)
    ctx.suspend(True)
    return (
        ctx.resume_pending is ResumeAction.RestoreAlt
        and ctx.terminal_commands == [
            "DisableAlternateScroll",
            "LeaveAlternateScreen",
            ("MoveTo", 0, 7),
            "Show",
        ]
        and ctx.suspend_trace.sigtstp_sent == 1
    )


def suspend_sets_realign_inline_for_inline_screen() -> bool:
    ctx = SuspendContext.new()
    ctx.set_cursor_y(3)
    ctx.suspend(False)
    return (
        ctx.resume_pending is ResumeAction.RealignInline
        and ctx.terminal_commands == [("MoveTo", 0, 3), "Show"]
    )


def prepare_resume_action_consumes_realign_inline() -> bool:
    ctx = SuspendContext.new()
    terminal = Terminal(cursor_position=Position(2, 12))
    ctx.set_resume_action(ResumeAction.RealignInline)
    first = ctx.prepare_resume_action(terminal)
    second = ctx.prepare_resume_action(terminal)
    return first == PreparedResumeAction.RealignViewport(Rect(0, 12, 0, 0)) and second is None


def prepare_resume_action_restores_alt_and_updates_saved_viewport() -> bool:
    ctx = SuspendContext.new()
    saved = Rect(0, 2, 80, 20)
    terminal = Terminal(cursor_position=Position(0, 5))
    ctx.set_resume_action(ResumeAction.RestoreAlt)
    action = ctx.prepare_resume_action(terminal, saved)
    return action == PreparedResumeAction.RestoreAltScreen() and saved.y == 5


__all__ = [
    "Position",
    "PreparedResumeAction",
    "RUST_MODULE",
    "Rect",
    "ResumeAction",
    "SUSPEND_KEY",
    "SuspendContext",
    "SuspendProcessTrace",
    "Terminal",
    "prepare_resume_action_consumes_realign_inline",
    "prepare_resume_action_restores_alt_and_updates_saved_viewport",
    "suspend_process",
    "suspend_sets_realign_inline_for_inline_screen",
    "suspend_sets_restore_alt_for_alt_screen",
]
