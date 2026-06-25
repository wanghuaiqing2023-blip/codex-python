from __future__ import annotations

from pycodex.tui.key_hint import MOD_CONTROL, MOD_SHIFT, KeyBinding, KeyEvent, is_pressed
from pycodex.tui.onboarding.keys import (
    CANCEL,
    CONFIRM,
    MOVE_DOWN,
    MOVE_UP,
    QUIT,
    SELECT_FIRST,
    SELECT_SECOND,
    SELECT_THIRD,
    TOGGLE_ANIMATION,
)


def test_onboarding_navigation_bindings_match_rust_constants() -> None:
    # Rust: codex-tui/src/onboarding/keys.rs MOVE_UP and MOVE_DOWN.
    assert MOVE_UP == (KeyBinding.new("Up"), KeyBinding.new("k"))
    assert MOVE_DOWN == (KeyBinding.new("Down"), KeyBinding.new("j"))
    assert is_pressed(MOVE_UP, KeyEvent.new("Up"))
    assert is_pressed(MOVE_UP, KeyEvent.new("k"))
    assert not is_pressed(MOVE_UP, KeyEvent.new("j"))


def test_onboarding_selection_bindings_match_rust_constants() -> None:
    # Rust: SELECT_FIRST/SECOND/THIRD fixed before keymap configuration exists.
    assert SELECT_FIRST == (KeyBinding.new("1"), KeyBinding.new("y"))
    assert SELECT_SECOND == (KeyBinding.new("2"), KeyBinding.new("n"))
    assert SELECT_THIRD == (KeyBinding.new("3"),)
    assert is_pressed(SELECT_FIRST, KeyEvent.new("y"))
    assert is_pressed(SELECT_SECOND, KeyEvent.new("n"))
    assert is_pressed(SELECT_THIRD, KeyEvent.new("3"))


def test_onboarding_confirm_cancel_quit_bindings_match_rust_constants() -> None:
    # Rust: CONFIRM, CANCEL, and QUIT constants.
    assert CONFIRM == (KeyBinding.new("Enter"),)
    assert CANCEL == (KeyBinding.new("Esc"),)
    assert QUIT == (
        KeyBinding.new("q"),
        KeyBinding.new("c", {MOD_CONTROL}),
        KeyBinding.new("d", {MOD_CONTROL}),
    )
    assert is_pressed(CONFIRM, KeyEvent.new("Enter"))
    assert is_pressed(CANCEL, KeyEvent.new("Esc"))
    assert is_pressed(QUIT, KeyEvent.new("c", {MOD_CONTROL}))
    assert is_pressed(QUIT, KeyEvent.new("d", {MOD_CONTROL}))


def test_onboarding_toggle_animation_includes_ctrl_shift_period() -> None:
    # Rust: TOGGLE_ANIMATION includes Ctrl+. and Ctrl+Shift+.
    assert TOGGLE_ANIMATION == (
        KeyBinding.new(".", {MOD_CONTROL}),
        KeyBinding.new(".", {MOD_CONTROL, MOD_SHIFT}),
    )
    assert is_pressed(TOGGLE_ANIMATION, KeyEvent.new(".", {MOD_CONTROL}))
    assert is_pressed(TOGGLE_ANIMATION, KeyEvent.new(".", {MOD_CONTROL, MOD_SHIFT}))
    assert not is_pressed(TOGGLE_ANIMATION, KeyEvent.new("."))
