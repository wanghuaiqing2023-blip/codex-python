from pycodex.tui.bottom_pane.request_user_input.layout import Rect
from pycodex.tui.bottom_pane.request_user_input.render import (
    MIN_OVERLAY_HEIGHT,
    StyledLine,
    cursor_pos_impl,
    desired_height,
    line_width,
    render_rows_bottom_aligned,
    render_ui,
    truncate_line_word_boundary_with_ellipsis,
    unanswered_confirmation_data,
    unanswered_confirmation_height,
)


class Composer:
    def __init__(self, text="notes"):
        self.text = text

    def current_text(self):
        return self.text

    def cursor_pos(self, area):
        return (area.x + 1, area.y + 1)


class Question:
    def __init__(self, secret=False):
        self.is_secret = secret


class Overlay:
    DESIRED_SPACERS_BETWEEN_SECTIONS = 2
    UNANSWERED_CONFIRM_TITLE = "Submit with unanswered questions?"

    def __init__(self):
        self.composer = Composer()
        self.confirm_unanswered = {"selected_idx": 1}
        self.confirm = False
        self.options = False
        self.notes_visible = True
        self.focus_notes = True
        self.secret = False

    def confirm_unanswered_active(self):
        return self.confirm

    def has_options(self):
        return self.options

    def notes_ui_visible(self):
        return self.notes_visible

    def wrapped_question_lines(self, width):
        return [StyledLine.from_text("Question line")]

    def options_preferred_height(self, width):
        return 2

    def options_required_height(self, width):
        return 4

    def notes_input_height(self, width):
        return 2

    def footer_required_height(self, width):
        return 1

    def question_count(self):
        return 2

    def current_index(self):
        return 0

    def unanswered_count(self):
        return 1

    def unanswered_question_count(self):
        return 2

    def is_question_answered(self, index, text):
        return bool(text)

    def option_rows(self, width):
        return ["one", "two", "three"]

    def current_answer(self):
        return {"selected_idx": 1}

    def current_question(self):
        return Question(self.secret)

    def focus_is_notes(self):
        return self.focus_notes

    def footer_tip_lines_with_prefix(self, width, prefix=None):
        row = []
        if prefix:
            row.append(prefix)
        row.append("enter submit")
        row.append("esc cancel")
        return [row]

    def selected_option_index(self):
        return 1

    def options_len(self):
        return 3

    def unanswered_confirmation_rows(self):
        return ["first", "second"]


def test_desired_height_uses_minimum_and_component_heights():
    overlay = Overlay()
    assert desired_height(overlay, 20) == MIN_OVERLAY_HEIGHT
    overlay.options = True
    assert desired_height(overlay, 20) == 9


def test_unanswered_confirmation_data_pluralizes_and_carries_rows_state():
    overlay = Overlay()
    data = unanswered_confirmation_data(overlay)
    assert data.title_line.text == "Submit with unanswered questions?"
    assert data.subtitle_line.text == "2 unanswered questions"
    assert data.rows == ["first", "second"]
    assert data.state == {"selected_idx": 1}


def test_unanswered_confirmation_height_respects_minimum():
    overlay = Overlay()
    assert unanswered_confirmation_height(overlay, 20) == MIN_OVERLAY_HEIGHT


def test_line_width_and_word_boundary_truncation():
    line = StyledLine.from_text("hello world again")
    assert line_width(line) == 17
    assert truncate_line_word_boundary_with_ellipsis(line, 9).text == "hello…"
    assert truncate_line_word_boundary_with_ellipsis(line, 0).text == ""


def test_render_rows_bottom_aligned_offsets_short_rows_to_bottom():
    events = render_rows_bottom_aligned(Rect(0, 0, 10, 4), ["one", "two"], {"selected_idx": 1}, 10, "empty")
    assert [event["y"] for event in events] == [2, 3]
    assert events[1]["selected"] is True


def test_cursor_pos_only_when_notes_focused_visible_and_area_nonzero():
    overlay = Overlay()
    assert cursor_pos_impl(overlay, Rect(0, 0, 20, 8)) == (2, 4)
    overlay.focus_notes = False
    assert cursor_pos_impl(overlay, Rect(0, 0, 20, 8)) is None


def test_render_ui_outputs_progress_question_notes_and_footer_semantics():
    overlay = Overlay()
    events = render_ui(overlay, Rect(0, 0, 30, 8))
    texts = [event.get("text") for event in events]
    assert "Question 1/2 (1 unanswered)" in texts
    assert "Question line" in texts
    assert "notes" in texts
    assert any("enter submit" in str(text) for text in texts)


def test_render_ui_unanswered_confirmation_branch():
    overlay = Overlay()
    overlay.confirm = True
    events = render_ui(overlay, Rect(0, 0, 30, 8))
    assert any(event.get("kind") == "unanswered_header" for event in events)
    assert any(event.get("text") == "Submit with unanswered questions?" for event in events)

def test_truncation_uses_display_width() -> None:
    line = StyledLine.from_text("你好 world")
    truncated = truncate_line_word_boundary_with_ellipsis(line, 5)
    assert truncated.text == "你好…"
    assert line_width(truncated) == 5

