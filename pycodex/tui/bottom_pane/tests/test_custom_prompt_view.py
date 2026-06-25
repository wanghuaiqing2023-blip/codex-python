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
    assert view.textarea.cursor == len("hello")
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


def test_render_uses_title_context_gutter_placeholder_and_hint():
    view = CustomPromptView.new("Title", "Placeholder", "", "Context", lambda _text: None)

    lines = view.render((0, 0, 40, 10))

    assert lines[0].text == f"{gutter()}Title"
    assert lines[0].style == "title"
    assert lines[1].text == f"{gutter()}Context"
    assert lines[2].text == gutter()
    assert lines[3].text == "Placeholder"
    assert lines[3].style == "placeholder"
    assert "enter" in lines[-1].text
    assert "esc" in lines[-1].text
