"""Python interface scaffold for Rust ``codex-tui::tui``.

Upstream source: ``codex/codex-rs/tui/src/tui.rs``.
Concrete behavior should be filled in from the Rust source and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(crate="codex-tui", module="tui", source="codex/codex-rs/tui/src/tui.rs")

TARGET_FRAME_INTERVAL: Any = None

Terminal: Any = None


class NotificationCondition(Enum):
    """Semantic mirror for ``codex_config::types::NotificationCondition``."""

    UNFOCUSED = "unfocused"
    ALWAYS = "always"

@dataclass
class InitializedTerminal:
    """Python boundary for Rust ``tui::InitializedTerminal``."""
    _payload: Any = None

def running_in_vscode_terminal(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::running_in_vscode_terminal``."""
    return not_ported(RUST_MODULE, "running_in_vscode_terminal")

def should_emit_notification(*args: Any, **kwargs: Any) -> Any:
    """Return whether a desktop notification should be emitted.

    Rust behavior:
    - ``Unfocused`` emits only when the terminal is not focused.
    - ``Always`` emits regardless of terminal focus.
    """

    if args:
        condition = args[0]
        terminal_focused = args[1] if len(args) > 1 else kwargs.get("terminal_focused")
    else:
        condition = kwargs.get("condition")
        terminal_focused = kwargs.get("terminal_focused")

    condition = _coerce_notification_condition(condition)
    terminal_focused = bool(terminal_focused)
    if condition is NotificationCondition.UNFOCUSED:
        return not terminal_focused
    if condition is NotificationCondition.ALWAYS:
        return True
    raise AssertionError(f"unhandled notification condition: {condition!r}")

