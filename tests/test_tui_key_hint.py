from __future__ import annotations

import sys

from pycodex.tui.key_hint import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    KeyBinding,
    KeyEvent,
    UP_LABEL,
    c0_control_char_to_ctrl_char,
    ctrl,
    ctrl_alt,
    ctrl_alt_sets_both_modifiers,
    ctrl_binding_does_not_match_ambiguous_c0_escape_or_delete,
    ctrl_bindings_match_all_supported_c0_control_char_events,
    ctrl_letter_binding_matches_c0_control_char_events,
    from_,
    has_ctrl_or_alt,
    has_ctrl_or_alt_checks_supported_modifier_combinations,
    history_search_ctrl_bindings_match_c0_control_char_events,
    is_plain_text_key_event,
    is_press_accepts_press_and_repeat_but_rejects_release,
    is_pressed,
    keybinding_list_ext_matches_any_binding,
    modifiers_to_string,
    normalize_key_parts,
    plain,
    shift,
    shift_letter_binding_does_not_match_plain_lowercase_or_other_uppercase,
    shift_letter_binding_preserves_other_modifiers_with_uppercase_compat,
    shifted_letter_binding_matches_uppercase_char_events,
)


def test_is_press_accepts_press_and_repeat_but_rejects_release() -> None:
    is_press_accepts_press_and_repeat_but_rejects_release()


def test_keybinding_list_ext_matches_any_binding() -> None:
    keybinding_list_ext_matches_any_binding()


def test_shifted_letter_binding_matches_uppercase_char_events() -> None:
    shifted_letter_binding_matches_uppercase_char_events()


def test_shift_letter_binding_preserves_other_modifiers_with_uppercase_compat() -> None:
    shift_letter_binding_preserves_other_modifiers_with_uppercase_compat()


def test_shift_letter_binding_does_not_match_plain_lowercase_or_other_uppercase() -> None:
    shift_letter_binding_does_not_match_plain_lowercase_or_other_uppercase()


def test_ctrl_letter_binding_matches_c0_control_char_events() -> None:
    ctrl_letter_binding_matches_c0_control_char_events()


def test_ctrl_bindings_match_all_supported_c0_control_char_events() -> None:
    ctrl_bindings_match_all_supported_c0_control_char_events()


def test_ctrl_binding_does_not_match_ambiguous_c0_escape_or_delete() -> None:
    ctrl_binding_does_not_match_ambiguous_c0_escape_or_delete()


def test_history_search_ctrl_bindings_match_c0_control_char_events() -> None:
    history_search_ctrl_bindings_match_c0_control_char_events()


def test_ctrl_alt_sets_both_modifiers() -> None:
    ctrl_alt_sets_both_modifiers()


def test_has_ctrl_or_alt_checks_supported_modifier_combinations() -> None:
    has_ctrl_or_alt_checks_supported_modifier_combinations()


def test_normalize_key_parts_uppercase_and_raw_c0() -> None:
    assert normalize_key_parts("A") == ("a", frozenset({MOD_SHIFT}))
    assert normalize_key_parts("I", {MOD_CONTROL}) == ("i", frozenset({MOD_CONTROL, MOD_SHIFT}))
    assert normalize_key_parts("\u0010") == ("p", frozenset({MOD_CONTROL}))
    assert c0_control_char_to_ctrl_char("\u001b") is None
    assert c0_control_char_to_ctrl_char("\u007f") is None


def test_is_plain_text_key_event_allows_printable_non_ctrl_alt() -> None:
    assert is_plain_text_key_event(KeyEvent.new("j")) is True
    assert is_plain_text_key_event(KeyEvent.new("J", {MOD_SHIFT})) is True
    assert is_plain_text_key_event(KeyEvent.new("j", {MOD_CONTROL})) is False
    assert is_plain_text_key_event(KeyEvent.new("j", {MOD_ALT})) is False
    assert is_plain_text_key_event(KeyEvent.new("\u0010")) is False


def test_display_label_and_span_style() -> None:
    assert plain("Enter").display_label() == "enter"
    assert plain(" ").display_label() == "space"
    assert plain("Up").display_label() == UP_LABEL
    assert ctrl("c").display_label() == "ctrl + c"
    assert shift("a").display_label() == "shift + a"
    assert ctrl_alt("v").display_label().startswith("ctrl + ")
    assert modifiers_to_string({MOD_CONTROL, MOD_SHIFT}).startswith("ctrl + shift + ")

    span = from_(ctrl("c"))
    assert span.text == "ctrl + c"
    assert span.style == {"dim": True}


def test_is_pressed_helper_accepts_any_binding() -> None:
    assert is_pressed([plain("a"), ctrl("b")], KeyEvent.new("b", {MOD_CONTROL})) is True
    assert is_pressed([plain("a"), ctrl("b")], KeyEvent.new("b")) is False


def test_keybinding_from_event_uses_normalization() -> None:
    assert KeyBinding.from_event(KeyEvent.new("A")).parts() == ("a", frozenset({MOD_SHIFT}))


def test_has_ctrl_or_alt_platform_altgr_boundary() -> None:
    expected = not sys.platform.startswith("win")
    assert has_ctrl_or_alt({MOD_CONTROL, MOD_ALT}) is expected


