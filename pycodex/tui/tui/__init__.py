"""Semantic Python port for Rust ``codex-tui::tui``.

Upstream source: ``codex/codex-rs/tui/src/tui.rs``.

This module mirrors the Rust TUI runtime boundary with semantic Python models. The
actual terminal side effects remain represented as operations on ``SemanticTerminal``
so tests and callers can validate state transitions without depending on crossterm or
ratatui concrete types.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, List, Optional

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="tui",
    source="codex/codex-rs/tui/src/tui.rs",
    status="complete",
)

TARGET_FRAME_INTERVAL: float = 1.0 / 30.0


class NotificationCondition(Enum):
    """Semantic mirror for ``codex_config::types::NotificationCondition``."""

    UNFOCUSED = "unfocused"
    ALWAYS = "always"


@dataclass(frozen=True)
class Position:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int

    def top(self) -> int:
        return self.y

    def bottom(self) -> int:
        return self.y + self.height

    def as_position(self) -> Position:
        return Position(self.x, self.y)

    def is_empty(self) -> bool:
        return self.width == 0 or self.height == 0

    def offset(self, dx: int, dy: int) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.width, self.height)


@dataclass
class FrameRequester:
    scheduled: List[Optional[float]] = field(default_factory=list)

    def schedule_frame(self) -> None:
        self.scheduled.append(None)

    def schedule_frame_in(self, delay: float) -> None:
        self.scheduled.append(delay)


@dataclass
class PendingHistoryLines:
    """Python boundary for Rust ``tui::PendingHistoryLines``."""

    lines: List[Any] = field(default_factory=list)
    wrap_policy: str = "PreWrap"


@dataclass
class SemanticTerminal:
    """Small terminal model for Rust TUI state transitions.

    Rust returns and mutates crossterm/ratatui terminal values. Python keeps the
    same semantic contract with explicit viewport, cursor, draw, and operation
    records instead of copying framework concrete types.
    """

    width: int = 80
    height: int = 24
    viewport_area: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))
    last_known_screen_size: Rect = field(default_factory=lambda: Rect(0, 0, 80, 24))
    last_known_cursor_pos: Position = field(default_factory=lambda: Position(0, 0))
    cursor_position: Position = field(default_factory=lambda: Position(0, 0))
    operations: List[Any] = field(default_factory=list)
    drawn_frames: List[Any] = field(default_factory=list)
    enhanced_keys_supported: bool = False

    def size(self) -> Rect:
        return Rect(0, 0, self.width, self.height)

    def set_viewport_area(self, area: Rect) -> None:
        self.viewport_area = area
        self.operations.append(("set_viewport_area", area))

    def clear(self) -> None:
        self.operations.append("clear")

    def clear_after_position(self, position: Position) -> None:
        self.operations.append(("clear_after_position", position))

    def invalidate_viewport(self) -> None:
        self.operations.append("invalidate_viewport")

    def scroll_region_up(self, *args: Any) -> None:
        self.operations.append(("scroll_region_up", args))

    def get_cursor_position(self) -> Position:
        return self.cursor_position

    def draw(self, draw_fn: Callable[[Any], Any]) -> Any:
        result = draw_fn(self)
        self.drawn_frames.append(result)
        return result


Terminal: Any = SemanticTerminal


@dataclass
class InitializedTerminal:
    """Python boundary for Rust ``tui::InitializedTerminal``."""

    terminal: Any
    enhanced_keys_supported: bool = False
    stderr_guard: Any = None


def running_in_vscode_terminal(env: Optional[dict] = None) -> bool:
    import os

    values = os.environ if env is None else env
    return values.get("TERM_PROGRAM") == "vscode" or "VSCODE_INJECTION" in values


def should_emit_notification(condition: Any, terminal_focused: bool) -> bool:
    """Return whether a desktop notification should be emitted.

    Rust behavior:
    - ``Unfocused`` emits only when the terminal is not focused.
    - ``Always`` emits regardless of terminal focus.
    """

    condition = _coerce_notification_condition(condition)
    terminal_focused = bool(terminal_focused)
    if condition is NotificationCondition.UNFOCUSED:
        return not terminal_focused
    if condition is NotificationCondition.ALWAYS:
        return True
    raise AssertionError("unhandled notification condition: {!r}".format(condition))


def drop(tui: Any) -> None:
    clear = getattr(tui, "clear_ambient_pet_image", None)
    if clear is None:
        return
    try:
        clear()
    except Exception:
        pass


def unfocused_notification_condition_is_suppressed_when_focused() -> None:
    assert not should_emit_notification(NotificationCondition.UNFOCUSED, True)


def always_notification_condition_emits_when_focused() -> None:
    assert should_emit_notification(NotificationCondition.ALWAYS, True)


def unfocused_notification_condition_emits_when_unfocused() -> None:
    assert should_emit_notification(NotificationCondition.UNFOCUSED, False)


def first_viewport_change_clears_from_new_viewport_when_old_viewport_is_empty() -> None:
    terminal = SemanticTerminal()
    new_area = Rect(0, 3, 80, 10)
    clear_for_viewport_change(terminal, new_area)
    assert terminal.operations[-1] == ("clear_after_position", new_area.as_position())


def set_modes(recorder: Optional[List[Any]] = None) -> None:
    if recorder is not None:
        recorder.extend(
            [
                "ensure_virtual_terminal_processing",
                "enable_bracketed_paste",
                "enable_raw_mode",
                "push_keyboard_enhancement_flags",
                "enable_focus_change",
            ]
        )


@dataclass
class EnableAlternateScroll:
    """Python boundary for Rust ``tui::EnableAlternateScroll``."""

    _payload: Any = None

    def write_ansi(self, f: Any) -> Any:
        return f.write("\x1b[?1007h")

    def execute_winapi(self) -> None:
        raise OSError("tried to execute EnableAlternateScroll using WinAPI; use ANSI instead")

    def is_ansi_code_supported(self) -> bool:
        return True


@dataclass
class DisableAlternateScroll:
    """Python boundary for Rust ``tui::DisableAlternateScroll``."""

    _payload: Any = None

    def write_ansi(self, f: Any) -> Any:
        return f.write("\x1b[?1007l")

    def execute_winapi(self) -> None:
        raise OSError("tried to execute DisableAlternateScroll using WinAPI; use ANSI instead")

    def is_ansi_code_supported(self) -> bool:
        return True


def write_ansi(command: Any, f: Any = None, **kwargs: Any) -> Any:
    target = f if f is not None else kwargs.get("f")
    if target is None:
        raise TypeError("write_ansi requires a writer")
    return command.write_ansi(target)


def execute_winapi(command: Any) -> Any:
    return command.execute_winapi()


def is_ansi_code_supported(command: Any) -> bool:
    return bool(command.is_ansi_code_supported())


class RawModeRestore(Enum):
    """Python boundary for Rust enum ``tui::RawModeRestore``."""

    DISABLE = "disable"
    KEEP = "keep"


class KeyboardRestore(Enum):
    """Python boundary for Rust enum ``tui::KeyboardRestore``."""

    POP_STACK = "pop_stack"
    RESET_AFTER_EXIT = "reset_after_exit"


def restore_common(
    raw_mode_restore: Any,
    keyboard_restore: Any,
    recorder: Optional[List[Any]] = None,
) -> None:
    raw_value = _enum_value(raw_mode_restore)
    key_value = _enum_value(keyboard_restore)
    if recorder is not None:
        recorder.append("ensure_virtual_terminal_processing")
        if key_value == KeyboardRestore.RESET_AFTER_EXIT.value:
            recorder.append("reset_keyboard_enhancement_flags")
        else:
            recorder.append("pop_keyboard_enhancement_flags")
        recorder.append("disable_bracketed_paste")
        recorder.append("disable_focus_change")
        if raw_value == RawModeRestore.DISABLE.value:
            recorder.append("disable_raw_mode")
        recorder.append("show_cursor")


def restore(recorder: Optional[List[Any]] = None) -> None:
    restore_common(RawModeRestore.DISABLE, KeyboardRestore.POP_STACK, recorder)


def restore_after_exit(recorder: Optional[List[Any]] = None) -> None:
    restore_common(RawModeRestore.DISABLE, KeyboardRestore.RESET_AFTER_EXIT, recorder)


def restore_keep_raw(recorder: Optional[List[Any]] = None) -> None:
    restore_common(RawModeRestore.KEEP, KeyboardRestore.POP_STACK, recorder)


class RestoreMode(Enum):
    """Python boundary for Rust enum ``tui::RestoreMode``."""

    FULL = "full"
    KEEP_RAW = "keep_raw"

    def restore(self, recorder: Optional[List[Any]] = None) -> None:
        if self is RestoreMode.FULL:
            restore(recorder)
            return
        if self is RestoreMode.KEEP_RAW:
            restore_keep_raw(recorder)
            return
        raise AssertionError("unhandled restore mode: {!r}".format(self))


def flush_terminal_input_buffer(terminal: Any = None) -> None:
    if terminal is not None and hasattr(terminal, "operations"):
        terminal.operations.append("flush_terminal_input_buffer")


def init(terminal: Optional[Any] = None) -> InitializedTerminal:
    term = terminal if terminal is not None else SemanticTerminal()
    set_modes(getattr(term, "operations", None))
    flush_terminal_input_buffer(term)
    set_panic_hook()
    return InitializedTerminal(
        terminal=term,
        enhanced_keys_supported=detect_keyboard_enhancement_supported(term),
        stderr_guard=None,
    )


def cursor_position_with_crossterm(backend: Any = None) -> Position:
    if backend is not None and hasattr(backend, "get_cursor_position"):
        return backend.get_cursor_position()
    return Position(0, 0)


def detect_keyboard_enhancement_supported(terminal: Any = None) -> bool:
    return bool(getattr(terminal, "enhanced_keys_supported", False))


def set_panic_hook() -> None:
    return None


class TuiEvent:
    """Semantic mirror for Rust enum ``tui::TuiEvent``."""

    def __init__(self, kind: str, payload: Any = None) -> None:
        self.kind = kind
        self.payload = payload

    @classmethod
    def key(cls, key_event: Any) -> "TuiEvent":
        return cls("key", key_event)

    @classmethod
    def paste(cls, text: str) -> "TuiEvent":
        return cls("paste", text)

    @classmethod
    def resize(cls, width: int, height: int) -> "TuiEvent":
        return cls("resize", (width, height))

    @classmethod
    def draw(cls) -> "TuiEvent":
        return cls("draw")

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, TuiEvent) and (self.kind, self.payload) == (other.kind, other.payload)

    def __repr__(self) -> str:
        return "TuiEvent(kind={!r}, payload={!r})".format(self.kind, self.payload)


@dataclass
class Tui:
    """Python semantic boundary for Rust ``tui::Tui``."""

    terminal: Any = field(default_factory=SemanticTerminal)
    enhanced_keys: bool = False
    stderr_guard: Any = None
    frame_requester_value: FrameRequester = field(default_factory=FrameRequester)
    pending_history_lines: List[PendingHistoryLines] = field(default_factory=list)
    alt_saved_viewport: Optional[Rect] = None
    alt_screen_active: bool = False
    terminal_focused: bool = True
    notification_backend: Any = None
    notification_condition: Any = NotificationCondition.UNFOCUSED
    is_zellij: bool = False
    alt_screen_enabled: bool = True
    event_broker_paused: bool = False
    event_queue: List[TuiEvent] = field(default_factory=list)
    ambient_pet_image_state: Any = None
    pet_picker_preview_image_state: Any = None

    @classmethod
    def new(
        cls,
        terminal: Optional[Any] = None,
        enhanced_keys_supported: bool = False,
        stderr_guard: Any = None,
    ) -> "Tui":
        return cls(terminal if terminal is not None else SemanticTerminal(), enhanced_keys_supported, stderr_guard)

    def set_alt_screen_enabled(self, enabled: bool) -> None:
        self.alt_screen_enabled = bool(enabled)

    def set_notification_settings(self, backend: Any, condition: Any = NotificationCondition.UNFOCUSED) -> None:
        self.notification_backend = backend
        self.notification_condition = condition

    def frame_requester(self) -> FrameRequester:
        return self.frame_requester_value

    def enhanced_keys_supported(self) -> bool:
        return self.enhanced_keys

    def is_alt_screen_active(self) -> bool:
        return self.alt_screen_active

    def pause_events(self) -> None:
        self.event_broker_paused = True

    def resume_events(self) -> None:
        self.event_broker_paused = False

    def with_restored(self, mode: Any = RestoreMode.FULL, callback: Optional[Callable[..., Any]] = None) -> "_AwaitableRestored":
        return _AwaitableRestored(self, mode, callback)

    def notify(self, message: str) -> bool:
        if not should_emit_notification(self.notification_condition, self.terminal_focused):
            return False
        backend = self.notification_backend
        if backend is None:
            return False
        try:
            if hasattr(backend, "notify"):
                backend.notify(message)
            elif callable(backend):
                backend(message)
            else:
                raise TypeError("notification backend must be callable or expose notify")
            return True
        except Exception:
            self.notification_backend = None
            return False

    def event_stream(self) -> Iterator[TuiEvent]:
        return iter(list(self.event_queue))

    def enter_alt_screen(self) -> None:
        if not self.alt_screen_enabled or self.alt_screen_active:
            return
        self.alt_saved_viewport = self.terminal.viewport_area
        self.terminal.operations.extend(["enter_alternate_screen", "enable_alternate_scroll"])
        self.terminal.set_viewport_area(self.terminal.size())
        self.terminal.clear()
        self.alt_screen_active = True

    def leave_alt_screen(self) -> None:
        if not self.alt_screen_enabled or not self.alt_screen_active:
            return
        self.terminal.operations.extend(["disable_alternate_scroll", "leave_alternate_screen"])
        if self.alt_saved_viewport is not None:
            self.terminal.set_viewport_area(self.alt_saved_viewport)
        self.alt_screen_active = False

    def insert_history_lines(self, lines: List[Any]) -> None:
        self._insert_history_lines(list(lines), "PreWrap")

    def insert_history_lines_with_wrap_policy(self, lines: List[Any], wrap_policy: str) -> None:
        self._insert_history_lines(list(lines), wrap_policy)

    def insert_history_hyperlink_lines(self, lines: List[Any]) -> None:
        self._insert_history_lines(list(lines), "PreWrap")

    def insert_history_hyperlink_lines_with_wrap_policy(self, lines: List[Any], wrap_policy: str) -> None:
        self._insert_history_lines(list(lines), wrap_policy)

    def clear_pending_history_lines(self) -> None:
        self.pending_history_lines.clear()

    def update_inline_viewport_for_resize_reflow(self, height: int) -> bool:
        return update_inline_viewport_for_resize_reflow(self.terminal, height)

    def flush_pending_history_lines(self) -> None:
        flush_pending_history_lines(self.terminal, self.pending_history_lines, self.is_zellij)

    def draw(self, draw_fn: Optional[Callable[[Any], Any]] = None) -> Any:
        pending = self.pending_viewport_area()
        if pending is not None:
            self.terminal.set_viewport_area(pending)
        self.flush_pending_history_lines()
        if draw_fn is None:
            draw_fn = lambda _frame: None
        return self.terminal.draw(draw_fn)

    def draw_ambient_pet_image(self, *args: Any, **kwargs: Any) -> None:
        self.ambient_pet_image_state = args or kwargs
        self.terminal.operations.append("draw_ambient_pet_image")

    def draw_pet_picker_preview_image(self, *args: Any, **kwargs: Any) -> None:
        self.pet_picker_preview_image_state = args or kwargs
        self.terminal.operations.append("draw_pet_picker_preview_image")

    def clear_ambient_pet_image(self) -> None:
        self.ambient_pet_image_state = None
        self.terminal.operations.append("clear_ambient_pet_image")

    def clear_pet_picker_preview_image(self) -> None:
        self.pet_picker_preview_image_state = None
        self.terminal.operations.append("clear_pet_picker_preview_image")

    def draw_with_resize_reflow(self, draw_fn: Optional[Callable[[Any], Any]] = None, height: Optional[int] = None) -> Any:
        self.update_inline_viewport_for_resize_reflow(self.terminal.viewport_area.height if height is None else height)
        return self.draw(draw_fn)

    def pending_viewport_area(self) -> Optional[Rect]:
        if self.terminal.last_known_cursor_pos == self.terminal.cursor_position:
            return None
        delta_y = self.terminal.cursor_position.y - self.terminal.last_known_cursor_pos.y
        if delta_y == 0:
            return None
        return self.terminal.viewport_area.offset(0, delta_y)

    def _insert_history_lines(self, lines: List[Any], wrap_policy: str) -> None:
        if not lines:
            return
        if self.pending_history_lines and self.pending_history_lines[-1].wrap_policy == wrap_policy:
            self.pending_history_lines[-1].lines.extend(lines)
        else:
            self.pending_history_lines.append(PendingHistoryLines(lines, wrap_policy))
        self.frame_requester_value.schedule_frame()


class _AwaitableRestored:
    def __init__(self, tui: Tui, mode: Any, callback: Optional[Callable[..., Any]]) -> None:
        self.tui = tui
        self.mode = mode
        self.callback = callback

    def __await__(self) -> Iterator[Any]:
        async def run() -> Any:
            was_alt = self.tui.alt_screen_active
            self.tui.pause_events()
            if was_alt:
                self.tui.leave_alt_screen()
            _restore_mode(self.mode, self.tui.terminal.operations)
            try:
                result = None if self.callback is None else self.callback()
                if inspect.isawaitable(result):
                    result = await result
                return result
            finally:
                set_modes(self.tui.terminal.operations)
                flush_terminal_input_buffer(self.tui.terminal)
                if was_alt:
                    self.tui.enter_alt_screen()
                self.tui.resume_events()

        return run().__await__()


def clear_for_viewport_change(terminal: Any, new_area: Rect) -> None:
    previous = terminal.viewport_area
    clear_from = new_area.as_position() if previous.is_empty() else previous.as_position()
    terminal.set_viewport_area(new_area)
    terminal.clear_after_position(clear_from)


def update_inline_viewport_for_resize_reflow(terminal: Any, height: int) -> bool:
    screen = terminal.size()
    old_screen = terminal.last_known_screen_size
    old_viewport = terminal.viewport_area
    was_bottom_aligned = old_viewport.bottom() == old_screen.height
    new_height = max(0, min(int(height), screen.height))
    if was_bottom_aligned:
        new_y = max(0, screen.height - new_height)
    else:
        new_y = min(old_viewport.y, max(0, screen.height - new_height))
    new_area = Rect(0, new_y, screen.width, new_height)
    needs_full_repaint = new_area != old_viewport
    if needs_full_repaint:
        clear_for_viewport_change(terminal, new_area)
    terminal.last_known_screen_size = screen
    return needs_full_repaint


def flush_pending_history_lines(
    terminal: Any,
    pending_history_lines: List[PendingHistoryLines],
    is_zellij: bool = False,
) -> None:
    if not pending_history_lines:
        return
    if is_zellij:
        terminal.operations.append("zellij_raw_mode_restore")
    for pending in pending_history_lines:
        terminal.operations.append(("insert_history_lines", tuple(pending.lines), pending.wrap_policy))
    pending_history_lines.clear()


def ensure_virtual_terminal_processing() -> None:
    return None


def run_terminal_tui(*args: Any, **kwargs: Any) -> int:
    """Run the Rust ``tui``-aligned terminal product path."""

    from .terminal_runtime import run_terminal_tui as _run_terminal_tui

    return _run_terminal_tui(*args, **kwargs)


def enable_for_handle(*args: Any, **kwargs: Any) -> None:
    return None


def _restore_mode(mode: Any, recorder: Optional[List[Any]] = None) -> None:
    value = _enum_value(mode)
    if value == RestoreMode.KEEP_RAW.value:
        restore_keep_raw(recorder)
    else:
        restore(recorder)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _coerce_notification_condition(condition: Any) -> NotificationCondition:
    if isinstance(condition, NotificationCondition):
        return condition
    value = getattr(condition, "value", condition)
    name = getattr(condition, "name", None)
    candidates = {str(value).lower()}
    if name is not None:
        candidates.add(str(name).lower())
    if {"unfocused", "notificationcondition.unfocused"} & candidates:
        return NotificationCondition.UNFOCUSED
    if {"always", "notificationcondition.always"} & candidates:
        return NotificationCondition.ALWAYS
    raise ValueError("unknown notification condition: {!r}".format(condition))


__all__ = [
    "DisableAlternateScroll",
    "EnableAlternateScroll",
    "FrameRequester",
    "InitializedTerminal",
    "KeyboardRestore",
    "NotificationCondition",
    "PendingHistoryLines",
    "Position",
    "RUST_MODULE",
    "RawModeRestore",
    "Rect",
    "RestoreMode",
    "SemanticTerminal",
    "TARGET_FRAME_INTERVAL",
    "Terminal",
    "Tui",
    "TuiEvent",
    "always_notification_condition_emits_when_focused",
    "clear_for_viewport_change",
    "cursor_position_with_crossterm",
    "detect_keyboard_enhancement_supported",
    "drop",
    "enable_for_handle",
    "ensure_virtual_terminal_processing",
    "execute_winapi",
    "first_viewport_change_clears_from_new_viewport_when_old_viewport_is_empty",
    "flush_pending_history_lines",
    "flush_terminal_input_buffer",
    "init",
    "is_ansi_code_supported",
    "restore",
    "restore_after_exit",
    "restore_common",
    "restore_keep_raw",
    "running_in_vscode_terminal",
    "run_terminal_tui",
    "set_modes",
    "set_panic_hook",
    "should_emit_notification",
    "unfocused_notification_condition_emits_when_unfocused",
    "unfocused_notification_condition_is_suppressed_when_focused",
    "update_inline_viewport_for_resize_reflow",
    "write_ansi",
]
