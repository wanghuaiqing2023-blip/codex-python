import pytest

from pycodex.config import (
    KeybindingSpec,
    KeybindingsSpec,
    Tui,
    TuiKeymap,
    normalize_keybinding_spec,
)


def test_misplaced_action_at_keymap_root_is_rejected() -> None:
    # Rust crate: codex-config
    # Rust module/test: tui_keymap.rs::misplaced_action_at_keymap_root_is_rejected
    with pytest.raises(ValueError, match="open_transcript"):
        TuiKeymap.from_mapping({"open_transcript": "ctrl-s"})


def test_misspelled_action_under_context_is_rejected() -> None:
    # Rust test: tui_keymap.rs::misspelled_action_under_context_is_rejected
    with pytest.raises(ValueError, match="open_transcrip"):
        TuiKeymap.from_mapping({"global": {"open_transcrip": "ctrl-x"}})


def test_misspelled_vim_text_object_action_is_rejected() -> None:
    # Rust test: tui_keymap.rs::misspelled_vim_text_object_action_is_rejected
    with pytest.raises(ValueError, match="double_quotes"):
        TuiKeymap.from_mapping({"vim_text_object": {"double_quotes": "shift-quote"}})


@pytest.mark.parametrize(
    ("context", "action"),
    [
        ("global", "edit_previous_message"),
        ("global", "confirm_edit_previous_message"),
        ("chat", "edit_previous_message"),
        ("chat", "confirm_edit_previous_message"),
        ("pager", "edit_previous_message"),
        ("pager", "edit_next_message"),
        ("pager", "confirm_edit_message"),
    ],
)
def test_removed_backtrack_actions_are_rejected(context: str, action: str) -> None:
    # Rust test: tui_keymap.rs::removed_backtrack_actions_are_rejected
    with pytest.raises(ValueError, match=action):
        TuiKeymap.from_mapping({context: {action: "ctrl-x"}})


def test_action_under_global_context_is_accepted() -> None:
    # Rust test: tui_keymap.rs::action_under_global_context_is_accepted
    keymap = TuiKeymap.from_mapping({"global": {"open_transcript": "ctrl-s"}})

    assert keymap.global_.open_transcript is not None
    assert keymap.global_.open_transcript.spec_strings() == ("ctrl-s",)
    assert keymap.to_mapping() == {"global": {"open_transcript": "ctrl-s"}}


@pytest.mark.parametrize("spec", ["minus", "alt-minus"])
def test_minus_bindings_under_global_context_are_accepted(spec: str) -> None:
    # Rust test: tui_keymap.rs::minus_bindings_under_global_context_are_accepted
    keymap = TuiKeymap.from_mapping({"global": {"open_transcript": spec}})

    assert keymap.to_mapping() == {"global": {"open_transcript": spec}}


def test_keybinding_aliases_are_canonicalized() -> None:
    # Rust behavior contract: normalize_keybinding_spec alias and modifier ordering.
    assert normalize_keybinding_spec(" control-option-shift-pageup ") == "ctrl-alt-shift-page-up"
    assert normalize_keybinding_spec("escape") == "esc"
    assert normalize_keybinding_spec("return") == "enter"
    assert normalize_keybinding_spec("spacebar") == "space"
    assert normalize_keybinding_spec("del") == "delete"


def test_keybindings_spec_preserves_single_many_and_empty_unbind() -> None:
    # Rust behavior contract: KeybindingsSpec is string-or-list, and [] explicitly unbinds.
    one = KeybindingsSpec.from_value("CTRL-A", path="tui.keymap.global.copy")
    many = KeybindingsSpec.from_value(["return", "alt-minus"], path="tui.keymap.composer.submit")
    empty = KeybindingsSpec.from_value([], path="tui.keymap.composer.submit")

    assert one == KeybindingsSpec((KeybindingSpec("ctrl-a"),), is_many=False)
    assert one.to_value() == "ctrl-a"
    assert many.spec_strings() == ("enter", "alt-minus")
    assert many.to_value() == ["enter", "alt-minus"]
    assert empty.spec_strings() == ()
    assert empty.to_value() == []


@pytest.mark.parametrize(
    "spec",
    ["", "ctrl-control-a", "a-ctrl", "meta-o", "f13"],
)
def test_malformed_keybindings_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError):
        normalize_keybinding_spec(spec)


def test_tui_aggregate_parses_typed_keymap() -> None:
    # Rust integration point: types.rs Tui.keymap uses the tui_keymap child schema.
    tui = Tui.from_mapping({"keymap": {"global": {"open_transcript": "CTRL-O"}}})

    assert isinstance(tui.keymap, TuiKeymap)
    assert tui.keymap.to_mapping() == {"global": {"open_transcript": "ctrl-o"}}
