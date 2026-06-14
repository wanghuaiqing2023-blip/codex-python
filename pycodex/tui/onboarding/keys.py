"""Behavior port for Rust ``codex-tui::onboarding::keys``.

The Rust module defines the fixed onboarding shortcuts used before the user has
had a chance to configure Codex.  Python represents the crossterm key bindings
with the semantic ``pycodex.tui.key_hint.KeyBinding`` model.
"""

from __future__ import annotations

from .._porting import RustTuiModule
from ..key_hint import MOD_CONTROL, MOD_SHIFT, KeyBinding, ctrl, plain

RUST_MODULE = RustTuiModule(crate="codex-tui", module="onboarding::keys", source="codex/codex-rs/tui/src/onboarding/keys.rs")

MOVE_UP: tuple[KeyBinding, ...] = (
    plain("Up"),
    plain("k"),
)
MOVE_DOWN: tuple[KeyBinding, ...] = (
    plain("Down"),
    plain("j"),
)
SELECT_FIRST: tuple[KeyBinding, ...] = (
    plain("1"),
    plain("y"),
)
SELECT_SECOND: tuple[KeyBinding, ...] = (
    plain("2"),
    plain("n"),
)
SELECT_THIRD: tuple[KeyBinding, ...] = (plain("3"),)
CONFIRM: tuple[KeyBinding, ...] = (plain("Enter"),)
CANCEL: tuple[KeyBinding, ...] = (plain("Esc"),)
QUIT: tuple[KeyBinding, ...] = (
    plain("q"),
    ctrl("c"),
    ctrl("d"),
)
TOGGLE_ANIMATION: tuple[KeyBinding, ...] = (
    ctrl("."),
    KeyBinding.new(".", {MOD_CONTROL, MOD_SHIFT}),
)

__all__ = [
    "CANCEL",
    "CONFIRM",
    "MOVE_DOWN",
    "MOVE_UP",
    "QUIT",
    "RUST_MODULE",
    "SELECT_FIRST",
    "SELECT_SECOND",
    "SELECT_THIRD",
    "TOGGLE_ANIMATION",
]
