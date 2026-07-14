from pycodex.tui.bottom_pane.custom_prompt_view import CancellationEvent
from pycodex.tui.bottom_pane.custom_prompt_view import CustomPromptView
from pycodex.tui.bottom_pane.custom_prompt_view import ViewCompletion
from pycodex.tui.bottom_pane.custom_prompt_view import gutter


def _view(submitted):
    return CustomPromptView.new(
        "Custom instructions",
        "Type instructions",
        "",
        None,
        submitted.append,
    )


def test_new_sets_initial_text_and_cursor_to_end():
    submitted = []
    view = CustomPromptView.new("Title", "Placeholder", "hello", "Context", submitted.append)

    assert view.textarea.text() == "hello"
    assert view.textarea.cursor() == len("hello")
    assert view.context_label == "Context"
    assert not view.is_complete()


def test_enter_submits_trimmed_non_empty_text_and_marks_accepted():
    submitted = []
    view = _view(submitted)
    view.handle_paste("  review this  ")

    view.handle_key_event("enter")

    assert submitted == ["review this"]
    assert view.completion() is ViewCompletion.ACCEPTED
    assert view.is_complete()


def test_enter_with_empty_trimmed_text_does_not_submit_or_complete():
    submitted = []
    view = _view(submitted)
    view.handle_paste("   \n  ")

    view.handle_key_event("enter")

    assert submitted == []
    assert view.completion() is None
    assert not view.is_complete()


def test_modified_enter_inserts_newline_instead_of_submit():
    submitted = []
    view = _view(submitted)
    key = type("Key", (), {"code": "enter", "modifiers": "shift"})()

    view.handle_key_event(key)

    assert view.textarea.text() == "\n"
    assert submitted == []
    assert not view.is_complete()


def test_escape_ctrl_c_and_paste_boundaries():
    submitted = []
    view = _view(submitted)

    assert view.handle_paste("") is False
    assert view.handle_paste("abc") is True
    assert view.textarea.text() == "abc"
    assert view.on_ctrl_c() is CancellationEvent.HANDLED
    assert view.completion() is ViewCompletion.CANCELLED


def test_height_and_cursor_position_follow_rust_offsets():
    view = CustomPromptView.new("Title", "Placeholder", "abc", "Context", lambda _text: None)

    assert view.input_height(20) == 2
    assert view.desired_height(20) == 7
    assert view.cursor_pos((5, 10, 20, 7)) == (10, 13)
    assert view.cursor_pos((0, 0, 2, 7)) is None
    assert view.cursor_pos((0, 0, 20, 1)) is None


def test_prefilled_prompt_supports_navigation_delete_and_committed_ime_text():
    # Rust: CustomPromptView delegates ordinary keys and paste payloads to its
    # TextArea, so a prefilled goal can be edited rather than only appended to.
    view = CustomPromptView.new("Edit goal", "Objective", "旧的目标", None, lambda _text: None)

    view.handle_key_event("home")
    view.handle_key_event("delete")
    view.handle_paste("新的")
    view.handle_key_event("delete")
    view.handle_key_event("end")
    view.handle_key_event("left")
    view.handle_key_event("right")

    assert view.textarea.text() == "新的目标"
    assert view.textarea.cursor() == len("新的目标")


def test_cursor_position_uses_terminal_width_for_chinese_text():
    view = CustomPromptView.new("Edit goal", "Objective", "你好", None, lambda _text: None)

    assert view.cursor_pos((0, 0, 20, 6)) == (6, 2)


def test_render_uses_title_context_gutter_placeholder_and_hint():
    view = CustomPromptView.new("Title", "Placeholder", "", "Context", lambda _text: None)

    lines = view.render((0, 0, 40, 10))

    assert lines[0].text == f"{gutter()}Title"
    assert lines[0].style == "title"
    assert lines[1].text == f"{gutter()}Context"
    assert lines[2].text == gutter()
    assert lines[3].text == f"{gutter()}Placeholder"
    assert lines[3].style == "placeholder"
    assert "enter" in lines[-1].text
    assert "esc" in lines[-1].text
    assert gutter() == "▌ "


def test_single_character_input_preserves_case():
    view = _view([])

    view.handle_key_event("A")

    assert view.textarea.text() == "A"


def test_goal_edit_prompt_matches_rust_snapshot_structure():
    # Rust: chatwidget/tests/goal_menu.rs::goal_edit_prompt_snapshot.
    view = CustomPromptView.new(
        "Edit goal",
        "Describe the updated goal",
        "Keep improving the bare goal command until it feels calm and useful.",
        None,
        lambda _text: None,
    )

    lines = [line.text.rstrip() for line in view.render((0, 0, 100, view.desired_height(100)))]

    assert lines == [
        "▌ Edit goal",
        "▌",
        "▌ Keep improving the bare goal command until it feels calm and useful.",
        "",
        "Press enter to confirm or esc to go back",
    ]


def test_enter_with_none_modifier_submits_like_rust_key_modifiers_none():
    submitted = []
    view = _view(submitted)
    view.handle_paste("updated goal")
    key = type("Key", (), {"code": "enter", "modifiers": "KeyModifiers.NONE"})()

    view.handle_key_event(key)

    assert submitted == ["updated goal"]
    assert view.completion() is ViewCompletion.ACCEPTED
