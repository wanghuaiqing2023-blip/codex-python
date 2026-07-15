"""Semantic Python port for Rust ``codex-tui::tui``.

Upstream source: ``codex/codex-rs/tui/src/tui.rs``.

This module mirrors the Rust TUI runtime boundary with semantic Python models. The
actual terminal side effects remain represented as operations on ``SemanticTerminal``
so tests and callers can validate state transitions without depending on crossterm or
ratatui concrete types.
"""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, List, Optional, Protocol

from ...terminal_detection import terminal_info
from .._porting import RustTuiModule
from ..bottom_pane.terminal_footprint import (
    TerminalBottomPaneFootprint,
)

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
        self.last_known_screen_size = self.size()
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
        return cls(
            terminal=terminal if terminal is not None else SemanticTerminal(),
            enhanced_keys=enhanced_keys_supported,
            stderr_guard=stderr_guard,
            is_zellij=terminal_info().is_zellij(),
        )

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
        desired_height = self.terminal.viewport_area.height if height is None else height
        needs_full_repaint = self.update_inline_viewport_for_resize_reflow(desired_height)
        self.flush_pending_history_lines()
        if needs_full_repaint:
            self.terminal.invalidate_viewport()
        if draw_fn is None:
            draw_fn = lambda _frame: None
        return self.terminal.draw(draw_fn)

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
    terminal_height_shrank = screen.height < old_screen.height
    terminal_height_grew = screen.height > old_screen.height
    previous_area = terminal.viewport_area
    viewport_was_bottom_aligned = previous_area.bottom() == old_screen.height

    area = Rect(
        previous_area.x,
        previous_area.y,
        screen.width,
        max(0, min(int(height), screen.height)),
    )
    if area.bottom() > screen.height:
        scroll_by = area.bottom() - screen.height
        if not terminal_height_shrank:
            terminal.scroll_region_up(range(0, area.top()), scroll_by)
        area = Rect(area.x, screen.height - area.height, area.width, area.height)
    elif terminal_height_grew and viewport_was_bottom_aligned:
        area = Rect(area.x, screen.height - area.height, area.width, area.height)

    needs_full_repaint = area != previous_area
    if needs_full_repaint:
        clear_position = Position(0, min(previous_area.y, area.y))
        terminal.set_viewport_area(area)
        terminal.clear_after_position(clear_position)
    return needs_full_repaint


@dataclass
class TerminalInlineViewport:
    """Real-terminal adapter for Rust ``Tui::draw_with_resize_reflow``.

    The policy and state live in ``tui``. ANSI operations remain delegated to
    ``custom_terminal`` through the callbacks supplied by the projection
    runner.
    """

    terminal_size: Callable[[], os.terminal_size]
    scroll_region_up_effect: Callable[[int, int, int], None]
    scroll_region_down_effect: Callable[[int, int, int], None]
    clear_after_position_effect: Callable[[int, int], None]
    invalidate_viewport_effect: Callable[[], None]
    viewport_area: Rect | None = None
    last_known_screen_size: Rect | None = None

    def _ensure_initialized(self) -> None:
        if self.viewport_area is not None and self.last_known_screen_size is not None:
            return
        size = self.terminal_size()
        screen = Rect(0, 0, max(0, int(size.columns)), max(0, int(size.lines)))
        self.last_known_screen_size = screen
        self.viewport_area = Rect(0, screen.height, screen.width, 0)

    def size(self) -> Rect:
        size = self.terminal_size()
        return Rect(0, 0, max(0, int(size.columns)), max(0, int(size.lines)))

    def scroll_region_up(self, region: range, scroll_by: int) -> None:
        self.scroll_region_up_effect(region.start, region.stop, scroll_by)

    def set_viewport_area(self, area: Rect) -> None:
        self.viewport_area = area

    def clear_after_position(self, position: Position) -> None:
        self.clear_after_position_effect(position.y, position.x)

    def update_inline_viewport_for_resize_reflow(self, height: int) -> bool:
        self._ensure_initialized()
        changed = update_inline_viewport_for_resize_reflow(self, height)
        if changed:
            self.invalidate_viewport_effect()
        return changed

    def prepare_history_insert(self, inserted_rows: int) -> None:
        """Move a non-bottom-aligned viewport down before history insertion.

        This mirrors ``insert_history``'s standard-mode area update while
        retaining viewport state in the terminal/TUI boundary.
        """

        self._ensure_initialized()
        assert self.viewport_area is not None
        screen = self.size()
        area = self.viewport_area
        if area.bottom() >= screen.height:
            return
        scroll_amount = min(max(0, int(inserted_rows)), screen.height - area.bottom())
        if scroll_amount == 0:
            return
        self.scroll_region_down_effect(area.top(), screen.height, scroll_amount)
        self.viewport_area = Rect(area.x, area.y + scroll_amount, area.width, area.height)
        self.invalidate_viewport_effect()

    def reset_top_after_resize_replay_clear(self) -> None:
        """Reset viewport geometry after app::resize_reflow clears the terminal.

        Rust ``App::clear_terminal_for_resize_replay`` resets the inline
        viewport to row zero before retained HistoryCells are emitted again.
        The terminal adapter keeps that geometry transition in ``tui`` while
        app::resize_reflow remains responsible for the hard-clear side effect.
        """

        self._ensure_initialized()
        assert self.viewport_area is not None
        area = self.viewport_area
        if area.y == 0:
            return
        self.viewport_area = Rect(area.x, 0, area.width, area.height)
        self.invalidate_viewport_effect()

    def draw_with_resize_reflow(
        self,
        height: int,
        draw_fn: Callable[[Rect], Any],
    ) -> Any:
        self.update_inline_viewport_for_resize_reflow(height)
        assert self.viewport_area is not None
        result = draw_fn(self.viewport_area)
        self.last_known_screen_size = self.size()
        return result


