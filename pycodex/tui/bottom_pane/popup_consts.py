"""Shared popup constants for Rust ``codex-tui::bottom_pane::popup_consts``."""

from __future__ import annotations

from typing import Any

from .._porting import RustTuiModule
from .. import key_hint
from ..keymap import ListKeymap, KeyBinding, plain, primary_binding

RUST_MODULE = RustTuiModule(crate="codex-tui", module="bottom_pane::popup_consts", source="codex/codex-rs/tui/src/bottom_pane/popup_consts.rs")

MAX_POPUP_ROWS = 8


def _hint(binding: KeyBinding) -> str:
    result = ""
    if "CONTROL" in binding.modifiers:
        result += key_hint.CTRL_PREFIX
    if "SHIFT" in binding.modifiers:
        result += key_hint.SHIFT_PREFIX
    if "ALT" in binding.modifiers:
        result += key_hint.ALT_PREFIX
    key = {
        "Enter": "enter",
        " ": "space",
        "Up": key_hint.UP_LABEL,
        "Down": key_hint.DOWN_LABEL,
        "Left": key_hint.LEFT_LABEL,
        "Right": key_hint.RIGHT_LABEL,
        "PageUp": "pgup",
        "PageDown": "pgdn",
    }.get(binding.code, binding.code.lower())
    return f"{result}{key}"


def standard_popup_hint_line() -> str:
    return accept_cancel_hint_line(plain("Enter"), "to confirm", plain("Esc"), "to go back")


def standard_popup_hint_line_for_keymap(list_keymap: ListKeymap) -> str:
    return accept_cancel_hint_line(
        primary_binding(list_keymap.accept),
        "to confirm",
        primary_binding(list_keymap.cancel),
        "to go back",
    )


def accept_cancel_hint_line(
    accept: KeyBinding | None,
    accept_label: str,
    cancel: KeyBinding | None,
    cancel_label: str,
) -> str:
    if accept is not None and cancel is not None:
        return f"Press {_hint(accept)} {accept_label} or {_hint(cancel)} {cancel_label}"
    if accept is not None:
        return f"Press {_hint(accept)} {accept_label}"
    if cancel is not None:
        return f"Press {_hint(cancel)} {cancel_label}"
    return ""


__all__ = [
    "MAX_POPUP_ROWS",
    "RUST_MODULE",
    "accept_cancel_hint_line",
    "standard_popup_hint_line",
    "standard_popup_hint_line_for_keymap",
]
