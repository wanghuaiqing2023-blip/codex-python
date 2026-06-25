from pycodex.tui.bottom_pane.popup_consts import (
    MAX_POPUP_ROWS,
    accept_cancel_hint_line,
    standard_popup_hint_line,
    standard_popup_hint_line_for_keymap,
)
from pycodex.tui.keymap import ListKeymap, alt, ctrl, plain, shift


def test_max_popup_rows_matches_rust_constant() -> None:
    # Rust source: bottom_pane/popup_consts.rs::MAX_POPUP_ROWS.
    assert MAX_POPUP_ROWS == 8


def test_standard_popup_hint_line_uses_enter_and_escape() -> None:
    # Rust source: standard_popup_hint_line.
    assert standard_popup_hint_line() == "Press enter to confirm or esc to go back"


def test_standard_popup_hint_line_for_keymap_uses_primary_bindings() -> None:
    keymap = ListKeymap(accept=[alt("a"), plain("Enter")], cancel=[plain("q"), plain("Esc")])
    assert standard_popup_hint_line_for_keymap(keymap) == "Press ⌥ + a to confirm or q to go back"


def test_accept_cancel_hint_line_handles_missing_bindings() -> None:
    assert accept_cancel_hint_line(plain("y"), "to accept", None, "to cancel") == "Press y to accept"
    assert accept_cancel_hint_line(None, "to accept", plain("n"), "to cancel") == "Press n to cancel"
    assert accept_cancel_hint_line(None, "to accept", None, "to cancel") == ""


def test_accept_cancel_hint_line_uses_rust_key_hint_display_labels() -> None:
    # Rust source: accept_cancel_hint_line delegates KeyBinding rendering to
    # key_hint::KeyBinding::display_label.
    assert (
        accept_cancel_hint_line(ctrl("PageUp"), "to accept", shift("PageDown"), "to cancel")
        == "Press ctrl + pgup to accept or shift + pgdn to cancel"
    )