class TerminalBottomPaneRenderContextProtocol(Protocol):
    popup_height: int
    active_tail_height: int
    composer_height: int


class TerminalBottomPaneRenderContextProviderProtocol(Protocol):
    def render_context_for_size(
        self,
        size: os.terminal_size,
        composer_cursor_visible: Callable[[], bool],
    ) -> TerminalBottomPaneRenderContextProtocol:
        ...


@dataclass(frozen=True)
class TerminalBottomPaneViewportRenderPass:
    """TUI-owned frame inputs for one inline-viewport draw."""

    check_resize: bool
    viewport_area: Rect
    clear_popup_height: int = 0
    clear_live_status_active: bool = False
    clear_active_tail_height: int = 0
    clear_composer_height: int = 1


@dataclass
class TerminalBottomPaneViewportCycleRunner:
    """Run bottom-pane frames through Rust's ``tui`` viewport lifecycle."""

    viewport: TerminalInlineViewport
    resize: Callable[[], None]
    footprint: TerminalBottomPaneFootprint = field(default_factory=TerminalBottomPaneFootprint)

    @staticmethod
    def _footprint_for_context(
        live_status: Any,
        context: TerminalBottomPaneRenderContextProtocol,
    ) -> TerminalBottomPaneFootprint:
        return TerminalBottomPaneFootprint.from_surface(
            live_status,
            popup_height=int(context.popup_height),
            active_tail_height=int(context.active_tail_height),
            composer_height=int(context.composer_height),
        )

    def history_bottom_row(
        self,
        size: os.terminal_size,
        *,
        live_status: Any,
        bottom_pane_state: TerminalBottomPaneRenderContextProviderProtocol,
        composer_cursor_visible: Callable[[], bool],
        reserve_active_bottom_pane: bool = False,
    ) -> int:
        context = bottom_pane_state.render_context_for_size(size, composer_cursor_visible)
        desired = self._footprint_for_context(live_status, context).height_for_size(size)
        if self.viewport.viewport_area is None:
            top = max(0, int(size.lines) - desired)
        else:
            top = self.viewport.viewport_area.y
        # Rust insert_history always uses terminal.viewport_area.top(). The
        # viewport draw cycle, not a second synthetic history boundary, owns
        # reserving rows when status or another bottom-pane surface appears.
        del reserve_active_bottom_pane
        return max(1, top)

    def history_bottom_row_callback(
        self,
        *,
        terminal_size: Callable[[], os.terminal_size],
        live_status: Callable[[], Any],
        bottom_pane_state: TerminalBottomPaneRenderContextProviderProtocol,
        composer_cursor_visible: Callable[[], bool],
    ) -> Callable[[bool], int]:
        def history_bottom_row(reserve_active_bottom_pane: bool = False) -> int:
            return self.history_bottom_row(
                terminal_size(),
                live_status=live_status(),
                bottom_pane_state=bottom_pane_state,
                composer_cursor_visible=composer_cursor_visible,
                reserve_active_bottom_pane=reserve_active_bottom_pane,
            )

        return history_bottom_row

    def prepare_history_insert(self, inserted_rows: int) -> None:
        self.viewport.prepare_history_insert(inserted_rows)

    def prepare_resize_reflow(
        self,
        size: os.terminal_size,
        *,
        live_status: Any,
        bottom_pane_state: TerminalBottomPaneRenderContextProviderProtocol,
        composer_cursor_visible: Callable[[], bool],
    ) -> Rect:
        """Resize the TUI viewport before app-owned transcript replay.

        Rust queues reflowed history before ``draw_with_resize_reflow``, whose
        first terminal effect is updating the viewport. The real-terminal
        adapter writes replay rows immediately, so this explicit handoff keeps
        the same observable ordering without moving geometry into ``app``.
        """

        context = bottom_pane_state.render_context_for_size(size, composer_cursor_visible)
        desired_height = self._footprint_for_context(live_status, context).height_for_size(size)
        self.viewport.update_inline_viewport_for_resize_reflow(desired_height)
        assert self.viewport.viewport_area is not None
        return self.viewport.viewport_area

    def resize_reflow_replay_callback_factory(
        self,
        *,
        terminal_size: Callable[[], os.terminal_size],
        live_status: Callable[[], Any],
        bottom_pane_state: TerminalBottomPaneRenderContextProviderProtocol,
        composer_cursor_visible: Callable[[], bool],
    ) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
        def bind_replay(replay_history_scrollback: Callable[[], Any]) -> Callable[[], Any]:
            def resize_reflow_replay() -> Any:
                self.prepare_resize_reflow(
                    terminal_size(),
                    live_status=live_status(),
                    bottom_pane_state=bottom_pane_state,
                    composer_cursor_visible=composer_cursor_visible,
                )
                self.viewport.reset_top_after_resize_replay_clear()
                return replay_history_scrollback()

            return resize_reflow_replay

        return bind_replay

    def clear_callback(
        self,
        *,
        live_status: Callable[[], Any],
        clear_factory: Callable[[Any, bool, TerminalBottomPaneFootprint], Callable[[], bool]],
    ) -> Callable[[bool], bool]:
        def clear(check_resize: bool = True) -> bool:
            if check_resize:
                self.resize()
            return bool(clear_factory(live_status(), False, self.footprint)())

        return clear

    def render_for_view_state_callback(
        self,
        *,
        terminal_size: Callable[[], os.terminal_size],
        live_status: Callable[[], Any],
        bottom_pane_state: TerminalBottomPaneRenderContextProviderProtocol,
        composer_cursor_visible: Callable[[], bool],
        render_factory: Callable[
            [Any, bool],
            Callable[[TerminalBottomPaneViewportRenderPass, TerminalBottomPaneRenderContextProtocol], bool],
        ],
    ) -> Callable[[bool, bool], bool]:
        def render_for_view_state(
            check_resize: bool = True,
            clear_external_blank_rows: bool = False,
        ) -> bool:
            if check_resize:
                self.resize()
            size = terminal_size()
            current_live_status = live_status()
            context = bottom_pane_state.render_context_for_size(size, composer_cursor_visible)
            current = self._footprint_for_context(current_live_status, context)
            render = render_factory(current_live_status, clear_external_blank_rows)

            def draw(viewport_area: Rect) -> bool:
                render_pass = TerminalBottomPaneViewportRenderPass(
                    check_resize=False,
                    viewport_area=viewport_area,
                    clear_popup_height=self.footprint.popup_height,
                    clear_live_status_active=self.footprint.live_status_active,
                    clear_active_tail_height=self.footprint.active_tail_height,
                    clear_composer_height=self.footprint.composer_height,
                )
                return bool(render(render_pass, context))

            rendered = bool(
                self.viewport.draw_with_resize_reflow(
                    current.height_for_size(size),
                    draw,
                )
            )
            if rendered:
                self.footprint = current
            return rendered

        return render_for_view_state


