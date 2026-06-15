from __future__ import annotations

from pycodex.tui.public_widgets.composer_input import ComposerAction, ComposerInput, default


def test_new_default_and_empty_clear_semantics_match_public_wrapper() -> None:
    # Rust: ComposerInput::new/default creates a focused composer with neutral placeholder.
    composer = ComposerInput.new()
    assert default().placeholder == "Compose new task"
    assert composer.enhanced_keys_supported is True
    assert composer.is_empty() is True

    composer.handle_paste("hello")
    assert composer.is_empty() is False
    composer.clear()
    assert composer.is_empty() is True


def test_input_enter_submits_and_shift_enter_inserts_newline() -> None:
    # Rust: input maps ChatComposer Submitted to ComposerAction::Submitted; Shift+Enter is newline behavior.
    composer = ComposerInput.new()
    composer.input({"code": "h"})
    composer.input({"code": "i"})
    assert composer.input({"code": "Enter", "modifiers": {"shift"}}) == ComposerAction.none()
    composer.input({"code": "!"})

    action = composer.input({"code": "Enter"})

    assert action == ComposerAction.submitted("hi\n!")
    assert composer.is_empty() is True


def test_input_backspace_and_non_text_control_keys_do_not_submit() -> None:
    composer = ComposerInput.new()
    composer.handle_paste("abc")
    assert composer.input({"code": "Backspace"}) == ComposerAction.none()
    assert composer.text == "ab"
    assert composer.input({"code": "x", "modifiers": {"control"}}) == ComposerAction.none()
    assert composer.text == "ab"


def test_handle_paste_and_flush_burst_semantics() -> None:
    # Rust: handle_paste delegates to ChatComposer and drains app events; flush returns whether text changed/redraw is due.
    composer = ComposerInput.new()
    assert composer.handle_paste("") is False
    assert composer.is_in_paste_burst() is False
    assert composer.handle_paste("chunk") is True
    assert composer.text == "chunk"
    assert composer.is_in_paste_burst() is True
    assert composer.flush_paste_burst_if_due() is True
    assert composer.is_in_paste_burst() is False
    assert composer.flush_paste_burst_if_due() is False


def test_hint_item_override_round_trips_stringified_pairs() -> None:
    # Rust: set_hint_items maps Into<String> pairs and clear restores default hints.
    composer = ComposerInput.new()
    composer.set_hint_items([("enter", "submit"), (1, "first")])
    assert composer.hint_items == (("enter", "submit"), ("1", "first"))
    composer.clear_hint_items()
    assert composer.hint_items is None


def test_desired_height_cursor_and_render_ref_are_semantic_boundaries() -> None:
    # Rust delegates desired_height/cursor_pos/render_ref to ChatComposer; Python exposes deterministic semantic equivalents.
    composer = ComposerInput.new()
    composer.handle_paste("abcdef\nxy")
    assert composer.desired_height(3) == 4
    assert composer.cursor_pos({"x": 10, "y": 5, "width": 3, "height": 5}) == (12, 6)
    assert composer.cursor_pos({"x": 0, "y": 0, "width": 0, "height": 1}) is None

    buf: list[dict[str, object]] = []
    rendered = composer.render_ref((1, 2, 10, 3), buf)
    assert rendered["area"] == (1, 2, 10, 3)
    assert rendered["lines"] == ("abcdef", "xy")
    assert buf == [rendered]


def test_recommended_flush_delay_is_positive_duration_slice() -> None:
    assert ComposerInput.recommended_flush_delay() > 0


def test_disable_paste_burst_keeps_paste_handled_without_active_burst() -> None:
    composer = ComposerInput(disable_paste_burst=True)

    assert composer.handle_paste("chunk") is True

    assert composer.text == "chunk"
    assert composer.is_in_paste_burst() is False
    assert composer.flush_paste_burst_if_due() is False


def test_input_paste_and_flush_drain_app_events_like_rust_wrapper() -> None:
    composer = ComposerInput.new()
    composer._events.extend(["queued"])

    composer.input({"code": "a"})
    assert composer._events == []

    composer._events.extend(["queued"])
    composer.handle_paste("b")
    assert composer._events == []

    composer._events.extend(["queued"])
    composer.flush_paste_burst_if_due()
    assert composer._events == []