def drop(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::drop``."""
    return not_ported(RUST_MODULE, "drop")

def unfocused_notification_condition_is_suppressed_when_focused(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::unfocused_notification_condition_is_suppressed_when_focused``."""
    return not_ported(RUST_MODULE, "unfocused_notification_condition_is_suppressed_when_focused")

def always_notification_condition_emits_when_focused(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::always_notification_condition_emits_when_focused``."""
    return not_ported(RUST_MODULE, "always_notification_condition_emits_when_focused")

def unfocused_notification_condition_emits_when_unfocused(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::unfocused_notification_condition_emits_when_unfocused``."""
    return not_ported(RUST_MODULE, "unfocused_notification_condition_emits_when_unfocused")

def first_viewport_change_clears_from_new_viewport_when_old_viewport_is_empty(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::first_viewport_change_clears_from_new_viewport_when_old_viewport_is_empty``."""
    return not_ported(RUST_MODULE, "first_viewport_change_clears_from_new_viewport_when_old_viewport_is_empty")

def set_modes(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::set_modes``."""
    return not_ported(RUST_MODULE, "set_modes")

@dataclass
class EnableAlternateScroll:
    """Python boundary for Rust ``tui::EnableAlternateScroll``."""
    _payload: Any = None

    def write_ansi(self, f: Any) -> None:
        f.write("\x1b[?1007h")

    def execute_winapi(self) -> None:
        raise OSError("tried to execute EnableAlternateScroll using WinAPI; use ANSI instead")

    def is_ansi_code_supported(self) -> bool:
        return True

def write_ansi(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::write_ansi``."""
    if not args:
        return not_ported(RUST_MODULE, "write_ansi")
    command = args[0]
    if hasattr(command, "write_ansi"):
        if len(args) > 1:
            return command.write_ansi(args[1])
        if "f" in kwargs:
            return command.write_ansi(kwargs["f"])
    return not_ported(RUST_MODULE, "write_ansi")

def execute_winapi(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::execute_winapi``."""
    return not_ported(RUST_MODULE, "execute_winapi")

def is_ansi_code_supported(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::is_ansi_code_supported``."""
    return not_ported(RUST_MODULE, "is_ansi_code_supported")

@dataclass
class DisableAlternateScroll:
    """Python boundary for Rust ``tui::DisableAlternateScroll``."""
    _payload: Any = None

    def write_ansi(self, f: Any) -> None:
        f.write("\x1b[?1007l")

    def execute_winapi(self) -> None:
        raise OSError("tried to execute DisableAlternateScroll using WinAPI; use ANSI instead")

    def is_ansi_code_supported(self) -> bool:
        return True

class RawModeRestore(Enum):
    """Python boundary for Rust enum ``tui::RawModeRestore``."""
    DISABLE = "disable"
    KEEP = "keep"

class KeyboardRestore(Enum):
    """Python boundary for Rust enum ``tui::KeyboardRestore``."""
    POP_STACK = "pop_stack"
    RESET_AFTER_EXIT = "reset_after_exit"

def restore_common(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::restore_common``."""
    return not_ported(RUST_MODULE, "restore_common")

def restore(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::restore``."""
    return not_ported(RUST_MODULE, "restore")

def restore_after_exit(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::restore_after_exit``."""
    return not_ported(RUST_MODULE, "restore_after_exit")

def restore_keep_raw(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::restore_keep_raw``."""
    return not_ported(RUST_MODULE, "restore_keep_raw")

class RestoreMode(Enum):
    """Python boundary for Rust enum ``tui::RestoreMode``."""
    FULL = "full"
    KEEP_RAW = "keep_raw"

    def restore(self) -> Any:
        if self is RestoreMode.FULL:
            return restore()
        if self is RestoreMode.KEEP_RAW:
            return restore_keep_raw()
        raise AssertionError(f"unhandled restore mode: {self!r}")

def flush_terminal_input_buffer(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::flush_terminal_input_buffer``."""
    return not_ported(RUST_MODULE, "flush_terminal_input_buffer")

def init(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::init``."""
    return not_ported(RUST_MODULE, "init")

def cursor_position_with_crossterm(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::cursor_position_with_crossterm``."""
    return not_ported(RUST_MODULE, "cursor_position_with_crossterm")

def detect_keyboard_enhancement_supported(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::detect_keyboard_enhancement_supported``."""
    return not_ported(RUST_MODULE, "detect_keyboard_enhancement_supported")

def set_panic_hook(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::set_panic_hook``."""
    return not_ported(RUST_MODULE, "set_panic_hook")

class TuiEvent(Enum):
    """Python boundary for Rust enum ``tui::TuiEvent``."""
    UNPORTED = "unported"

@dataclass
class Tui:
    """Python boundary for Rust ``tui::Tui``."""
    _payload: Any = None

    def new(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.new")

    def set_alt_screen_enabled(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.set_alt_screen_enabled")

    def set_notification_settings(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.set_notification_settings")

    def frame_requester(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.frame_requester")

    def enhanced_keys_supported(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.enhanced_keys_supported")

    def is_alt_screen_active(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.is_alt_screen_active")

    def pause_events(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.pause_events")

    def resume_events(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.resume_events")

    async def with_restored(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.with_restored")

    def notify(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.notify")

    def event_stream(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.event_stream")

    def enter_alt_screen(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.enter_alt_screen")

    def leave_alt_screen(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.leave_alt_screen")

    def insert_history_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.insert_history_lines")

    def insert_history_lines_with_wrap_policy(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.insert_history_lines_with_wrap_policy")

    def insert_history_hyperlink_lines_with_wrap_policy(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.insert_history_hyperlink_lines_with_wrap_policy")

    def clear_pending_history_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.clear_pending_history_lines")

    def update_inline_viewport_for_resize_reflow(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.update_inline_viewport_for_resize_reflow")

    def flush_pending_history_lines(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.flush_pending_history_lines")

    def draw(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.draw")

    def draw_ambient_pet_image(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.draw_ambient_pet_image")

    def draw_pet_picker_preview_image(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.draw_pet_picker_preview_image")

    def clear_ambient_pet_image(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.clear_ambient_pet_image")

    def draw_with_resize_reflow(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.draw_with_resize_reflow")

    def pending_viewport_area(self, *args: Any, **kwargs: Any) -> Any:
        return not_ported(RUST_MODULE, "Tui.pending_viewport_area")

@dataclass
class PendingHistoryLines:
    """Python boundary for Rust ``tui::PendingHistoryLines``."""
    _payload: Any = None

def clear_for_viewport_change(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::clear_for_viewport_change``."""
    return not_ported(RUST_MODULE, "clear_for_viewport_change")

def ensure_virtual_terminal_processing(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::ensure_virtual_terminal_processing``."""
    return None

def enable_for_handle(*args: Any, **kwargs: Any) -> Any:
    """Python boundary for Rust function ``tui::enable_for_handle``."""
    return not_ported(RUST_MODULE, "enable_for_handle")


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
    raise ValueError(f"unknown notification condition: {condition!r}")

__all__ = [
    "DisableAlternateScroll",
    "EnableAlternateScroll",
    "InitializedTerminal",
    "KeyboardRestore",
    "NotificationCondition",
    "PendingHistoryLines",
    "RUST_MODULE",
    "RawModeRestore",
    "RestoreMode",
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
    "flush_terminal_input_buffer",
    "init",
    "is_ansi_code_supported",
    "restore",
    "restore_after_exit",
    "restore_common",
    "restore_keep_raw",
    "running_in_vscode_terminal",
    "set_modes",
    "set_panic_hook",
    "should_emit_notification",
    "unfocused_notification_condition_emits_when_unfocused",
    "unfocused_notification_condition_is_suppressed_when_focused",
    "write_ansi",
]