def create_terminal_bottom_pane_viewport_cycle_runner(
    *,
    terminal_size: Callable[[], os.terminal_size],
    resize: Callable[[], None],
    scroll_region_up: Callable[[int, int, int], None],
    scroll_region_down: Callable[[int, int, int], None],
    clear_after_position: Callable[[int, int], None],
    invalidate_viewport: Callable[[], None],
) -> TerminalBottomPaneViewportCycleRunner:
    return TerminalBottomPaneViewportCycleRunner(
        viewport=TerminalInlineViewport(
            terminal_size=terminal_size,
            scroll_region_up_effect=scroll_region_up,
            scroll_region_down_effect=scroll_region_down,
            clear_after_position_effect=clear_after_position,
            invalidate_viewport_effect=invalidate_viewport,
        ),
        resize=resize,
    )


def flush_pending_history_lines(
    terminal: Any,
    pending_history_lines: List[PendingHistoryLines],
    is_zellij: bool = False,
) -> None:
    if not pending_history_lines:
        return
    if is_zellij and any(batch.wrap_policy == "Terminal" for batch in pending_history_lines):
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
    "TerminalBottomPaneViewportCycleRunner",
    "TerminalBottomPaneViewportRenderPass",
    "TerminalInlineViewport",
    "Tui",
    "TuiEvent",
    "always_notification_condition_emits_when_focused",
    "clear_for_viewport_change",
    "create_terminal_bottom_pane_viewport_cycle_runner",
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
